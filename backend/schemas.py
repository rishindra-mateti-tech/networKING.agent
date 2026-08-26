from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

# --- Auth Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class GoogleAuthRequest(BaseModel):
    credential: str

class UserOut(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    user_id: Optional[int] = None

# --- Connection Schemas ---
class ConnectionCreate(BaseModel):
    name: str
    current_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    connection_count: Optional[int] = None
    years_experience: Optional[float] = 0.0
    profile_text: Optional[str] = None
    posts_text: Optional[str] = None
    profile_url: Optional[str] = None

class ConnectionUpdateStatus(BaseModel):
    status: str

class ConnectionOut(BaseModel):
    id: int
    user_id: int
    name: str
    current_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    connection_count: Optional[int] = None
    years_experience: float
    current_company_years_experience: Optional[float] = None
    profile_text: Optional[str] = None
    posts_text: Optional[str] = None
    status: str
    is_starred: bool
    why_person: Optional[str] = None
    bridge: Optional[str] = None
    best_angle: Optional[str] = None
    generated_outreach_short: Optional[str] = None
    generated_outreach_warm: Optional[str] = None
    generated_outreach_tech: Optional[str] = None
    generated_outreach_mixed: Optional[str] = None
    
    generated_outreach_referral: Optional[str] = None
    generated_outreach_coffee: Optional[str] = None
    generated_outreach_technical: Optional[str] = None
    generated_outreach_relationship: Optional[str] = None
    generated_outreach_featured: Optional[str] = None
    
    selected_variant: Optional[str] = None
    hiring_badge_status: Optional[str] = None
    profile_url: Optional[str] = None

    screenshot_path: Optional[str] = None
    posts_screenshot_path: Optional[str] = None

    networking_score: Optional[float] = None
    reply_probability: Optional[float] = None
    hiring_probability_score: Optional[str] = None
    is_decision_maker: Optional[str] = None
    referral_potential: Optional[str] = None
    networking_difficulty: Optional[str] = None
    conversation_starter: Optional[str] = None
    avoid_points: Optional[str] = None
    best_message_type: Optional[str] = None
    
    profile_intelligence: Optional[str] = None
    company_intelligence: Optional[str] = None
    relationship_strategy: Optional[str] = None
    personalization_data: Optional[str] = None
    context_summary: Optional[str] = None
    error_message: Optional[str] = None
    sent_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    pdf_filename: Optional[str] = None
    candidate_email: Optional[str] = None
    generated_email_subject: Optional[str] = None
    generated_email_body: Optional[str] = None
    conversation_verdict: Optional[str] = None
    conversation_verdict_reason: Optional[str] = None
    conversation_recommended_action: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- API Key Schemas ---
class ApiKeyCreate(BaseModel):
    key_value: str
    role: str = "primary" # 'primary' or 'standby'
    label: Optional[str] = None

class ApiKeyOut(BaseModel):
    id: int
    user_id: int
    role: str
    is_active: bool
    cooldown_until: Optional[datetime] = None
    label: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

# --- Setting Schemas ---
class SettingCreate(BaseModel):
    key: str
    value: Optional[str] = None

class SettingUpdateBatch(BaseModel):
    settings: List[SettingCreate]

class AnalyticsQuestion(BaseModel):
    question: str

class TwinChatTurn(BaseModel):
    role: str          # 'user' or 'agent'
    content: str

class TwinChatMessage(BaseModel):
    message: str
    history: List[TwinChatTurn] = []

class SettingOut(BaseModel):
    id: int
    user_id: int
    key: str
    value: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Interaction Log Schemas ---
class InteractionLogCreate(BaseModel):
    message: str
    sender: str # 'user' or 'connection'

class InteractionLogOut(BaseModel):
    id: int
    connection_id: int
    user_id: int
    sender: str
    message: str
    screenshot_path: Optional[str] = None
    created_at: datetime

# --- Email Draft Schemas ---
# contact_status: "standard" (default) | "cold" | "messaged_no_reply" | "messaged_replied"
# style_modifiers: any of "referral", "punchy_opener"
# length: "short" | "mid" (default) | "long"
class EmailDraftRequest(BaseModel):
    contact_status: str = "standard"
    style_modifiers: List[str] = []
    length: str = "mid"
    custom_instructions: str = ""

    class Config:
        from_attributes = True
