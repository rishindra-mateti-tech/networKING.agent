import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from database import Base
from crypto import EncryptedString

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    connections = relationship("Connection", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("Setting", back_populates="user", cascade="all, delete-orphan")
    interaction_logs = relationship("InteractionLog", back_populates="user", cascade="all, delete-orphan")

class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Candidate details
    name = Column(String, index=True, nullable=False)
    current_title = Column(String, nullable=True)
    company = Column(String, nullable=True)
    location = Column(String, nullable=True)
    connection_count = Column(Integer, default=0)
    years_experience = Column(Float, default=0.0)
    
    # Ingested details
    profile_text = Column(Text, nullable=True)  # From PDF profile
    posts_text = Column(Text, nullable=True)    # pasted recent posts
    
    # Pipeline Funnel Status: pending, processing, completed, failed, replied, sent, interview, closed
    status = Column(String, default="pending", index=True)
    is_starred = Column(Boolean, default=False, index=True)
    
    # Bridge and Scoring Details
    why_person = Column(Text, nullable=True)
    bridge = Column(Text, nullable=True)
    best_angle = Column(String, nullable=True)  # Job referral, Learning, Project curiosity, Shared domain, Alumni path
    
    # Generated Outreach variants
    generated_outreach_short = Column(Text, nullable=True)
    generated_outreach_warm = Column(Text, nullable=True)
    generated_outreach_tech = Column(Text, nullable=True)
    generated_outreach_mixed = Column(Text, nullable=True)
    
    generated_outreach_referral = Column(Text, nullable=True)
    generated_outreach_coffee = Column(Text, nullable=True)
    generated_outreach_technical = Column(Text, nullable=True)
    generated_outreach_relationship = Column(Text, nullable=True)
    generated_outreach_featured = Column(Text, nullable=True)
    
    selected_variant = Column(String, nullable=True)  # 'referral', 'coffee', 'technical', 'relationship', 'featured'
    hiring_badge_status = Column(String, nullable=True)  # 'ON' or 'OFF' or custom

    
    # URL & Screen Context
    profile_url = Column(String, nullable=True)
    screenshot_path = Column(String, nullable=True)

    # Source file + contact details harvested from the PDF
    pdf_filename = Column(String, nullable=True)     # original uploaded filename
    candidate_email = Column(String, nullable=True)  # email found in the profile text, if any

    # Generated outreach email (kept separate from LinkedIn DM drafts, which
    # are short-form; this one is a real email with a subject line)
    generated_email_subject = Column(Text, nullable=True)
    generated_email_body = Column(Text, nullable=True)
    
    # Rich Platform Signals & Metrics
    networking_score = Column(Float, nullable=True)
    reply_probability = Column(Float, nullable=True)
    hiring_probability_score = Column(String, nullable=True)  # 'high', 'medium', 'low', 'unknown'
    is_decision_maker = Column(String, nullable=True)          # 'yes', 'no', 'partial'
    referral_potential = Column(String, nullable=True)         # 'high', 'medium', 'low'
    networking_difficulty = Column(String, nullable=True)      # 'easy', 'medium', 'hard', 'very_hard'
    conversation_starter = Column(Text, nullable=True)
    avoid_points = Column(Text, nullable=True)
    best_message_type = Column(String, nullable=True)
    
    # Multi-Agent outputs
    profile_intelligence = Column(Text, nullable=True)
    company_intelligence = Column(Text, nullable=True)
    relationship_strategy = Column(Text, nullable=True)
    personalization_data = Column(Text, nullable=True)
    context_summary = Column(Text, nullable=True)
    
    error_message = Column(Text, nullable=True)

    # Timestamps for reply-time analytics. Set once, at the moment the status
    # actually transitions, so later status changes (updated_at gets
    # overwritten on every change) don't destroy the original timing signal.
    sent_at = Column(DateTime, nullable=True)
    replied_at = Column(DateTime, nullable=True)

    # Conversation quality verdict from an uploaded chat screenshot
    conversation_verdict = Column(String, nullable=True)          # 'interested', 'lukewarm', 'not_interested', 'vague'
    conversation_verdict_reason = Column(Text, nullable=True)
    conversation_recommended_action = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="connections")
    interaction_logs = relationship("InteractionLog", back_populates="connection", cascade="all, delete-orphan")

class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    key_value = Column(EncryptedString, nullable=False)  # Encrypted at rest (see crypto.py)
    role = Column(String, default="primary")      # 'primary' or 'standby'
    is_active = Column(Boolean, default=True)
    cooldown_until = Column(DateTime, nullable=True)
    label = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="api_keys")

class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    key = Column(String, nullable=False)           # 'resume_context', 'resume_latex', 'github_url', 'portfolio_url', 'telegram_token', 'telegram_chat_id', 'pacing_interval_minutes'
    value = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="settings")

class InteractionLog(Base):
    __tablename__ = "interaction_logs"

    id = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("connections.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    sender = Column(String, nullable=False)        # 'user' or 'connection'
    message = Column(Text, nullable=False)
    screenshot_path = Column(String, nullable=True)  # optional uploaded conversation screenshot
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="interaction_logs")
    connection = relationship("Connection", back_populates="interaction_logs")
