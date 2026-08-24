from sqlalchemy.orm import Session
import models


def get_sender_name(db: Session, user_id: int) -> str:
    """
    The actual name to write outreach in the voice of. This app is
    multi-tenant: every generation prompt needs the signed-in user's own
    name, not a name hardcoded for whoever originally built the app. Falls
    back to the local part of their account email when they haven't set
    "full_name" yet (auto-filled from their resume on upload, same as the
    other identity fields), so drafts are never signed with the wrong name.
    """
    setting = db.query(models.Setting).filter(
        models.Setting.user_id == user_id,
        models.Setting.key == "full_name"
    ).first()
    if setting and setting.value and setting.value.strip():
        return setting.value.strip()

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user and user.email:
        return user.email.split("@")[0]
    return "the sender"


def compile_twin_agent_profile(db: Session, user_id: int) -> str:
    """
    Compiles all available user settings (Resume text, LaTeX code, portfolio links,
    career preferences, and tone guidelines) into a structured markdown profile.
    This serves as the 'TwinAgent Persona' for the generation models.
    """
    # Fetch all settings for the user
    settings_records = db.query(models.Setting).filter(models.Setting.user_id == user_id).all()
    settings = {s.key: s.value for s in settings_records if s.value}

    # Extract fields with fallback defaults. These fallbacks are deliberately
    # neutral, not specific to any one person's background: this app is
    # multi-tenant, and a default like "on OPT" or "Software Engineer" would
    # be simply wrong for a different user in a different role, industry, or
    # country who hasn't filled a field in yet.
    full_name = settings.get("full_name", "").strip() or "Not provided."
    resume_context = settings.get("resume_context", "No resume PDF uploaded yet.")
    resume_latex = settings.get("resume_latex", "No LaTeX code provided.")
    github_url = settings.get("github_url", "Not provided.")
    portfolio_url = settings.get("portfolio_url", "Not provided.")
    linkedin_url = settings.get("linkedin_url", "Not provided.")
    job_search_status = settings.get("job_search_status", "Not specified.")
    target_roles = settings.get("target_roles", "Not specified.")
    tone_examples = settings.get("tone_examples", "No custom tone examples provided.")
    learning_goals = settings.get("learning_goals", "Not specified.")

    # Facts the user taught the agent directly, either by editing the
    # understanding summary or through the chat. Placed last in the profile so
    # they read as the most recent and most deliberate statement of who they
    # are, and can correct anything the resume implies incorrectly.
    twin_understanding = settings.get("twin_understanding", "")
    twin_extra_notes = settings.get("twin_extra_notes", "")

    profile_md = f"""# TWINAGENT PROFESSIONAL PERSONA PROFILE

## 0. Identity
- **Full Name**: {full_name}

## 1. Professional Identity & Status
- **Current Target Roles**: {target_roles}
- **Job Search / Legal Status**: {job_search_status}
- **Primary Learning Interests**: {learning_goals}

## 2. Professional Links
- **GitHub**: {github_url}
- **Portfolio**: {portfolio_url}
- **LinkedIn**: {linkedin_url}

## 3. Resume & Project Background
{resume_context}

## 4. Resume LaTeX Source Context (For Structural Precision)
```latex
{resume_latex}
```

## 5. Tone Guidelines & Sample Messages (Write Like This)
{tone_examples}
"""

    if twin_understanding:
        profile_md += f"""
## 6. Verified Self-Description (User-Confirmed, Highest Authority)
The user reviewed and approved this description of themselves. Where it
conflicts with anything inferred from the resume above, this wins.
{twin_understanding}
"""

    if twin_extra_notes:
        profile_md += f"""
## 7. Additional Context The User Provided Directly
{twin_extra_notes}
"""

    return profile_md
