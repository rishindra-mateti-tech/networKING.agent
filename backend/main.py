import asyncio
import datetime
import html
import httpx
import os
import secrets
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Request, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import DataError

import models
import schemas
from database import engine, Base, get_db
from auth import get_current_user, create_access_token, get_password_hash, verify_password
from parser import (
    parse_pdf_text,
    extract_linkedin_profile_metadata,
    extract_resume_contact_info,
    normalize_linkedin_slug,
)
from orchestrator import QueueOrchestrator
from generator import (
    generate_thread_followup,
    analyze_conversation_screenshot,
    generate_outreach_email,
    answer_analytics_question,
    generate_twin_understanding,
    chat_about_twin_profile,
    validate_api_key,
)
from twin_agent import compile_twin_agent_profile, get_sender_name

from migrate import run_migrations
from config import CORS_ORIGINS, GOOGLE_CLIENT_ID

# Run database schema migrations
run_migrations()

# Initialize Database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="networKING.agent SaaS API", version="1.0.0")


@app.exception_handler(OverflowError)
async def _out_of_range_id_handler(request: Request, exc: OverflowError):
    """
    A path id larger than the database's integer range blows up inside the
    driver while binding the parameter, before the query runs, which surfaces
    to the caller as a 500. No row can ever carry such an id, so the honest
    answer is the same one any other non-existent id gets.
    """
    return JSONResponse(status_code=404, content={"detail": "Not Found"})


@app.exception_handler(DataError)
async def _db_data_error_handler(request: Request, exc: DataError):
    """
    Postgres reports the same out-of-range id as a DataError rather than an
    OverflowError, so the production path needs its own case. Only range
    errors are translated; every other DataError is a genuine fault and is
    re-raised so it stays visible instead of being masked as a 404.
    """
    if "out of range" in str(exc).lower():
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    raise exc


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

def _init_default_settings(db: Session, user_id: int):
    basic_keys = [
        "resume_context", "resume_latex", "github_url",
        "portfolio_url", "linkedin_url", "telegram_token",
        "telegram_chat_id", "telegram_enabled", "slack_webhook_url", "slack_enabled", "pacing_interval_minutes",
        "job_search_status", "target_roles", "learning_goals", "tone_examples",
        "email_client_preference", "twin_understanding", "twin_extra_notes",
        "resume_filename", "contact_email", "contact_phone", "resume_location",
        "custom_links", "tone_presets", "full_name"
    ]
    for key in basic_keys:
        default_val = "15" if key == "pacing_interval_minutes" else ""
        db.add(models.Setting(user_id=user_id, key=key, value=default_val))
    db.commit()


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

    _init_default_settings(db, new_user.id)
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

