from sqlalchemy.orm import Session
import models

def compile_twin_agent_profile(db: Session, user_id: int) -> str:
    """
    Compiles all available user settings (Resume text, LaTeX code, portfolio links,
    career preferences, and tone guidelines) into a structured markdown profile.
    This serves as the 'TwinAgent Persona' for the generation models.
    """
    # Fetch all settings for the user
    settings_records = db.query(models.Setting).filter(models.Setting.user_id == user_id).all()
    settings = {s.key: s.value for s in settings_records if s.value}

    # Extract fields with fallback defaults
    resume_context = settings.get("resume_context", "No resume PDF uploaded yet.")
    resume_latex = settings.get("resume_latex", "No LaTeX code provided.")
    github_url = settings.get("github_url", "Not provided.")
    portfolio_url = settings.get("portfolio_url", "Not provided.")
    linkedin_url = settings.get("linkedin_url", "Not provided.")
    job_search_status = settings.get("job_search_status", "Active software engineering job search on OPT.")
    target_roles = settings.get("target_roles", "Software Engineer, Full Stack Engineer, AI/ML Engineer.")
    tone_examples = settings.get("tone_examples", "No custom tone examples provided.")
    learning_goals = settings.get("learning_goals", "Genuinely interested in learning about distributed systems, backend scalability, and real-world agent deployments.")

    # Facts the user taught the agent directly, either by editing the
    # understanding summary or through the chat. Placed last in the profile so
    # they read as the most recent and most deliberate statement of who they
    # are, and can correct anything the resume implies incorrectly.
    twin_understanding = settings.get("twin_understanding", "")
    twin_extra_notes = settings.get("twin_extra_notes", "")

    profile_md = f"""# TWINAGENT PROFESSIONAL PERSONA PROFILE

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
