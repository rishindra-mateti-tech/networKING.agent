import datetime
import html
import httpx
import os
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import models
import schemas
from database import engine, Base, get_db
from auth import get_current_user, create_access_token, get_password_hash, verify_password
from parser import parse_pdf_text, extract_linkedin_profile_metadata
from orchestrator import QueueOrchestrator
from generator import generate_thread_followup
from twin_agent import compile_twin_agent_profile

from migrate import run_migrations
from config import CORS_ORIGINS

# Run database schema migrations
run_migrations()

# Initialize Database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="networKING.agent SaaS API", version="1.0.0")

@app.get("/health")
def health_check():
    """Cheap, no-DB-touch endpoint for uptime pingers to keep a free-tier host from sleeping."""
    return {"status": "ok"}

# Mount uploads directory to serve screenshots static files. Overridable so a
# deployed instance can point at a persistent volume instead of the working
# directory, which would otherwise be wiped on every redeploy.
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# CORS middleware — scoped to CORS_ORIGINS (backend/.env), defaults to the local Next.js dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup and Shutdown Lifecycle Hooks
@app.on_event("startup")
async def startup_event():
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    QueueOrchestrator().start()
    # Sync workers for all existing users at startup
    db = next(get_db())
    try:
        users = db.query(models.User).all()
        for user in users:
            await QueueOrchestrator().sync_user_workers(user.id)
    except Exception as e:
        print(f"[STARTUP] Error syncing workers: {e}")
    finally:
        db.close()

@app.on_event("shutdown")
def shutdown_event():
    QueueOrchestrator().stop()


# --- ORCHESTRATOR CONTROL ENDPOINTS ---

@app.post("/api/orchestrator/trigger")
async def trigger_queue_processing(current_user: models.User = Depends(get_current_user)):
    """Manually trigger immediate queue processing for the current user."""
    orchestrator = QueueOrchestrator()
    orchestrator.trigger_now(current_user.id)
    # Also sync workers in case keys were added/changed
    await orchestrator.sync_user_workers(current_user.id)
    return {"message": "Queue processing triggered. Workers are waking up now."}