@app.post("/api/auth/google", response_model=schemas.Token)
def login_with_google(body: schemas.GoogleAuthRequest, db: Session = Depends(get_db)):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google sign-in isn't configured on this server yet")

    try:
        payload = google_id_token.verify_oauth2_token(
            body.credential, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    email = payload.get("email")
    if not email or not payload.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google account has no verified email")

    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        # Google-authenticated accounts never use this password; it just
        # satisfies the column so login()'s local-password path stays unused.
        unusable_password = get_password_hash(secrets.token_urlsafe(32))
        user = models.User(email=email, hashed_password=unusable_password)
        db.add(user)
        db.commit()
        db.refresh(user)
        _init_default_settings(db, user.id)

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

    # Filename is tracked unconditionally so the TwinAgent tab can show what's
    # currently uploaded, e.g. "resume_v3.pdf", instead of a generic checkmark.
    _upsert_setting(db, current_user.id, "resume_filename", file.filename)

    # Auto-fill social/contact links from the resume, but only into settings
    # that are still empty -- never clobber something the user already typed
    # in or already corrected by hand on a prior upload.
    extracted = extract_resume_contact_info(resume_text)
    existing_settings = {
        s.key: s.value for s in db.query(models.Setting).filter(
            models.Setting.user_id == current_user.id
        ).all()
    }
    fill_only_if_empty = {
        "github_url": extracted.get("github_url"),
        "portfolio_url": extracted.get("portfolio_url"),
        "linkedin_url": extracted.get("linkedin_url"),
        "contact_email": extracted.get("email"),
        "contact_phone": extracted.get("phone"),
        "resume_location": extracted.get("location"),
        "full_name": extracted.get("full_name"),
    }
    for key, value in fill_only_if_empty.items():
        if value and not (existing_settings.get(key) or "").strip():
            _upsert_setting(db, current_user.id, key, value)

    db.commit()
    return {
        "message": "Resume uploaded and compiled successfully.",
        "char_count": len(resume_text),
        "detected": extracted,
    }

def _get_active_key_or_400(db: Session, user_id: int) -> models.ApiKey:
    key = db.query(models.ApiKey).filter(
        models.ApiKey.user_id == user_id,
        models.ApiKey.is_active == True
    ).first()
    if not key:
        raise HTTPException(status_code=400, detail="No active API key set. Add a Gemini key under API Key Workers first.")
    return key


def _upsert_setting(db: Session, user_id: int, key: str, value: str):
    setting = db.query(models.Setting).filter(
        models.Setting.user_id == user_id,
        models.Setting.key == key
    ).first()
    if setting:
        setting.value = value
        setting.updated_at = datetime.datetime.utcnow()
    else:
        db.add(models.Setting(user_id=user_id, key=key, value=value))
    db.commit()


@app.post("/api/settings/twin-understanding/generate")
def generate_understanding(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Plays back what the system understands about the user, so a wrong reading
    gets caught here rather than silently shaping every message it writes.
    Stored as plain text in settings.
    """
    api_key_record = _get_active_key_or_400(db, current_user.id)
    summary = generate_twin_understanding(
        api_key=api_key_record.key_value,
        twin_profile=compile_twin_agent_profile(db, current_user.id),
    )
    _upsert_setting(db, current_user.id, "twin_understanding", summary)
    return {"understanding": summary}


@app.post("/api/settings/twin-chat")
def twin_chat(
    payload: schemas.TwinChatMessage,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Conversational way to teach the agent about yourself. Anything durable it
    picks up is appended to twin_extra_notes, so the conversation actually
    changes future output instead of being a throwaway chat.
    """
    api_key_record = _get_active_key_or_400(db, current_user.id)

    result = chat_about_twin_profile(
        api_key=api_key_record.key_value,
        twin_profile=compile_twin_agent_profile(db, current_user.id),
        history=[{"role": t.role, "content": t.content} for t in payload.history],
        message=payload.message,
    )

    if result["learned"]:
        existing = db.query(models.Setting).filter(
            models.Setting.user_id == current_user.id,
            models.Setting.key == "twin_extra_notes"
        ).first()
        prior = (existing.value or "").strip() if existing else ""
        # Plain newline-delimited text, no JSON, to keep it small and readable
        # (and editable by hand in the same textarea as everything else).
        merged = f"{prior}\n- {result['learned']}".strip() if prior else f"- {result['learned']}"
        _upsert_setting(db, current_user.id, "twin_extra_notes", merged)

    return {"reply": result["reply"], "learned": result["learned"]}


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

@app.post("/api/keys/{key_id}/test")
async def test_api_key(key_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Makes one lightweight Gemini call with this stored key to confirm it's actually working right now."""
    key = db.query(models.ApiKey).filter(
        models.ApiKey.id == key_id,
        models.ApiKey.user_id == current_user.id
    ).first()
    if not key:
        raise HTTPException(status_code=404, detail="API Key not found")

    check = await asyncio.to_thread(validate_api_key, key.key_value)
    if check["valid"]:
        return {"message": f"'{key.label or 'This key'}' is working."}
    raise HTTPException(status_code=400, detail=f"'{key.label or 'This key'}' failed: {check['error']}")

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
        connection_count=data.connection_count,
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

# Values that land in name/company when extraction failed rather than because
# they describe anyone. They are shared by every failed upload, so they can
# never be used to decide that two uploads are the same person.
_PLACEHOLDER_IDENTITY_VALUES = {
    "unknown candidate", "unknown", "unknown company", "candidate",
    "n/a", "na", "none", "null", "unnamed", "company", "-", "--",
}


def _is_placeholder_identity(name: Optional[str], company: Optional[str]) -> bool:
    """True when name or company is an extraction-failure placeholder rather than a real value."""
    for value in (name, company):
        if not value or value.strip().lower() in _PLACEHOLDER_IDENTITY_VALUES:
            return True
    return False


def _find_duplicate_connection(db: Session, user_id: int, profile_url: Optional[str], candidate_email: Optional[str], name: Optional[str], company: Optional[str]) -> Optional["models.Connection"]:
    """
    Looks for a Connection already belonging to this user that represents the
    same real person, so a re-uploaded PDF (weeks or months later) refreshes
    their existing pipeline entry instead of creating a disconnected
    duplicate. Tried in order of reliability: LinkedIn profile slug (stable
    across re-exports even when the raw URL string differs), then email,
    then an exact name+company match as a last resort.
    """
    slug = normalize_linkedin_slug(profile_url or "")
    if slug:
        candidates = db.query(models.Connection).filter(
            models.Connection.user_id == user_id,
            models.Connection.profile_url.isnot(None)
        ).all()
        for c in candidates:
            if normalize_linkedin_slug(c.profile_url) == slug:
                return c

    if candidate_email:
        match = db.query(models.Connection).filter(
            models.Connection.user_id == user_id,
            models.Connection.candidate_email == candidate_email
        ).first()
        if match:
            return match

    # The name+company fallback is only safe when the name actually identifies
    # a person. When a PDF fails to parse, every such upload lands on the same
    # placeholder ("Unknown Candidate"), so matching on it would merge two
    # completely different people into one record, overwriting the first
    # person's details with the second's while keeping the first person's
    # pipeline history. Slug and email matches above are exact identifiers and
    # stay trustworthy; this one is a heuristic and has to be held back.
    if name and company and not _is_placeholder_identity(name, company):
        match = db.query(models.Connection).filter(
            models.Connection.user_id == user_id,
            func.lower(models.Connection.name) == name.strip().lower(),
            func.lower(models.Connection.company) == company.strip().lower(),
        ).first()
        if match:
            return match

    return None


@app.post("/api/connections/upload-profile")
async def upload_linkedin_profile(
    file: Optional[UploadFile] = File(None),
    screenshot: Optional[UploadFile] = File(None),
    posts_image: Optional[UploadFile] = File(None),
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
    current_company_years_experience = None
    pdf_filename = None
    candidate_email = None

    if file:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF profile exports are supported.")
        content = await file.read()
        pdf_filename = file.filename
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
            current_company_years_experience = extracted.get("current_company_years_experience")
            if not profile_url:
                profile_url = extracted.get("profile_url")
            candidate_email = extracted.get("email")
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

    posts_screenshot_path = None
    if posts_image:
        import uuid
        ext = os.path.splitext(posts_image.filename)[1] or ".png"
        filename = f"{uuid.uuid4()}{ext}"
        filepath = os.path.join(UPLOADS_DIR, filename)
        try:
            with open(filepath, "wb") as f:
                content = await posts_image.read()
                f.write(content)
            posts_screenshot_path = filepath
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save posts screenshot: {str(e)}")

    if not name:
        raise HTTPException(status_code=400, detail="Candidate Name is required.")

    existing = _find_duplicate_connection(db, current_user.id, profile_url, candidate_email, name, company)

    if existing:
        # Same person, re-uploaded later: refresh the raw profile fields but
        # never touch pipeline state (status, star, sent/replied timestamps,
        # generated drafts, AI analysis) -- that history belongs to this
        # person regardless of how stale their title/company text was.
        if screenshot_path and existing.screenshot_path and os.path.exists(existing.screenshot_path):
            try:
                os.remove(existing.screenshot_path)
            except OSError as e:
                print(f"[UPLOAD] Failed to remove stale screenshot {existing.screenshot_path}: {e}")
        if posts_screenshot_path and existing.posts_screenshot_path and os.path.exists(existing.posts_screenshot_path):
            try:
                os.remove(existing.posts_screenshot_path)
            except OSError as e:
                print(f"[UPLOAD] Failed to remove stale posts screenshot {existing.posts_screenshot_path}: {e}")

        existing.name = name
        existing.current_title = current_title or existing.current_title
        existing.company = company or existing.company
        existing.location = location or existing.location
        if connection_count_val is not None:
            existing.connection_count = connection_count_val
        if years_experience:
            existing.years_experience = years_experience
        if current_company_years_experience is not None:
            existing.current_company_years_experience = current_company_years_experience
        if profile_text:
            existing.profile_text = profile_text
        if posts:
            existing.posts_text = posts
        if profile_url:
            existing.profile_url = profile_url
        if screenshot_path:
            existing.screenshot_path = screenshot_path
        if posts_screenshot_path:
            existing.posts_screenshot_path = posts_screenshot_path
        if hiring_badge_status:
            existing.hiring_badge_status = hiring_badge_status
        if pdf_filename:
            existing.pdf_filename = pdf_filename
        if candidate_email:
            existing.candidate_email = candidate_email

        needs_analysis = existing.status in ("pending", "failed")
        if needs_analysis:
            existing.status = "pending"
            existing.error_message = None

        db.commit()
        db.refresh(existing)

        if needs_analysis:
            QueueOrchestrator().trigger_now(current_user.id)

        when = existing.sent_at or existing.replied_at or existing.created_at
        payload = schemas.ConnectionOut.model_validate(existing).model_dump(mode="json")
        payload["duplicate_detected"] = True
        payload["duplicate_message"] = (
            f"Already in your pipeline (status: {existing.status}). "
            f"Added {existing.created_at.date().isoformat()}"
            + (f", last activity {when.date().isoformat()}" if when else "")
            + ". Profile details refreshed from this PDF."
        )
        return payload

    new_conn = models.Connection(
        user_id=current_user.id,
        name=name,
        current_title=current_title,
        company=company,
        location=location,
        connection_count=connection_count_val,
        years_experience=years_experience,
        current_company_years_experience=current_company_years_experience,
        profile_text=profile_text,
        posts_text=posts,
        profile_url=profile_url,
        screenshot_path=screenshot_path,
        posts_screenshot_path=posts_screenshot_path,
        status="pending",
        is_starred=False,
        hiring_badge_status=hiring_badge_status,
        pdf_filename=pdf_filename,
        candidate_email=candidate_email
    )
    db.add(new_conn)
    db.commit()
    db.refresh(new_conn)
    # Auto-trigger queue worker to process this connection immediately
    QueueOrchestrator().trigger_now(current_user.id)
    payload = schemas.ConnectionOut.model_validate(new_conn).model_dump(mode="json")
    payload["duplicate_detected"] = False
    return payload

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
    # Stamp the timestamp once, at the moment of transition -- updated_at gets
    # overwritten by every later status change, so it can't be used for
    # reply-time analytics the way these dedicated fields can.
    if payload.status == "sent" and conn.sent_at is None:
        conn.sent_at = datetime.datetime.utcnow()
    if payload.status == "replied" and conn.replied_at is None:
        conn.replied_at = datetime.datetime.utcnow()
        # A reply is the most valuable signal in the pipeline, so surface
        # it automatically instead of relying on the user to star it.
        conn.is_starred = True
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
        if conn.replied_at is None:
            conn.replied_at = datetime.datetime.utcnow()
            conn.is_starred = True
    elif log_data.sender == "user" and conn.status == "replied":
        conn.status = "follow_up"

    db.commit()
    db.refresh(new_log)
    return new_log

@app.post("/api/connections/{connection_id}/logs/upload-screenshot", response_model=schemas.InteractionLogOut)
async def upload_conversation_screenshot(
    connection_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Uploads a screenshot of a real conversation, logs it in the thread, and runs
    a vision-based agent to judge how the conversation is actually going (genuinely
    interested vs. politely vague vs. not interested), with a recommended next step.
    """
    conn = db.query(models.Connection).filter(models.Connection.id == connection_id, models.Connection.user_id == current_user.id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    api_key_record = db.query(models.ApiKey).filter(
        models.ApiKey.user_id == current_user.id,
        models.ApiKey.is_active == True
    ).first()
    if not api_key_record:
        raise HTTPException(status_code=400, detail="No active API key set for screenshot analysis.")

    import uuid
    ext = os.path.splitext(file.filename)[1] or ".png"
    filename = f"{uuid.uuid4()}{ext}"
    filepath = os.path.join(UPLOADS_DIR, filename)
    try:
        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save screenshot: {str(e)}")

    new_log = models.InteractionLog(
        connection_id=connection_id,
        user_id=current_user.id,
        sender="connection",
        message="[Conversation screenshot uploaded]",
        screenshot_path=filepath
    )
    db.add(new_log)

    logs = db.query(models.InteractionLog).filter(
        models.InteractionLog.connection_id == connection_id
    ).order_by(models.InteractionLog.created_at.asc()).all()
    thread_history = [{"sender": l.sender, "message": l.message} for l in logs]

    analysis = analyze_conversation_screenshot(
        api_key=api_key_record.key_value,
        candidate_name=conn.name,
        screenshot_path=filepath,
        thread_history=thread_history,
        sender_name=get_sender_name(db, current_user.id)
    )
    conn.conversation_verdict = analysis["verdict"]
    conn.conversation_verdict_reason = analysis["reason"]
    conn.conversation_recommended_action = analysis["recommended_action"]
    conn.status = "replied"
    if conn.replied_at is None:
        conn.replied_at = datetime.datetime.utcnow()
        conn.is_starred = True

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
        user_intent=user_intent,
        sender_name=get_sender_name(db, current_user.id)
    )

    return {"suggested_reply": reply_text}


# --- ANALYTICS ---

@app.get("/api/analytics/overview")
def get_analytics_overview(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Aggregate view over every outreach target: pipeline breakdown, seniority mix,
    reply-time buckets, and a lightweight per-person list so the frontend can filter
    by connection-count range, seniority, or experience without extra round trips.
    """
    import json as j

    connections = db.query(models.Connection).filter(models.Connection.user_id == current_user.id).all()

    by_status: dict = {}
    by_seniority: dict = {}
    experienced_10_plus = 0
    reply_buckets = {"within_a_day": 0, "within_a_week": 0, "longer_than_a_week": 0, "no_reply_yet": 0}
    people = []

    now = datetime.datetime.utcnow()

    for c in connections:
        by_status[c.status] = by_status.get(c.status, 0) + 1

        seniority = "Unknown"
        try:
            p_intel = j.loads(c.profile_intelligence or "{}")
            seniority = p_intel.get("seniority") or "Unknown"
        except Exception:
            pass
        by_seniority[seniority] = by_seniority.get(seniority, 0) + 1

        if (c.years_experience or 0) >= 10:
            experienced_10_plus += 1

        if c.sent_at:
            if c.replied_at:
                delta = c.replied_at - c.sent_at
                if delta.total_seconds() <= 86400:
                    reply_buckets["within_a_day"] += 1
                elif delta.total_seconds() <= 7 * 86400:
                    reply_buckets["within_a_week"] += 1
                else:
                    reply_buckets["longer_than_a_week"] += 1
            elif (now - c.sent_at).total_seconds() > 7 * 86400:
                reply_buckets["no_reply_yet"] += 1

        people.append({
            "id": c.id,
            "name": c.name,
            "company": c.company,
            "current_title": c.current_title,
            "status": c.status,
            "seniority": seniority,
            "years_experience": c.years_experience,
            "current_company_years_experience": c.current_company_years_experience,
            "connection_count": c.connection_count,
            "networking_score": c.networking_score,
            "reply_probability": c.reply_probability,
            "conversation_verdict": c.conversation_verdict,
            "conversation_verdict_reason": c.conversation_verdict_reason,
            "conversation_recommended_action": c.conversation_recommended_action,
            "sent_at": c.sent_at,
            "replied_at": c.replied_at,
        })

    # Reply score: what share of everything actually sent came back with a reply.
    # Only counts connections that reached "sent", since anything still sitting in
    # the queue was never given the chance to reply and would unfairly drag the
    # rate down.
    sent_count = sum(1 for c in connections if c.sent_at is not None)
    replied_count = sum(1 for c in connections if c.replied_at is not None)
    reply_rate = round((replied_count / sent_count) * 100, 1) if sent_count else None

    # When the rate is weak, surface who actually did reply so the pattern is
    # visible, plus the highest-scoring people never contacted yet.
    who_replied = [
        {"id": c.id, "name": c.name, "company": c.company, "profile_url": c.profile_url,
         "seniority": (j.loads(c.profile_intelligence or "{}").get("seniority") if c.profile_intelligence else None)}
        for c in connections if c.replied_at is not None
    ][:10]

    untouched = [c for c in connections if c.sent_at is None and c.status == "completed"]
    untouched.sort(key=lambda c: (c.networking_score or 0), reverse=True)
    suggested_targets = [
        {"id": c.id, "name": c.name, "company": c.company, "profile_url": c.profile_url,
         "networking_score": c.networking_score, "reply_probability": c.reply_probability}
        for c in untouched[:5]
    ]

    return {
        "total": len(connections),
        "by_status": by_status,
        "by_seniority": by_seniority,
        "experienced_10_plus": experienced_10_plus,
        "reply_time_buckets": reply_buckets,
        "reply_score": {
            "sent_count": sent_count,
            "replied_count": replied_count,
            "reply_rate": reply_rate,
            "who_replied": who_replied,
            "suggested_targets": suggested_targets,
        },
        "people": people,
    }


@app.post("/api/analytics/ask")
def ask_analytics(
    payload: schemas.AnalyticsQuestion,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Free-form question answered by Gemini over the user's own outreach data."""
    import json as j

    api_key_record = db.query(models.ApiKey).filter(
        models.ApiKey.user_id == current_user.id,
        models.ApiKey.is_active == True
    ).first()
    if not api_key_record:
        raise HTTPException(status_code=400, detail="No active API key set. Add a Gemini key under API Key Workers first.")

    connections = db.query(models.Connection).filter(models.Connection.user_id == current_user.id).all()

    rows = []
    for c in connections:
        seniority = "Unknown"
        try:
            seniority = j.loads(c.profile_intelligence or "{}").get("seniority") or "Unknown"
        except Exception:
            pass
        rows.append(
            f"- {c.name} | {c.current_title or 'unknown title'} at {c.company or 'unknown company'} | "
            f"seniority={seniority} | total_experience={c.years_experience}yrs | "
            f"experience_at_current_company={c.current_company_years_experience if c.current_company_years_experience is not None else 'unknown'}yrs | "
            f"connections={c.connection_count} | "
            f"status={c.status} | networking_score={c.networking_score} | reply_probability={c.reply_probability} | "
            f"sent={c.sent_at.isoformat() if c.sent_at else 'never'} | "
            f"replied={c.replied_at.isoformat() if c.replied_at else 'no'} | "
            f"conversation_verdict={c.conversation_verdict or 'not analyzed'}"
        )

    sent_count = sum(1 for c in connections if c.sent_at is not None)
    replied_count = sum(1 for c in connections if c.replied_at is not None)
    context = (
        f"Total people added: {len(connections)}\n"
        f"Total actually sent: {sent_count}\n"
        f"Total that replied: {replied_count}\n"
        f"Reply rate: {round((replied_count / sent_count) * 100, 1) if sent_count else 'n/a'}%\n"
        f"Today's date: {datetime.datetime.utcnow().date().isoformat()}\n\n"
        f"PER PERSON:\n" + "\n".join(rows)
    )

    answer = answer_analytics_question(
        api_key=api_key_record.key_value,
        question=payload.question,
        analytics_context=context
    )
    return {"answer": answer}


@app.post("/api/connections/{connection_id}/generate-email")
def generate_email_draft(
    connection_id: int,
    body: schemas.EmailDraftRequest = schemas.EmailDraftRequest(),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Writes a real outreach email (subject + body) for this person, in one of
    a few real-world situations the user picks (cold, already messaged and
    waiting, already messaged and replied), plus optional style modifiers
    (referral ask, punchier opener) that layer on top.
    """
    conn = db.query(models.Connection).filter(
        models.Connection.id == connection_id,
        models.Connection.user_id == current_user.id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    api_key_record = db.query(models.ApiKey).filter(
        models.ApiKey.user_id == current_user.id,
        models.ApiKey.is_active == True
    ).first()
    if not api_key_record:
        raise HTTPException(status_code=400, detail="No active API key set for email generation.")

    settings_records = db.query(models.Setting).filter(models.Setting.user_id == current_user.id).all()
    settings = {s.key: s.value for s in settings_records if s.value}

    conversation_context = ""
    if body.contact_status == "messaged_replied":
        logs = db.query(models.InteractionLog).filter(
            models.InteractionLog.connection_id == connection_id
        ).order_by(models.InteractionLog.created_at.asc()).all()
        transcript_lines = [
            f"{'You' if log.sender == 'user' else conn.name}: {log.message}"
            for log in logs
            if log.message and log.message != "[Conversation screenshot uploaded]"
        ]
        if conn.conversation_verdict:
            transcript_lines.append(
                f"[Read on how this is going: {conn.conversation_verdict}"
                + (f", {conn.conversation_verdict_reason}" if conn.conversation_verdict_reason else "")
                + "]"
            )
        conversation_context = "\n".join(transcript_lines) or "No transcript text was saved, only a screenshot. Write generally warm and continuing, without quoting specifics you don't have."

    result = generate_outreach_email(
        api_key=api_key_record.key_value,
        twin_profile=compile_twin_agent_profile(db, current_user.id),
        candidate_name=conn.name,
        candidate_email=conn.candidate_email or "",
        candidate_profile=conn.profile_text or "",
        bridge_data={
            "profile_intelligence": conn.profile_intelligence,
            "company_intelligence": conn.company_intelligence,
            "relationship_strategy": conn.relationship_strategy,
            "personalization_data": conn.personalization_data,
            "context_summary": conn.context_summary,
        },
        tone_examples=settings.get("tone_examples", ""),
        sender_name=get_sender_name(db, current_user.id),
        contact_status=body.contact_status,
        style_modifiers=body.style_modifiers,
        conversation_context=conversation_context,
        length=body.length,
        custom_instructions=body.custom_instructions,
    )

    conn.generated_email_subject = result["subject"]
    conn.generated_email_body = result["body"]
    db.commit()

    return {"subject": result["subject"], "body": result["body"]}
