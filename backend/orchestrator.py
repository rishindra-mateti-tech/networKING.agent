import asyncio
import datetime
import html
import httpx
from sqlalchemy.orm import Session

import models
from database import SessionLocal
from twin_agent import compile_twin_agent_profile
from generator import analyze_candidate_bridge, generate_outreach_variants

class QueueOrchestrator:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(QueueOrchestrator, cls).__new__(cls, *args, **kwargs)
            cls._instance.active_workers = {}  # user_id -> list of asyncio.Task
            cls._instance.user_locks = {}      # user_id -> asyncio.Lock (to prevent race conditions in connection pulling)
            cls._instance.user_triggers = {}   # user_id -> asyncio.Event (to wake workers immediately)
            cls._instance.running = False
        return cls._instance

    def start(self):
        """Starts the main orchestrator monitoring loop."""
        if not self.running:
            self.running = True
            self.loop_task = asyncio.create_task(self._orchestrator_loop())
            print("[ORCHESTRATOR] QueueOrchestrator started with periodic monitoring loop.")

    def stop(self):
        """Stops the orchestrator and cancels all active workers."""
        self.running = False
        if hasattr(self, 'loop_task') and self.loop_task:
            self.loop_task.cancel()
        for user_id, tasks in list(self.active_workers.items()):
            for task in tasks:
                task.cancel()
        self.active_workers.clear()
        print("[ORCHESTRATOR] QueueOrchestrator stopped and all workers cancelled.")

    async def _orchestrator_loop(self):
        """Periodically syncs workers for all users."""
        while self.running:
            try:
                db = SessionLocal()
                try:
                    users = db.query(models.User).all()
                    for user in users:
                        await self.sync_user_workers(user.id)
                finally:
                    db.close()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[ORCHESTRATOR] Error in monitoring loop: {e}")
            await asyncio.sleep(10)

    def get_user_lock(self, user_id: int) -> asyncio.Lock:
        """Retrieves or creates a thread-safe lock for connection selection for a given user."""
        if user_id not in self.user_locks:
            self.user_locks[user_id] = asyncio.Lock()
        return self.user_locks[user_id]

    def get_user_trigger(self, user_id: int) -> asyncio.Event:
        """Retrieves or creates an asyncio.Event trigger for a given user to wake workers immediately."""
        if user_id not in self.user_triggers:
            self.user_triggers[user_id] = asyncio.Event()
        return self.user_triggers[user_id]

    def trigger_now(self, user_id: int):
        """
        Immediately wakes up all sleeping workers for a user by setting the trigger event.
        Called when a new connection is added or user manually triggers processing.
        """
        trigger = self.get_user_trigger(user_id)
        trigger.set()
        print(f"[ORCHESTRATOR] Trigger fired for User {user_id} — workers waking up immediately.")

    async def sync_user_workers(self, user_id: int):
        """
        Dynamically adjusts the number of concurrent worker tasks for a user
        to match the number of active primary API keys they have configured.
        """
        if not self.running:
            return

        db = SessionLocal()
        try:
            now = datetime.datetime.utcnow()
            # Clear expired cooldowns
            expired = db.query(models.ApiKey).filter(
                models.ApiKey.user_id == user_id,
                models.ApiKey.cooldown_until != None,
                models.ApiKey.cooldown_until <= now
            ).all()
            if expired:
                for k in expired:
                    k.cooldown_until = None
                db.commit()

            # Fetch active primary API keys
            active_keys = db.query(models.ApiKey).filter(
                models.ApiKey.user_id == user_id,
                models.ApiKey.is_active == True,
                models.ApiKey.role == "primary",
                (models.ApiKey.cooldown_until == None) | (models.ApiKey.cooldown_until < now)
            ).all()

            desired_worker_count = len(active_keys)
            
            # If no primary keys, see if we can use standby keys instead of stopping completely
            if desired_worker_count == 0:
                standby_keys = db.query(models.ApiKey).filter(
                    models.ApiKey.user_id == user_id,
                    models.ApiKey.is_active == True,
                    models.ApiKey.role == "standby",
                    (models.ApiKey.cooldown_until == None) | (models.ApiKey.cooldown_until < now)
                ).all()
                desired_worker_count = min(len(standby_keys), 1) # Run at least one standby worker

            # If all configured keys are temporarily in cooldown, keep at least 1 worker polling
            all_user_keys = db.query(models.ApiKey).filter(
                models.ApiKey.user_id == user_id,
                models.ApiKey.is_active == True
            ).count()
            if desired_worker_count == 0 and all_user_keys > 0:
                desired_worker_count = 1

            current_workers = self.active_workers.get(user_id, [])
            current_worker_count = len(current_workers)

            if current_worker_count < desired_worker_count:
                # Spawn more workers
                diff = desired_worker_count - current_worker_count
                print(f"[ORCHESTRATOR] Spawning {diff} new workers for User {user_id}.")
                if user_id not in self.active_workers:
                    self.active_workers[user_id] = []
                for idx in range(diff):
                    worker_index = current_worker_count + idx
                    task = asyncio.create_task(self._worker_loop(user_id, f"Worker_{worker_index}", worker_index))
                    self.active_workers[user_id].append(task)
            elif current_worker_count > desired_worker_count:
                # Terminate excess workers
                diff = current_worker_count - desired_worker_count
                print(f"[ORCHESTRATOR] Terminating {diff} excess workers for User {user_id}.")
                for _ in range(diff):
                    task = self.active_workers[user_id].pop()
                    task.cancel()
        except Exception as e:
            print(f"[ORCHESTRATOR] Error syncing workers for User {user_id}: {e}")
        finally:
            db.close()

    async def _send_telegram_alert(self, token: str, chat_id: str, text: str):
        """Dispatches an asynchronous Telegram notification."""
        token = token.strip() if token else ""
        chat_id = chat_id.strip() if chat_id else ""
        if not token or not chat_id:
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(url, json=payload, timeout=10.0)
                if res.status_code == 200:
                    print(f"[ORCHESTRATOR] Telegram notification sent successfully to chat {chat_id}.")
                else:
                    print(f"[ORCHESTRATOR] Telegram API error ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"[ORCHESTRATOR] Failed to send Telegram alert: {e}")

    async def _send_slack_alert(self, webhook_url: str, text: str):
        """Dispatches an asynchronous Slack notification via an Incoming Webhook."""
        webhook_url = webhook_url.strip() if webhook_url else ""
        if not webhook_url:
            return

        payload = {"text": text}
        try:
            async with httpx.AsyncClient() as client:
                res = await client.post(webhook_url, json=payload, timeout=10.0)
                if res.status_code == 200:
                    print(f"[ORCHESTRATOR] Slack notification sent successfully.")
                else:
                    print(f"[ORCHESTRATOR] Slack API error ({res.status_code}): {res.text}")
        except Exception as e:
            print(f"[ORCHESTRATOR] Failed to send Slack alert: {e}")

    async def _interruptible_sleep(self, user_id: int, seconds: float):
        """
        Sleeps for the given duration but can be interrupted immediately
        when the user's trigger event is set (e.g., new connection added
        or manual 'Process Queue Now' clicked).
        """
        trigger = self.get_user_trigger(user_id)
        trigger.clear()  # Reset the trigger before sleeping
        try:
            await asyncio.wait_for(trigger.wait(), timeout=seconds)
            # If we get here, the trigger was set — clear it for next use
            trigger.clear()
            print(f"[ORCHESTRATOR] Sleep interrupted by trigger for User {user_id}.")
        except asyncio.TimeoutError:
            # Normal timeout — sleep completed naturally
            pass

    async def _worker_loop(self, user_id: int, worker_name: str, worker_index: int = 0):
        """
        The execution loop for an individual WorkerThread.
        Pulls connection queue items, processes using Gemini APIs, handles cooldown failover, and sends alerts.
        """
        print(f"[WORKER] {worker_name} started for User {user_id}.")
        while self.running:
            db = SessionLocal()
            connection = None
            try:
                # 1. Thread-safe lock to pull next pending connection
                lock = self.get_user_lock(user_id)
                async with lock:
                    connection = db.query(models.Connection).filter(
                        models.Connection.user_id == user_id,
                        models.Connection.status == "pending"
                    ).order_by(
                        models.Connection.is_starred.desc(),
                        models.Connection.created_at.asc()
                    ).first()

                    if connection:
                        connection.status = "processing"
                        connection.error_message = None
                        db.commit()
                        db.refresh(connection)

                # If no pending connection, use interruptible sleep and try again
                if not connection:
                    await self._interruptible_sleep(user_id, 5)
                    continue

                print(f"[WORKER] {worker_name} picked connection: {connection.name} (Starred: {connection.is_starred})")

                # 2. Get API key for this worker operation. Each worker prefers a distinct
                # key (by its stable worker_index) so parallel workers actually spread load
                # across the whole key pool instead of piling onto whichever key is oldest.
                api_key_record = self._get_available_key(db, user_id, worker_index)
                if not api_key_record:
                    # Check if there are keys in cooldown vs no active keys configured
                    has_active_keys = db.query(models.ApiKey).filter(
                        models.ApiKey.user_id == user_id,
                        models.ApiKey.is_active == True
                    ).first()
                    connection.status = "pending"
                    if has_active_keys:
                        connection.error_message = "API key temporarily in cooldown. Retrying shortly..."
                    else:
                        connection.error_message = "No available API keys (all are in cooldown/inactive)."
                    db.commit()
                    print(f"[WORKER] {worker_name} paused: No active API keys available for User {user_id}.")
                    await self._interruptible_sleep(user_id, 15) # Cooldown wait
                    continue

                # 3. Retrieve settings context (TwinAgent profile, Telegram details, pacing)
                settings_records = db.query(models.Setting).filter(models.Setting.user_id == user_id).all()
                settings = {s.key: s.value for s in settings_records if s.value}

                telegram_token = settings.get("telegram_token")
                telegram_chat_id = settings.get("telegram_chat_id")
                slack_webhook_url = settings.get("slack_webhook_url")

                # Default pacing is 15 minutes, but user can change it
                try:
                    pacing_min = float(settings.get("pacing_interval_minutes", 15.0))
                except ValueError:
                    pacing_min = 15.0

                twin_profile = compile_twin_agent_profile(db, user_id)

                # 4. Generate with Failover Pool Retry
                success = False
                attempts = 0
                max_attempts = 3
                current_key_record = api_key_record

                while not success and attempts < max_attempts:
                    attempts += 1
                    try:
                        print(f"[WORKER] {worker_name} executing Gemini call with key: {current_key_record.label or 'unlabeled'}")
                                           # Step A: Bridge Analysis in non-blocking thread
                        bridge_data = await asyncio.to_thread(
                            analyze_candidate_bridge,
                            api_key=current_key_record.key_value,
                            twin_profile=twin_profile,
                            candidate_name=connection.name,
                            candidate_profile=connection.profile_text or "",
                            candidate_posts=connection.posts_text or "",
                            screenshot_path=connection.screenshot_path
                        )
                        
                        # Sync manually specified hiring_badge_status if set, and backfill
                        # name/title/company from the AI's own extraction when the PDF
                        # metadata heuristic (parser.py) failed to find them. Gemini reads
                        # the same raw text with far more context than the regex heuristic,
                        # so it often gets the name right even when the heuristic didn't.
                        try:
                            import json as j
                            p_intel = j.loads(bridge_data.get("profile_intelligence") or "{}")
                            if connection.hiring_badge_status:
                                p_intel["hiring_badge_status"] = connection.hiring_badge_status
                                bridge_data["profile_intelligence"] = j.dumps(p_intel)

                            ai_name = (p_intel.get("name") or "").strip()
                            if ai_name and connection.name in (None, "", "Unknown Candidate"):
                                connection.name = ai_name
                            ai_title = (p_intel.get("title") or p_intel.get("role") or "").strip()
                            if ai_title and not connection.current_title:
                                connection.current_title = ai_title
                            ai_company = (p_intel.get("company") or "").strip()
                            if ai_company and not connection.company:
                                connection.company = ai_company
                        except Exception:
                            pass

                        # Step B: Variants Generation in non-blocking thread
                        variants = await asyncio.to_thread(
                            generate_outreach_variants,
                            api_key=current_key_record.key_value,
                            twin_profile=twin_profile,
                            candidate_name=connection.name,
                            candidate_profile=connection.profile_text or "",
                            candidate_posts=connection.posts_text or "",
                            bridge_data=bridge_data,
                            tone_examples=settings.get("tone_examples", "")
                        )
                        
                        # Save successful outreach
                        connection.why_person = bridge_data["why_person"]
                        connection.bridge = bridge_data["bridge"]
                        connection.best_angle = bridge_data["best_angle"]
                        connection.profile_intelligence = bridge_data["profile_intelligence"]
                        connection.company_intelligence = bridge_data["company_intelligence"]
                        connection.relationship_strategy = bridge_data["relationship_strategy"]
                        connection.personalization_data = bridge_data["personalization_data"]
                        connection.context_summary = bridge_data["context_summary"]
                        
                        # Save new platform metrics
                        connection.networking_score = bridge_data["networking_score"]
                        connection.reply_probability = bridge_data["reply_probability"]
                        connection.hiring_probability_score = bridge_data["hiring_probability_score"]
                        connection.is_decision_maker = bridge_data["is_decision_maker"]
                        connection.referral_potential = bridge_data["referral_potential"]
                        connection.networking_difficulty = bridge_data["networking_difficulty"]
                        connection.conversation_starter = bridge_data["conversation_starter"]
                        connection.avoid_points = bridge_data["avoid_points"]
                        connection.best_message_type = bridge_data["best_message_type"]
                        
                        # Save variants
                        connection.generated_outreach_short = variants["short"]
                        connection.generated_outreach_warm = variants["warm"]
                        connection.generated_outreach_tech = variants["tech"]
                        connection.generated_outreach_mixed = variants["mixed"]
                        
                        connection.generated_outreach_referral = variants.get("referral")
                        connection.generated_outreach_coffee = variants.get("coffee")
                        connection.generated_outreach_technical = variants.get("technical")
                        connection.generated_outreach_relationship = variants.get("relationship")
                        connection.generated_outreach_featured = variants.get("featured")
                        
                        connection.status = "completed"
                        db.commit()
                        success = True
                        print(f"[WORKER] {worker_name} successfully finished generation for {connection.name}.")
                        
                        # Build shared notification content (used by both Telegram and Slack)
                        if (telegram_token and telegram_chat_id) or slack_webhook_url:
                            import json as j

                            try:
                                company_intel = j.loads(bridge_data.get("company_intelligence") or "{}")
                            except Exception:
                                company_intel = {}

                            raw_name = connection.name or "Candidate"
                            raw_title = connection.current_title or "Software Professional"
                            raw_company = connection.company or "Company"
                            raw_company_class = company_intel.get("company_type") or "Startup"

                            networking_score = f"{connection.networking_score or 5.0}"
                            reply_probability = f"{int(connection.reply_probability or 50)}"

                            hiring_val = connection.hiring_badge_status or company_intel.get("hiring_status") or connection.hiring_probability_score or "unknown"
                            raw_hiring_probability = str(hiring_val).capitalize()

                            raw_is_decision_maker = (connection.is_decision_maker or "no").capitalize()
                            raw_referral_potential = (connection.referral_potential or "medium").capitalize()
                            raw_networking_difficulty = (connection.networking_difficulty or "medium").replace('_', ' ').capitalize()

                            raw_conversation_starter = connection.conversation_starter or "None"
                            raw_avoid_points = connection.avoid_points or "None"
                            raw_best_message_type = connection.best_message_type or "Technical curiosity"

                            raw_referral = connection.generated_outreach_referral or ""
                            raw_coffee = connection.generated_outreach_coffee or ""
                            raw_technical = connection.generated_outreach_technical or ""
                            raw_relationship = connection.generated_outreach_relationship or ""
                            raw_featured = connection.generated_outreach_featured or ""

                            # --- Telegram (HTML parse_mode) ---
                            if telegram_token and telegram_chat_id:
                                safe_name = html.escape(raw_name)
                                safe_title = html.escape(raw_title)
                                safe_company = html.escape(raw_company)
                                company_class = html.escape(raw_company_class)
                                profile_url_block = ""
                                if connection.profile_url:
                                    profile_url_block = f"🔗 <b>LinkedIn URL</b>: {html.escape(connection.profile_url)}\n"
                                hiring_probability = html.escape(raw_hiring_probability)
                                is_decision_maker = html.escape(raw_is_decision_maker)
                                referral_potential = html.escape(raw_referral_potential)
                                networking_difficulty = html.escape(raw_networking_difficulty)
                                conversation_starter = html.escape(raw_conversation_starter)
                                avoid_points = html.escape(raw_avoid_points)
                                best_message_type = html.escape(raw_best_message_type)
                                safe_referral = html.escape(raw_referral)
                                safe_coffee = html.escape(raw_coffee)
                                safe_technical = html.escape(raw_technical)
                                safe_relationship = html.escape(raw_relationship)
                                safe_featured = html.escape(raw_featured)

                                telegram_text = (
                                    f"✨ <b>Outreach Intelligence Ready for {safe_name}!</b>\n"
                                    f"💼 <b>Role</b>: {safe_title} @ {safe_company}\n"
                                    f"🏢 <b>Classification</b>: {company_class}\n"
                                    f"{profile_url_block}\n"
                                    f"🌟 <b>Networking Score</b>: {networking_score}/10\n"
                                    f"📈 <b>Reply Probability</b>: {reply_probability}%\n"
                                    f"💼 <b>Hiring Probability</b>: {hiring_probability}\n"
                                    f"🔑 <b>Decision Maker</b>: {is_decision_maker}\n"
                                    f"🤝 <b>Referral Potential</b>: {referral_potential}\n"
                                    f"🧗 <b>Networking Difficulty</b>: {networking_difficulty}\n\n"
                                    f"💡 <b>Conversation Starter</b>: {conversation_starter}\n"
                                    f"⚠️ <b>Avoid</b>: {avoid_points}\n"
                                    f"🎯 <b>Best Message Type</b>: {best_message_type}\n\n"
                                    f"----------------------------\n"
                                    f"📝 <b>REFERRAL DRAFT</b>\n<code>{safe_referral}</code>\n\n"
                                    f"----------------------------\n"
                                    f"📝 <b>COFFEE CHAT DRAFT</b>\n<code>{safe_coffee}</code>\n\n"
                                    f"----------------------------\n"
                                    f"📝 <b>TECHNICAL DRAFT</b>\n<code>{safe_technical}</code>\n\n"
                                    f"----------------------------\n"
                                    f"📝 <b>RELATIONSHIP BUILDING DRAFT</b>\n<code>{safe_relationship}</code>\n\n"
                                    f"----------------------------\n"
                                    f"📝 <b>FEATURED OUTREACH DRAFT (No Limit)</b>\n<code>{safe_featured}</code>\n\n"
                                    f"----------------------------\n"
                                    f"<i>Review, select & copy from your networKING dashboard.</i>"
                                )
                                await self._send_telegram_alert(telegram_token, telegram_chat_id, telegram_text)

                            # --- Slack (mrkdwn) ---
                            if slack_webhook_url:
                                def _slack_escape(s: str) -> str:
                                    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

                                profile_url_line = ""
                                if connection.profile_url:
                                    profile_url_line = f"🔗 *LinkedIn URL*: {_slack_escape(connection.profile_url)}\n"

                                slack_text = (
                                    f"✨ *Outreach Intelligence Ready for {_slack_escape(raw_name)}!*\n"
                                    f"💼 *Role*: {_slack_escape(raw_title)} @ {_slack_escape(raw_company)}\n"
                                    f"🏢 *Classification*: {_slack_escape(raw_company_class)}\n"
                                    f"{profile_url_line}\n"
                                    f"🌟 *Networking Score*: {networking_score}/10\n"
                                    f"📈 *Reply Probability*: {reply_probability}%\n"
                                    f"💼 *Hiring Probability*: {_slack_escape(raw_hiring_probability)}\n"
                                    f"🔑 *Decision Maker*: {_slack_escape(raw_is_decision_maker)}\n"
                                    f"🤝 *Referral Potential*: {_slack_escape(raw_referral_potential)}\n"
                                    f"🧗 *Networking Difficulty*: {_slack_escape(raw_networking_difficulty)}\n\n"
                                    f"💡 *Conversation Starter*: {_slack_escape(raw_conversation_starter)}\n"
                                    f"⚠️ *Avoid*: {_slack_escape(raw_avoid_points)}\n"
                                    f"🎯 *Best Message Type*: {_slack_escape(raw_best_message_type)}\n\n"
                                    f"----------------------------\n"
                                    f"📝 *REFERRAL DRAFT*\n```{_slack_escape(raw_referral)}```\n"
                                    f"----------------------------\n"
                                    f"📝 *COFFEE CHAT DRAFT*\n```{_slack_escape(raw_coffee)}```\n"
                                    f"----------------------------\n"
                                    f"📝 *TECHNICAL DRAFT*\n```{_slack_escape(raw_technical)}```\n"
                                    f"----------------------------\n"
                                    f"📝 *RELATIONSHIP BUILDING DRAFT*\n```{_slack_escape(raw_relationship)}```\n"
                                    f"----------------------------\n"
                                    f"📝 *FEATURED OUTREACH DRAFT (No Limit)*\n```{_slack_escape(raw_featured)}```\n"
                                    f"----------------------------\n"
                                    f"_Review, select & copy from your networKING dashboard._"
                                )
                                await self._send_slack_alert(slack_webhook_url, slack_text)


                    except Exception as e:
                        # Catch quota/rate limit error (typically 429) or invalid keys
                        error_str = str(e).lower()
                        print(f"[WORKER] {worker_name} failed attempt {attempts} with key error: {e}")
                        
                        # Cooldown the failing key for 3 minutes
                        current_key_record.cooldown_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=3)
                        db.commit()
                        
                        if telegram_token and telegram_chat_id:
                            alert_msg = f"⚠️ <b>Key Cooldown alert:</b> API key '{current_key_record.label}' encountered an error and was placed in cooldown for 3 minutes."
                            await self._send_telegram_alert(telegram_token, telegram_chat_id, alert_msg)
                        if slack_webhook_url:
                            await self._send_slack_alert(slack_webhook_url, f"⚠️ *Key Cooldown alert:* API key '{current_key_record.label}' encountered an error and was placed in cooldown for 3 minutes.")

                        # Attempt to failover to a standby key
                        fallback_key = self._get_backup_key(db, user_id)
                        if fallback_key:
                            print(f"[WORKER] {worker_name} hot-swapping to standby key: {fallback_key.label or 'unlabeled'}")
                            current_key_record = fallback_key
                            if telegram_token and telegram_chat_id:
                                alert_msg = f"🔄 <b>Failover active:</b> Swapped to standby key '{fallback_key.label}'."
                                await self._send_telegram_alert(telegram_token, telegram_chat_id, alert_msg)
                            if slack_webhook_url:
                                await self._send_slack_alert(slack_webhook_url, f"🔄 *Failover active:* Swapped to standby key '{fallback_key.label}'.")
                        else:
                            # No standby key found, exit attempt loop
                            break

                if not success:
                    # Final fallback: return connection to pending status
                    connection.status = "pending"
                    connection.error_message = "Failed to generate outreach after failover attempts."
                    db.commit()
                    print(f"[WORKER] {worker_name} failed to process connection: {connection.name}. Returned to queue.")
                    await self._interruptible_sleep(user_id, 10)
                    continue

                # 5. Pacing: check if more connections are pending to proceed immediately, otherwise sleep
                has_more_pending = db.query(models.Connection).filter(
                    models.Connection.user_id == user_id,
                    models.Connection.status == "pending"
                ).first() is not None

                if has_more_pending:
                    print(f"[WORKER] {worker_name} completed outreach task. More pending items in queue. Proceeding in 2 seconds.")
                    await self._interruptible_sleep(user_id, 2)
                else:
                    print(f"[WORKER] {worker_name} completed outreach task. Queue is empty. Pacing sleep of {pacing_min} minutes started.")
                    await self._interruptible_sleep(user_id, pacing_min * 60)


            except asyncio.CancelledError:
                print(f"[WORKER] {worker_name} task cancelled.")
                break
            except Exception as e:
                print(f"[WORKER] {worker_name} general error: {e}")
                if connection:
                    try:
                        connection.status = "pending"
                        connection.error_message = f"Worker runtime exception: {str(e)}"
                        db.commit()
                    except Exception:
                        pass
                await self._interruptible_sleep(user_id, 10)
            finally:
                db.close()

    def _get_available_key(self, db: Session, user_id: int, worker_index: int = 0) -> models.ApiKey:
        """
        Pulls an active, non-cooldown primary key, preferring the key at `worker_index`
        in the ordered pool so each concurrent worker sticks to its own key rather than
        every worker competing for whichever key is oldest. Falls back to any other
        available primary key (mod-wrapped), then to standby keys, if its preferred key
        is missing or in cooldown.
        """
        now = datetime.datetime.utcnow()
        expired = db.query(models.ApiKey).filter(
            models.ApiKey.user_id == user_id,
            models.ApiKey.cooldown_until != None,
            models.ApiKey.cooldown_until <= now
        ).all()
        if expired:
            for k in expired:
                k.cooldown_until = None
            db.commit()

        available_primary_keys = db.query(models.ApiKey).filter(
            models.ApiKey.user_id == user_id,
            models.ApiKey.is_active == True,
            models.ApiKey.role == "primary",
            (models.ApiKey.cooldown_until == None) | (models.ApiKey.cooldown_until < now)
        ).order_by(models.ApiKey.created_at.asc()).all()

        key = None
        if available_primary_keys:
            key = available_primary_keys[worker_index % len(available_primary_keys)]

        # If no primary keys are available, fallback to an active standby key
        if not key:
            key = self._get_backup_key(db, user_id)
        return key

    def _get_backup_key(self, db: Session, user_id: int) -> models.ApiKey:
        """Pulls an active, non-cooldown standby (failover) key."""
        now = datetime.datetime.utcnow()
        return db.query(models.ApiKey).filter(
            models.ApiKey.user_id == user_id,
            models.ApiKey.is_active == True,
            models.ApiKey.role == "standby",
            (models.ApiKey.cooldown_until == None) | (models.ApiKey.cooldown_until < now)
        ).order_by(models.ApiKey.created_at.asc()).first()