@app.get("/api/orchestrator/status")
def get_queue_status(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Returns pipeline queue counts for the current user."""
    pending = db.query(models.Connection).filter(
        models.Connection.user_id == current_user.id,
        models.Connection.status == "pending"
    ).count()
    processing = db.query(models.Connection).filter(
        models.Connection.user_id == current_user.id,
        models.Connection.status == "processing"
    ).count()
    completed = db.query(models.Connection).filter(
        models.Connection.user_id == current_user.id,
        models.Connection.status == "completed"
    ).count()
    failed = db.query(models.Connection).filter(
        models.Connection.user_id == current_user.id,
        models.Connection.status == "failed"
    ).count()
    active_keys = db.query(models.ApiKey).filter(
        models.ApiKey.user_id == current_user.id,
        models.ApiKey.is_active == True
    ).count()
    return {
        "pending": pending,
        "processing": processing,
        "completed": completed,
        "failed": failed,
        "active_keys": active_keys
    }


# --- AUTH ENDPOINTS ---

@app.post("/api/auth/register", response_model=schemas.UserOut)
def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pwd = get_password_hash(user_data.password)
    new_user = models.User(email=user_data.email, hashed_password=hashed_pwd)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Initialize basic settings keys for this user
    basic_keys = [
        "resume_context", "resume_latex", "github_url",
        "portfolio_url", "linkedin_url", "telegram_token",
        "telegram_chat_id", "slack_webhook_url", "pacing_interval_minutes",
        "job_search_status", "target_roles", "learning_goals", "tone_examples"
    ]
    for key in basic_keys:
        default_val = "15" if key == "pacing_interval_minutes" else ""
        setting = models.Setting(user_id=new_user.id, key=key, value=default_val)
        db.add(setting)
    db.commit()
    
    return new_user

@app.post("/api/auth/login", response_model=schemas.Token)
def login(login_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == login_data.email).first()
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.email, "user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


# --- SETTINGS / TWINAGENT ENDPOINTS ---

@app.get("/api/settings", response_model=List[schemas.SettingOut])
def get_settings(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Setting).filter(models.Setting.user_id == current_user.id).all()

@app.post("/api/settings/batch", response_model=List[schemas.SettingOut])
async def update_settings_batch(payload: schemas.SettingUpdateBatch, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    updated_records = []
    pacing_changed = False
    
    for item in payload.settings:
        setting = db.query(models.Setting).filter(
            models.Setting.user_id == current_user.id,
            models.Setting.key == item.key
        ).first()
        
        if setting:
            setting.value = item.value
            setting.updated_at = datetime.datetime.utcnow()
        else:
            setting = models.Setting(user_id=current_user.id, key=item.key, value=item.value)
            db.add(setting)
            
        if item.key == "pacing_interval_minutes":
            pacing_changed = True
            
        db.commit()
        db.refresh(setting)
        updated_records.append(setting)
        
    return updated_records

@app.post("/api/settings/upload-resume")
async def upload_resume(file: UploadFile = File(...), current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are supported.")
        
    content = await file.read()
    try:
        resume_text = parse_pdf_text(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse resume PDF: {str(e)}")
        
    setting = db.query(models.Setting).filter(
        models.Setting.user_id == current_user.id,
        models.Setting.key == "resume_context"
    ).first()
    
    if setting:
        setting.value = resume_text
        setting.updated_at = datetime.datetime.utcnow()
    else:
        setting = models.Setting(user_id=current_user.id, key="resume_context", value=resume_text)
        db.add(setting)
        
    db.commit()
    return {"message": "Resume uploaded and compiled successfully.", "char_count": len(resume_text)}

@app.post("/api/settings/test-telegram")
async def test_telegram_setting(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings_records = db.query(models.Setting).filter(models.Setting.user_id == current_user.id).all()
    settings = {s.key: s.value for s in settings_records if s.value}
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()
    
    if not token or not chat_id:
        raise HTTPException(status_code=400, detail="Telegram bot token and Chat ID must be configured in Settings first.")
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": "🎉 <b>networKING.agent Telegram Notification Test!</b>\n\nYour Telegram bot is successfully connected and ready to send instant outreach alerts.",
        "parse_mode": "HTML"
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=10.0)
            if res.status_code == 200:
                return {"message": "Test notification sent successfully to your Telegram chat!"}
            else:
                data = res.json()
                detail_msg = data.get("description", res.text)
                raise HTTPException(status_code=400, detail=f"Telegram API Error ({res.status_code}): {detail_msg}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reach Telegram API: {str(e)}")

@app.post("/api/settings/test-slack")
async def test_slack_setting(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    settings_records = db.query(models.Setting).filter(models.Setting.user_id == current_user.id).all()
    settings = {s.key: s.value for s in settings_records if s.value}
    webhook_url = settings.get("slack_webhook_url", "").strip()

    if not webhook_url:
        raise HTTPException(status_code=400, detail="Slack Incoming Webhook URL must be configured in Settings first.")

    payload = {
        "text": ":tada: *networKING.agent Slack Notification Test!*\n\nYour Slack webhook is successfully connected and ready to send instant outreach alerts."
    }
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(webhook_url, json=payload, timeout=10.0)
            if res.status_code == 200:
                return {"message": "Test notification sent successfully to your Slack channel!"}
            else:
                raise HTTPException(status_code=400, detail=f"Slack API Error ({res.status_code}): {res.text}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reach Slack: {str(e)}")


# --- API KEYS ENDPOINTS ---

@app.get("/api/keys", response_model=List[schemas.ApiKeyOut])
def get_api_keys(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.ApiKey).filter(models.ApiKey.user_id == current_user.id).all()

@app.post("/api/keys", response_model=schemas.ApiKeyOut)
async def create_api_key(key_data: schemas.ApiKeyCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_key = models.ApiKey(
        user_id=current_user.id,
        key_value=key_data.key_value,
        role=key_data.role,
        label=key_data.label or f"{key_data.role.capitalize()} Key",
        is_active=True
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    
    # Sync worker threads to reflect the key change
    await QueueOrchestrator().sync_user_workers(current_user.id)
    return new_key

@app.put("/api/keys/{key_id}/toggle", response_model=schemas.ApiKeyOut)
async def toggle_api_key(key_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = db.query(models.ApiKey).filter(
        models.ApiKey.id == key_id,
        models.ApiKey.user_id == current_user.id
    ).first()
    
    if not key:
        raise HTTPException(status_code=404, detail="API Key not found")
        
    key.is_active = not key.is_active
    if key.is_active:
        key.cooldown_until = None
    db.commit()
    db.refresh(key)
    
    await QueueOrchestrator().sync_user_workers(current_user.id)
    return key

@app.delete("/api/keys/{key_id}")
async def delete_api_key(key_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = db.query(models.ApiKey).filter(
        models.ApiKey.id == key_id,
        models.ApiKey.user_id == current_user.id
    ).first()
    
    if not key:
        raise HTTPException(status_code=404, detail="API Key not found")
        
    db.delete(key)
    db.commit()
    
    await QueueOrchestrator().sync_user_workers(current_user.id)
    return {"message": "API key deleted successfully."}


# --- CONNECTIONS & OUTREACH ENDPOINTS ---

@app.get("/api/connections", response_model=List[schemas.ConnectionOut])
def get_connections(
    search: Optional[str] = None,
    status: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(models.Connection).filter(models.Connection.user_id == current_user.id)
    
    if search:
        query = query.filter(
            (models.Connection.name.ilike(f"%{search}%")) |
            (models.Connection.company.ilike(f"%{search}%")) |
            (models.Connection.current_title.ilike(f"%{search}%"))
        )
    if status:
        query = query.filter(models.Connection.status == status)
        
    # Sort Starred connections first, then created_at order
    return query.order_by(models.Connection.is_starred.desc(), models.Connection.created_at.desc()).all()

@app.get("/api/connections/{connection_id}", response_model=schemas.ConnectionOut)
def get_connection(connection_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    connection = db.query(models.Connection).filter(
        models.Connection.id == connection_id,
        models.Connection.user_id == current_user.id
    ).first()
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    return connection

@app.post("/api/connections", response_model=schemas.ConnectionOut)
async def create_connection(data: schemas.ConnectionCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    new_conn = models.Connection(
        user_id=current_user.id,
        name=data.name,
        current_title=data.current_title,
        company=data.company,
        location=data.location,
        connection_count=data.connection_count or 0,
        years_experience=data.years_experience or 0.0,
        profile_text=data.profile_text,
        posts_text=data.posts_text,
        profile_url=data.profile_url,
        status="pending",
        is_starred=False
    )
    db.add(new_conn)
    db.commit()
    db.refresh(new_conn)
    # Auto-trigger queue worker to process this connection immediately
    QueueOrchestrator().trigger_now(current_user.id)
    return new_conn

@app.post("/api/connections/upload-profile", response_model=schemas.ConnectionOut)
async def upload_linkedin_profile(
    file: Optional[UploadFile] = File(None),
    screenshot: Optional[UploadFile] = File(None),
    posts: Optional[str] = Form(None),
    profile_url: Optional[str] = Form(None),
    name: Optional[str] = Form(None),
    current_title: Optional[str] = Form(None),
    company: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    connection_count: Optional[int] = Form(None),
    hiring_badge_status: Optional[str] = Form(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    profile_text = None
    connection_count_val = connection_count
    years_experience = 0.0
    
    if file:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF profile exports are supported.")
        content = await file.read()
        try:
            profile_text = parse_pdf_text(content)
            extracted = extract_linkedin_profile_metadata(profile_text)
            name = name or extracted["name"]
            current_title = current_title or extracted["current_title"]
            company = company or extracted["company"]
            location = location or extracted["location"]
            if connection_count_val is None:
                connection_count_val = extracted["connection_count"]
            years_experience = extracted["years_experience"]
            if not profile_url:
                profile_url = extracted.get("profile_url")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to parse profile PDF: {str(e)}")
            
    screenshot_path = None
    if screenshot:
        import uuid
        ext = os.path.splitext(screenshot.filename)[1] or ".png"
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        try:
            with open(filepath, "wb") as f:
                content = await screenshot.read()
                f.write(content)
            screenshot_path = filepath
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save screenshot: {str(e)}")

    if not name:
        raise HTTPException(status_code=400, detail="Candidate Name is required.")

    new_conn = models.Connection(
        user_id=current_user.id,
        name=name,
        current_title=current_title,
        company=company,
        location=location,
        connection_count=connection_count_val or 0,
        years_experience=years_experience,
        profile_text=profile_text,
        posts_text=posts,
        profile_url=profile_url,
        screenshot_path=screenshot_path,
        status="pending",
        is_starred=False,
        hiring_badge_status=hiring_badge_status
    )
    db.add(new_conn)
    db.commit()
    db.refresh(new_conn)
    # Auto-trigger queue worker to process this connection immediately
    QueueOrchestrator().trigger_now(current_user.id)
    return new_conn

@app.put("/api/connections/{connection_id}/status", response_model=schemas.ConnectionOut)
def update_connection_status(connection_id: int, payload: schemas.ConnectionUpdateStatus, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(models.Connection).filter(
        models.Connection.id == connection_id,
        models.Connection.user_id == current_user.id
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    # Validation status strings
    valid_statuses = ["pending", "processing", "completed", "failed", "replied", "follow_up", "sent", "interview", "closed"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status value")
        
    conn.status = payload.status
    db.commit()
    db.refresh(conn)
    return conn

@app.put("/api/connections/{connection_id}/star", response_model=schemas.ConnectionOut)
def toggle_connection_star(connection_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(models.Connection).filter(
        models.Connection.id == connection_id,
        models.Connection.user_id == current_user.id
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    conn.is_starred = not conn.is_starred
    db.commit()
    db.refresh(conn)
    return conn

@app.put("/api/connections/{connection_id}/select-variant", response_model=schemas.ConnectionOut)
def select_outreach_variant(connection_id: int, variant: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(models.Connection).filter(
        models.Connection.id == connection_id,
        models.Connection.user_id == current_user.id
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    if variant not in ["short", "warm", "tech", "mixed", "referral", "coffee", "technical", "relationship", "featured"]:
        raise HTTPException(status_code=400, detail="Invalid variant. Must be short, warm, tech, mixed, referral, coffee, technical, relationship, or featured")
        
    conn.selected_variant = variant
    db.commit()
    db.refresh(conn)
    return conn


@app.delete("/api/connections/{connection_id}")
def delete_connection(connection_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = db.query(models.Connection).filter(
        models.Connection.id == connection_id,
        models.Connection.user_id == current_user.id
    ).first()
    
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    if conn.screenshot_path and os.path.exists(conn.screenshot_path):
        try:
            os.remove(conn.screenshot_path)
        except OSError as e:
            print(f"[DELETE] Failed to remove screenshot file {conn.screenshot_path}: {e}")

    db.delete(conn)
    db.commit()
    return {"message": "Connection deleted successfully."}


# --- INTERACTION THREAD LOGS ---

@app.get("/api/connections/{connection_id}/logs", response_model=List[schemas.InteractionLogOut])
def get_interaction_logs(connection_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Verify ownership
    conn = db.query(models.Connection).filter(models.Connection.id == connection_id, models.Connection.user_id == current_user.id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    return db.query(models.InteractionLog).filter(
        models.InteractionLog.connection_id == connection_id,
        models.InteractionLog.user_id == current_user.id
    ).order_by(models.InteractionLog.created_at.asc()).all()

@app.post("/api/connections/{connection_id}/logs", response_model=schemas.InteractionLogOut)
def create_interaction_log(connection_id: int, log_data: schemas.InteractionLogCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Verify ownership
    conn = db.query(models.Connection).filter(models.Connection.id == connection_id, models.Connection.user_id == current_user.id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    new_log = models.InteractionLog(
        connection_id=connection_id,
        user_id=current_user.id,
        sender=log_data.sender,
        message=log_data.message
    )
    db.add(new_log)
    
    # Auto-advance pipeline status when adding log replies
    if log_data.sender == "connection":
        conn.status = "replied"
    elif log_data.sender == "user" and conn.status == "replied":
        conn.status = "follow_up"
        
    db.commit()
    db.refresh(new_log)
    return new_log

@app.post("/api/connections/{connection_id}/generate-reply")
def generate_followup_suggestion(
    connection_id: int,
    user_intent: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify ownership
    conn = db.query(models.Connection).filter(models.Connection.id == connection_id, models.Connection.user_id == current_user.id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
        
    # Compile TwinAgent profile
    twin_profile = compile_twin_agent_profile(db, current_user.id)
    
    # Retrieve active key
    api_key_record = db.query(models.ApiKey).filter(
        models.ApiKey.user_id == current_user.id,
        models.ApiKey.is_active == True
    ).first()
    
    if not api_key_record:
        raise HTTPException(status_code=400, detail="No active API key set for prompt generation.")
        
    # Get thread log
    logs = db.query(models.InteractionLog).filter(
        models.InteractionLog.connection_id == connection_id
    ).order_by(models.InteractionLog.created_at.asc()).all()
    
    thread_history = [{"sender": l.sender, "message": l.message} for l in logs]
    
    # Fallback to include the selected generated outreach message as the outbox start if no user logs exist yet
    if not thread_history and conn.selected_variant:
        variant_text = {
            "short": conn.generated_outreach_short,
            "warm": conn.generated_outreach_warm,
            "tech": conn.generated_outreach_tech,
            "mixed": conn.generated_outreach_mixed,
            "referral": conn.generated_outreach_referral,
            "coffee": conn.generated_outreach_coffee,
            "technical": conn.generated_outreach_technical,
            "relationship": conn.generated_outreach_relationship,
            "featured": conn.generated_outreach_featured
        }.get(conn.selected_variant)
        if variant_text:
            thread_history.append({"sender": "user", "message": variant_text})
            
    reply_text = generate_thread_followup(
        api_key=api_key_record.key_value,
        twin_profile=twin_profile,
        candidate_profile=conn.profile_text or "",
        thread_history=thread_history,
        user_intent=user_intent
    )
    
    return {"suggested_reply": reply_text}
