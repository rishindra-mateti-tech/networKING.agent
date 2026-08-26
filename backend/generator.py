import re
import json
import os
from typing import List, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError
from parser import clean_unicode_text


def _strip_json_codeblock(text: str) -> str:
    """
    Strips markdown code fences (```json ... ```) that Gemini sometimes wraps
    around JSON responses, even when json_mode is requested.
    """
    text = text.strip()
    # Remove ```json ... ``` wrapper
    if text.startswith("```"):
        # Find the end of the first line (which may contain ```json or just ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove trailing ```
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return text


def _call_gemini(api_key: str, system_instruction: str, prompt_or_contents, json_mode: bool = False) -> str:
    """
    Calls the Gemini API using a per-call Client (google-genai SDK). Each Client instance
    carries its own API key with no shared global state, so concurrent workers on different
    keys run in true parallel, unlike the legacy `google.generativeai` module-global
    `configure()` API this replaced, which forced every call in the process onto one lock.
    """
    client = genai.Client(api_key=api_key)

    # Ordered fallback: try newest/fastest first, then stable models
    models_to_try = [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]
    last_exception = None

    for model_name in models_to_try:
        try:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json" if json_mode else None,
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt_or_contents,
                config=config,
            )
            raw_text = response.text
            # Clean unicode artifacts from Gemini output
            return clean_unicode_text(raw_text)
        except Exception as e:
            last_exception = e
            code = e.code if isinstance(e, APIError) else None
            error_str = str(e).lower()
            # If model not found (404), deprecated, or rate-limited (429), try the next model
            if code in (404, 429):
                continue
            if "404" in error_str or "not found" in error_str or "deprecated" in error_str:
                continue
            if "429" in error_str or "quota" in error_str or "rate" in error_str:
                continue
            # For other errors (auth, network), don't retry different models
            raise

    if last_exception:
        raise last_exception
    raise RuntimeError("Failed to obtain response from Gemini API.")


def validate_api_key(api_key: str) -> dict:
    """
    Makes one minimal Gemini call to confirm a newly added API key actually
    works, so a dead key or a typo gets caught immediately when it's added
    instead of silently failing the first time a worker tries to use it for
    real processing. This can only confirm the key is valid and currently
    able to make a call -- Gemini's API does not expose whether a key is on
    the free tier vs. a paid tier, or its exact rate limits, so this cannot
    report that.
    """
    try:
        _call_gemini(api_key, "Reply with exactly one word.", "Say hello.")
        return {"valid": True, "error": None}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def run_profile_intelligence_agent(api_key: str, name: str, profile_text: str, posts_text: str, screenshot_path: str = None, posts_screenshot_path: str = None) -> dict:
    """
    Agent 1: Profile Intelligence Agent
    Extracts name, role (title), seniority, company, follower count, education,
    technologies, mutual interests, recent posts, and screenshot visual details.

    Connection count and hiring-badge status are deliberately NOT guessed here:
    a text-only model reading an exported PDF has no reliable way to see
    LinkedIn's visual "Open to Work"/"Hiring" badge, and connection count is
    either explicitly stated in the text (parsed separately, see parser.py)
    or left for the user to enter, never invented.
    """
    system_instruction = (
        "You are a Profile Intelligence Agent. Your job is to extract detailed professional profile details "
        "about a candidate from their LinkedIn PDF export, optional profile screenshot, and optional screenshot "
        "of their recent posts."
    )

    prompt = f"""
    Extract the following details from the LinkedIn profile of candidate: {name}.

    PROFILE PDF TEXT:
    {profile_text or "No PDF text provided."}

    RECENT POSTS TEXT:
    {posts_text or "No posts text provided."}
    {"A screenshot of their recent posts is attached below the profile screenshot (if any). Read any text visible in it and factor it into recent_posts and tone." if posts_screenshot_path else ""}
    
    Analyze the profile text and optional screenshot (if provided) to return a JSON object with the following fields:
    - "name": Candidate's full name.
    - "role": Current title/role.
    - "title": Current title (same as role).
    - "seniority": Seniority category. Must be one of: "CEO", "Founder", "Recruiter", "Senior SWE", "Principal Engineer", "Engineering Manager", "University Alum", "HR", "VP", "Director", "Other".
    - "company": Current company name.
    - "follower_count": Candidate's follower count if visible (e.g. "1,200", "50k", or "Under 500"). If not found, output "Under 500".
    - "years_experience": Approximate TOTAL years of professional experience across their entire career,
      every employer combined (float/number).
    - "current_company_years_experience": Approximate years spent at their CURRENT company specifically
      (float/number), which is very often much smaller than years_experience. A senior director with 16
      years of total experience who joined their current company 1 year ago should report
      "years_experience": 16 and "current_company_years_experience": 1. These two numbers describe
      different things and are not interchangeable: total experience is what the person can credibly
      claim overall, current-company tenure is what determines whether they're established enough there
      to give a referral or speak for the team's current hiring needs.
    - "education": Summary of their education (e.g. degrees, universities).
    - "mutual_interests": Any mutual interests, topics, or domains.
    - "technologies": Core programming languages, systems, stacks, or tools they work with.
    - "recent_posts": Summary of their recent activities/posts if provided.
    - "tone": Tone of their writing or posts (e.g., direct, technical, academic, casual).
    - "company_size": Estimate company size category: "Enterprise", "Mid-size", "Startup", "Scaleup".
    - "hiring_probability": Assessment of their likelihood of hiring (e.g., "High", "Medium", "Low", "Unknown").
    - "best_conversation_angle": One of: "Job Referral", "Learning", "Project Curiosity", "Shared Domain", "Alumni Path".
    - "screenshot_observations": Any interesting visual detail extracted from the screenshot (e.g. active hiring banner, featured projects, specific certifications, activity). Write "None" if no screenshot is provided.
    
    Return ONLY raw JSON. Do not include markdown code blocks or wrapper text.
    """

    contents = [prompt]
    if screenshot_path and os.path.exists(screenshot_path):
        try:
            import PIL.Image
            img = PIL.Image.open(screenshot_path)
            contents.append(img)
        except Exception as e:
            print(f"[PROFILE AGENT] Warning: Failed to load screenshot image: {e}")
    if posts_screenshot_path and os.path.exists(posts_screenshot_path):
        try:
            import PIL.Image
            img = PIL.Image.open(posts_screenshot_path)
            contents.append(img)
        except Exception as e:
            print(f"[PROFILE AGENT] Warning: Failed to load posts screenshot image: {e}")

    try:
        raw_output = _call_gemini(api_key, system_instruction, contents, json_mode=True)
        cleaned_output = _strip_json_codeblock(raw_output)
        data = json.loads(cleaned_output)
        return {
            "name": clean_unicode_text(data.get("name", name)),
            "role": clean_unicode_text(data.get("role", "")),
            "title": clean_unicode_text(data.get("title", data.get("role", ""))),
            "seniority": data.get("seniority", "Other"),
            "company": clean_unicode_text(data.get("company", "")),
            "follower_count": data.get("follower_count", "Under 500"),
            "years_experience": float(data.get("years_experience") or 0.0),
            "current_company_years_experience": float(data.get("current_company_years_experience") or 0.0),
            "education": clean_unicode_text(data.get("education", "")),
            "mutual_interests": clean_unicode_text(data.get("mutual_interests", "")),
            "technologies": clean_unicode_text(data.get("technologies", "")),
            "recent_posts": clean_unicode_text(data.get("recent_posts", "")),
            "tone": clean_unicode_text(data.get("tone", "")),
            "company_size": data.get("company_size", "Startup"),
            "hiring_probability": data.get("hiring_probability", "Unknown"),
            "best_conversation_angle": data.get("best_conversation_angle", "Shared Domain"),
            "screenshot_observations": clean_unicode_text(data.get("screenshot_observations", "None"))
        }
    except Exception as e:
        print(f"Error in profile intelligence agent: {e}")
        return {
            "name": name,
            "role": "Software Professional",
            "title": "Software Professional",
            "seniority": "Other",
            "company": "Company",
            "follower_count": "Under 500",
            "years_experience": 0.0,
            "current_company_years_experience": 0.0,
            "education": "",
            "mutual_interests": "",
            "technologies": "",
            "recent_posts": "",
            "tone": "professional",
            "company_size": "Startup",
            "hiring_probability": "Unknown",
            "best_conversation_angle": "Shared Domain",
            "screenshot_observations": "None"
        }


def run_company_intelligence_agent(api_key: str, profile_json: dict) -> dict:
    """
    Agent 2: Company Intelligence Agent
    Classifies the company type, stage (Seed, Series A, Series B, IPO, Fortune 500), employee count,
    hiring status, engineering culture, and decision-maker accessibility.
    """
    system_instruction = (
        "You are a Company Intelligence Agent. Your job is to classify the candidate's current company "
        "and analyze its engineering culture, hiring behavior, and communication expectations."
    )

    prompt = f"""
    Analyze the company '{profile_json.get("company", "Unknown")}' where the candidate works as '{profile_json.get("role", "Unknown")}'.
    
    CANDIDATE DETAILS:
    - Name: {profile_json.get("name")}
    - Role: {profile_json.get("role")}
    - Company: {profile_json.get("company")}
    - Company Size Category: {profile_json.get("company_size")}
    
    Return a JSON object with the following fields:
    - "company_type": Must be one of: "Enterprise", "Startup", "Scaleup", "Research Lab", "Consulting", "Government", "University", "Other".
    - "approximate_size": Estimated number of employees (e.g. "1-10", "11-50", "51-200", "201-1000", "1000-5000", "5000+").
    - "company_stage": Stage of company development. Must be one of: "Seed", "Series A", "Series B", "IPO", "Fortune 500", "Unknown".
    - "employee_count": Estimated number of employees (string, e.g. "150 employees" or "5000+").
    - "hiring_status": General company hiring status (one of: "actively hiring", "slow hiring", "frozen", "unknown").
    - "engineering_culture": Core style of their engineering team (e.g. research-focused, fast-shipping startup, structured corporate enterprise, open-source).
    - "hiring_culture": Description of their hiring behavior and candidate intake style.
    - "referral_friendliness": Likelihood of employees giving referrals (e.g. "High", "Medium", "Low", "Highly Restricted").
    - "outreach_difficulty": Expected difficulty of getting a response (e.g. "High", "Medium", "Low").
    - "expected_response_rate": Inferred response rate percentage (e.g. "5%", "15%", "30%").
    - "decision_making_hierarchy": Expected level of influence this role has in hiring decisions.
    - "typical_outreach_style": Suggested tone (e.g. technical & deep, brief & casual, formal & credentials-first).
    - "decision_maker_accessibility": Inferred accessibility of decision makers in this company (e.g., "easy", "medium", "hard").
    
    Return ONLY raw JSON. Do not include markdown code blocks or wrapper text.
    """

    try:
        raw_output = _call_gemini(api_key, system_instruction, prompt, json_mode=True)
        cleaned_output = _strip_json_codeblock(raw_output)
        data = json.loads(cleaned_output)
        return {
            "company_type": data.get("company_type", "Other"),
            "approximate_size": data.get("approximate_size", "Unknown"),
            "company_stage": data.get("company_stage", "Unknown"),
            "employee_count": data.get("employee_count", data.get("approximate_size", "Unknown")),
            "hiring_status": data.get("hiring_status", "unknown"),
            "hiring_culture": clean_unicode_text(data.get("hiring_culture", "")),
            "engineering_culture": clean_unicode_text(data.get("engineering_culture", "")),
            "referral_friendliness": data.get("referral_friendliness", "Medium"),
            "outreach_difficulty": data.get("outreach_difficulty", "Medium"),
            "expected_response_rate": data.get("expected_response_rate", "Unknown"),
            "decision_making_hierarchy": clean_unicode_text(data.get("decision_making_hierarchy", "")),
            "typical_outreach_style": clean_unicode_text(data.get("typical_outreach_style", "")),
            "decision_maker_accessibility": data.get("decision_maker_accessibility", "medium")
        }
    except Exception as e:
        print(f"Error in company intelligence agent: {e}")
        return {
            "company_type": "Other",
            "approximate_size": "Unknown",
            "company_stage": "Unknown",
            "employee_count": "Unknown",
            "hiring_status": "unknown",
            "hiring_culture": "",
            "engineering_culture": "",
            "referral_friendliness": "Medium",
            "outreach_difficulty": "Medium",
            "expected_response_rate": "Unknown",
            "decision_making_hierarchy": "",
            "typical_outreach_style": "",
            "decision_maker_accessibility": "medium"
        }


def run_relationship_strategy_agent(api_key: str, profile_json: dict, company_json: dict, connection_count: Optional[int] = None, hiring_badge_status: Optional[str] = None) -> dict:
    """
    Agent 3: Relationship Strategy Agent
    Decides the best outreach approach, calculates key networking metrics (networking score, reply probability,
    decision maker status, networking difficulty, referral potential, hiring probability), and establishes strict DOs and DONTs.

    connection_count and hiring_badge_status come from the Connection row itself (a real
    parsed "N connections" match, or a value the user entered manually), never from a
    model guess. When neither is available they're passed through as None, in which case
    the prompt is told outright to leave them out of the score rather than defaulting to
    a number or status that was never actually confirmed.
    """
    system_instruction = (
        "You are a Relationship Strategy Agent. Your job is to decide the best outreach approach, "
        "calculate networking intelligence metrics, and establish strict DOs and DONTs rules based on the candidate's seniority and company context."
    )

    connection_count_line = str(connection_count) if connection_count is not None else "Not provided, do not factor this into the score."
    hiring_badge_line = hiring_badge_status if hiring_badge_status else "Not provided, do not factor this into the score or hiring_probability_score."

    prompt = f"""
    Determine the relationship strategy and networking metrics for contacting the following candidate:

    CANDIDATE PROFILE:
    - Name: {profile_json.get("name")}
    - Seniority Category: {profile_json.get("seniority")}
    - Role: {profile_json.get("role")}
    - Company: {profile_json.get("company")}
    - Follower Count: {profile_json.get("follower_count")}
    - Connection Count: {connection_count_line}
    - Hiring Badge Status: {hiring_badge_line}

    COMPANY DETAILS:
    - Company Type: {company_json.get("company_type")}
    - Company Stage: {company_json.get("company_stage")}
    - Outreach Difficulty: {company_json.get("outreach_difficulty")}
    - Typical Outreach Style: {company_json.get("typical_outreach_style")}
    
    Determine the strategy and return a JSON object with the following fields:
    - "networking_score": Overall rating of candidate as a networking target from 1.0 to 10.0 (Float). Higher scores for decision makers, hiring teams, and alumni in relevant fields.
    - "reply_probability": Statistical likelihood (0.0 to 100.0%) of receiving a reply. Highly active accounts, alumni, and recruiters have high rates, while VIPs with large audience size (follower count) have lower rates.
    - "is_decision_maker": Inferred decision maker status (one of: "yes", "no", "partial").
    - "networking_difficulty": Expected difficulty of networking (one of: "easy", "medium", "hard", "very_hard").
      CONSISTENCY RULE: this must agree with reply_probability, since they measure the same underlying thing
      from two directions. Someone easy to reach is by definition likely to reply. Keep them aligned:
        reply_probability 60-100  -> "easy"
        reply_probability 35-59   -> "medium"
        reply_probability 15-34   -> "hard"
        reply_probability 0-14    -> "very_hard"
      Never report a low reply probability alongside "easy", or a high one alongside "hard".
    - "referral_potential": Referral potential (one of: "high", "medium", "low").
    - "hiring_probability_score": Likelihood of hiring status (one of: "high", "medium", "low", "unknown"). Matches the hiring badge and company context.
    - "strategy": A brief description of the core strategy.
    - "reason": Rationale for this strategy based on seniority, audience size, and company size.
    - "confidence": Confidence score from 0.0 to 1.0.
    - "dos": A list of items to explicitly include or do (e.g. "mention shared tech stack", "ask a technical question").
    - "donts": A list of items to explicitly avoid or NOT do (e.g. "do not ask for coffee chat", "do not ask for referral").
    
    Rules guidelines:
    - If seniority is CEO, Founder, VP, or Director: DONT ask for a referral, DONT ask for a coffee chat. DO mention company vision or a specific product, DO ask a thoughtful technical/strategic question. Set is_decision_maker to "yes" or "partial".
    - If seniority is Recruiter or HR: DO mention the target role, DO ask whether background aligns, DO offer resume.
    - If seniority is Senior SWE or Principal Engineer: DO mention technical systems/projects, DO ask technical/advice questions.
    - If seniority is University Alum: DO mention shared university connection, DO ask about their path.
    
    Return ONLY raw JSON. Do not include markdown code blocks or wrapper text.
    """

    try:
        raw_output = _call_gemini(api_key, system_instruction, prompt, json_mode=True)
        cleaned_output = _strip_json_codeblock(raw_output)
        data = json.loads(cleaned_output)
        
        # Parse scores
        try:
            net_score = float(data.get("networking_score", 5.0))
        except (ValueError, TypeError):
            net_score = 5.0
            
        try:
            reply_prob = float(data.get("reply_probability", 50.0))
        except (ValueError, TypeError):
            reply_prob = 50.0

        # Derive difficulty from reply probability rather than trusting the two
        # to agree. They describe the same thing from opposite directions, and
        # asked separately the model would happily return "35% reply chance"
        # next to "easy", which reads as broken to anyone looking at the card.
        if reply_prob >= 60:
            difficulty = "easy"
        elif reply_prob >= 35:
            difficulty = "medium"
        elif reply_prob >= 15:
            difficulty = "hard"
        else:
            difficulty = "very_hard"

        return {
            "networking_score": net_score,
            "reply_probability": reply_prob,
            "is_decision_maker": data.get("is_decision_maker", "no"),
            "networking_difficulty": difficulty,
            "referral_potential": data.get("referral_potential", "medium"),
            "hiring_probability_score": data.get("hiring_probability_score", "unknown"),
            "strategy": clean_unicode_text(data.get("strategy", "")),
            "reason": clean_unicode_text(data.get("reason", "")),
            "confidence": float(data.get("confidence") or 0.8),
            "dos": data.get("dos") or ["mention shared interests"],
            "donts": data.get("donts") or ["do not sound generic"]
        }
    except Exception as e:
        print(f"Error in relationship strategy agent: {e}")
        return {
            "networking_score": 5.0,
            "reply_probability": 50.0,
            "is_decision_maker": "no",
            "networking_difficulty": "medium",
            "referral_potential": "medium",
            "hiring_probability_score": "unknown",
            "strategy": "Direct connect",
            "reason": "Default fallback strategy due to error",
            "confidence": 0.5,
            "dos": ["mention shared interests"],
            "donts": ["do not sound generic"]
        }


def run_personalization_agent(api_key: str, profile_json: dict, company_json: dict, screenshot_obs: str = None) -> dict:
    """
    Agent 4: Personalization Agent
    Identifies specific career motivation hooks, custom conversation starters, key projects/achievements, and lists points to avoid.
    """
    system_instruction = (
        "You are a Personalization Agent. Your job is to identify the strongest common ground, "
        "unique conversation hooks (like career transitions, transition motivations), "
        "specific conversation starters, and things to avoid to make outreach feel authentic."
    )

    prompt = f"""
    Find the best personalization details for:
    
    PROFILE:
    - Name: {profile_json.get("name")}
    - Core Stacks/Technologies: {profile_json.get("technologies")}
    - Education: {profile_json.get("education")}
    - Career Experience: {profile_json.get("years_experience")} years
    - Mutual Interests: {profile_json.get("mutual_interests")}
    - Posts Summary: {profile_json.get("recent_posts")}
    - Profile Screenshot Observations: {screenshot_obs or "None"}
    
    COMPANY:
    - Company Name: {profile_json.get("company")}
    - Engineering Culture: {company_json.get("engineering_culture")}
    
    Generate and return a JSON object with the following fields:
    - "motivation_hooks": An analysis of their career transition/motivation patterns (e.g., transition from big tech like Amazon to a 15-person startup after 8 years, or passion for AI Agent safety).
    - "conversation_starter": A tailored, conversational, low-pressure opening sentence or topic specific to their career path or recent activity.
    - "avoid_points": A list of points or topics to avoid mentioning/asking (e.g. "do not request a referral in the first message", "do not ask for coffee chat with high-seniority profiles immediately").
    - "conversation_hooks": A list of 2-3 specific, highly-tailored conversational hooks (e.g., referencing a project, a technology stack they use, or their career transition).
    - "shared_elements": List of shared tech stacks, career interests, or academic overlaps.
    - "highlighted_projects": Key projects or achievements from their profile to mention.
    - "custom_observations": Subtle observations (e.g., active certifications, featured posts, specific keywords in their profile).
    
    Return ONLY raw JSON. Do not include markdown code blocks or wrapper text.
    """

    try:
        raw_output = _call_gemini(api_key, system_instruction, prompt, json_mode=True)
        cleaned_output = _strip_json_codeblock(raw_output)
        data = json.loads(cleaned_output)
        
        # Format avoid points to a string for simple storage
        av_pts = data.get("avoid_points") or []
        if isinstance(av_pts, list):
            av_text = "; ".join(av_pts)
        else:
            av_text = str(av_pts)

        return {
            "motivation_hooks": clean_unicode_text(data.get("motivation_hooks", "")),
            "conversation_starter": clean_unicode_text(data.get("conversation_starter", "")),
            "avoid_points": clean_unicode_text(av_text),
            "conversation_hooks": data.get("conversation_hooks") or [],
            "shared_elements": data.get("shared_elements") or [],
            "highlighted_projects": data.get("highlighted_projects") or [],
            "custom_observations": data.get("custom_observations") or []
        }
    except Exception as e:
        print(f"Error in personalization agent: {e}")
        return {
            "motivation_hooks": "",
            "conversation_starter": "",
            "avoid_points": "",
            "conversation_hooks": ["Mention shared tech stack interest"],
            "shared_elements": [],
            "highlighted_projects": [],
            "custom_observations": []
        }


def generate_context_summary(api_key: str, profile_json: dict, company_json: dict, strategy_json: dict, personalization_json: dict) -> str:
    """
    Synthesizer Step: Context Summary Generator
    Creates a 2-4 sentence reasoning summary representing a 'mental model' of the outreach thesis.
    """
    system_instruction = (
        "You are a Context Synthesizer. Your job is to write a concise, 2-to-4 sentence reasoning summary "
        "that synthesizes the candidate analysis and outreach strategy into a natural language 'mental model' for message writing."
    )

    prompt = f"""
    Synthesize a 2-4 sentence reasoning summary for writing an outreach message.
    
    CANDIDATE: {profile_json.get("name")} ({profile_json.get("role")} at {profile_json.get("company")})
    SENIORITY: {profile_json.get("seniority")}
    COMPANY CLASSIFICATION: {company_json.get("company_type")} ({company_json.get("approximate_size")} employees)
    STRATEGY DECIDED: {strategy_json.get("strategy")}
    STRATEGY REASON: {strategy_json.get("reason")}
    DOS: {strategy_json.get("dos")}
    DONTS: {strategy_json.get("donts")}
    KEY HOOKS: {personalization_json.get("conversation_hooks")}
    
    Write a 2-4 sentence natural language reasoning synthesis explaining exactly who this person is, the core thesis of the approach, and what to highlight vs. avoid.
    Do not include markdown or tags. Return only the plain text summary.
    """

    try:
        raw_output = _call_gemini(api_key, system_instruction, prompt)
        return clean_unicode_text(raw_output.strip())
    except Exception as e:
        print(f"Error in context synthesis: {e}")
        return f"Outreach targeting {profile_json.get('name')} at {profile_json.get('company')}. Focusing on {strategy_json.get('strategy')} based on their {profile_json.get('seniority')} role."


def run_message_writing_agent(
    api_key: str,
    profile_json: dict,
    company_json: dict,
    strategy_json: dict,
    personalization_json: dict,
    context_summary: str,
    twin_profile: str,
    tone_examples: str,
    sender_name: str = "the user",
) -> dict:
    """
    Agent 5: Message Writing Agent
    Takes reasoning JSONs and the reasoning context summary, plus twin profile and tone guidelines.
    Writes exactly 5 objective-specific outreach message drafts in the voice of the user (sender_name,
    the currently signed-in account -- this app is multi-tenant, so this must never be hardcoded).
    Fills in the candidate's actual name and company instead of outputting placeholders like [Name].
    No conversational clichés are allowed. Follows explicit strategy guidelines.
    """
    candidate_name = profile_json.get("name", "there")
    candidate_company = profile_json.get("company", "your company")

    system_instruction = (
        "You are a Message Writing Agent. Your ONLY job is to draft outreach messages. "
        "You have NO reasoning responsibility. Follow the decided strategy, dos, donts, and context summary strictly. "
        f"Write in the voice of the user ({sender_name}). You must substitute actual candidate details (name, company) "
        "and never output bracketed placeholders like [Name] or [Company]. "
        f"{sender_name}'s voice is highly polite, humble, requesting, and professional. Always acknowledge that their "
        "time is valuable, use phrases like 'no pressure', and ask if they can share their insights, guidance, or perspective.\n\n"
        "HOW TO SOUND LIKE AN ACTUAL PERSON, NOT A MODEL:\n"
        "- Never use an em dash (—) or en dash (–) anywhere, for any reason. If you're tempted to use one to join two "
        "clauses, that's a sign the sentence is trying to do too much. Split it into two sentences, or use 'and', 'but', "
        "a comma, or a period instead. A real person texting on LinkedIn does not use em dashes.\n"
        "- Write like you're typing a message to someone, not composing a business letter. Short sentences next to "
        "longer ones. Occasional sentence fragments are fine. Contractions are expected (I'm, I've, it's, that's).\n"
        "- Never open with a rhetorical question ('Ever wondered how...'), a compliment sandwich ('I hope this message "
        "finds you well', 'I was really impressed by your profile'), or a resume dump. Open with something specific and "
        "true about them or their work, in plain language.\n"
        "- Do not use corporate/LinkedIn-influencer vocabulary: 'delve', 'tapestry', 'leverage', 'synergy', 'unlock', "
        "'game-changer', 'passionate about', 'reaching out because', 'circle back', 'touch base', 'pick your brain', "
        "'thought leader', 'journey' (as a metaphor for career), 'excited to connect', 'would love to connect', "
        "'in today's fast-paced world', 'navigate the landscape of'. If a phrase sounds like it belongs in a "
        "LinkedIn 'thought leadership' post, cut it.\n"
        "- Do not stack adjectives or hype anything up ('incredible work', 'amazing journey', 'truly inspiring'). "
        "Describe what they actually did in specific, concrete terms instead of praising it in the abstract.\n"
        "- One idea leads to the next like a person actually thinking, not a list of talking points glued together. "
        "No message should read like it was assembled from a template with the blanks filled in, even though "
        "technically it was.\n"
        "- Never end on a generic sign-off phrase like 'Looking forward to hearing from you!' or 'Thanks in advance!'. "
        "End the way a thoughtful person would: a real, specific ask or a low-key acknowledgment that they're busy."
    )

    prompt = f"""
    USER DETAILS ({sender_name}):
    {twin_profile}
    
    TONE EXAMPLES / GUIDELINES:
    {tone_examples or "Curious, sincere, practical, slightly informal, and respectful."}
    
    CANDIDATE DETAILS:
    - Name: {candidate_name}
    - Current Role: {profile_json.get("role")}
    - Company: {candidate_company}
    - Core Technologies: {profile_json.get("technologies")}
    - Experience: {profile_json.get("years_experience")} years
    - Seniority Category: {profile_json.get("seniority")}
    
    COMPANY PROFILE:
    - Type: {company_json.get("company_type")}
    - Size: {company_json.get("approximate_size")}
    - Typical Style: {company_json.get("typical_outreach_style")}
    
    STRATEGY DECISION:
    - Context Summary: {context_summary}
    - Explicit DOs: {strategy_json.get("dos")}
    - Explicit DONTs: {strategy_json.get("donts")}
    
    PERSONALIZATION DETAILS:
    - Motivation Hooks: {personalization_json.get("motivation_hooks")}
    - Conversation Starter: {personalization_json.get("conversation_starter")}
    - Things to Avoid: {personalization_json.get("avoid_points")}
    
    Write exactly 5 message variants in the voice of {sender_name} following these instructions:
    - Do not do any reasoning. Just output the drafts.
    - Strictly respect all DONTs and Things to Avoid.
    - Write short messages (usually 2 to 5 sentences) for variants 1-4.
    - Write a longer, natural message for variant 5 (Featured Draft) without word count restrictions, modeled after the templates below.
    - **CRITICAL**: Fill in actual candidate details. Substitute '[Name]' with '{candidate_name}' and '[Company]' with '{candidate_company}' directly in the drafts. Do NOT output bracketed placeholders like '[Name]' or '[Company]'.
    - **TONE RULE**: Make the drafts sound polite, humble, and requesting. You MUST include phrases like: 'I know your time is valuable, so there is absolutely no pressure', 'I would be incredibly grateful for any advice you could share', 'I would truly value your perspective', or 'If you ever have a few spare minutes to share your insights, I'd genuinely appreciate it'.
    - CRITICAL NEGATIVE CONSTRAINT: Never use an em dash (—) or en dash (–). Ban all AI clichés: "Hope this finds you well", "Hope you are doing well", "I was impressed by your profile", "Quick chat", "15-minute coffee chat", "delve", "leverage", "synergy", "unlock", "game-changer", "passionate about", "reaching out because", "pick your brain", "thought leader", "excited to connect", "would love to connect", "in today's fast-paced world", "navigate the landscape of", "incredible work", "truly inspiring", "Looking forward to hearing from you!", "Thanks in advance!".
    - COFFEE CHAT CONSTRAINT: If the candidate's seniority is Founder, CEO, VP, or Director, DO NOT request a coffee chat or a meeting in the Coffee Chat draft. Instead, write it as a brief, respectful request to connect/follow their work or ask a quick strategic question.
    
    FEW-SHOT TONE REFERENCE TEMPLATES (STRUCTURE AND TONE ONLY, NOT FACTS):
    These four examples exist to show sentence rhythm, warmth, and the "no pressure" pattern. They are
    NOT a source of truth about who the sender is, what they do, where they studied, or what company
    they work at -- every bracketed placeholder below must be filled from the actual USER DETAILS
    ({sender_name}) section above, which is different for every account using this app. Never reuse the
    illustrative examples inside the brackets (a specific school, a specific employer) as if they were
    real; they are only there to show the shape of what belongs in that spot.
    * Referral / Opportunity Inquiry:
      "Hi {candidate_name}, I'm {sender_name}, [role/status from USER DETAILS, e.g. a software engineer at [their actual company]], where I [what they actually work on, from USER DETAILS]. I saw that your team at {candidate_company} focuses on shipping fast, which caught my attention. With my background in [their actual relevant background], I'm curious if your team is currently looking for additional engineering support. I know your time is valuable, so there is absolutely no pressure, but I would be grateful to connect and learn more about what you're building."

    * Low-Pressure Career Advice Request (Connection Accepted Follow-up):
      "Hi {candidate_name}, thanks for connecting. [role/status from USER DETAILS, one sentence]. I spent some time going through your profile, and I was genuinely impressed by your journey at {candidate_company}. I'm trying to learn from developers who have successfully navigated this path. If you ever have a few spare minutes, I'd be incredibly grateful for any advice or insights you could share on what skills are critical for your team. I know your time is valuable, so there is absolutely no pressure at all."

    * Alumni / Common Ground Builder (ONLY use this angle if USER DETAILS actually names a shared school/employer with the candidate -- never invent one):
      "Fellow [their actual school] Builder 👋 Hi {candidate_name}, fellow [their actual school] alum here. I came across your profile while learning about {candidate_company} and really enjoyed seeing how you approached building resilient engineering teams. [role/status from USER DETAILS, one sentence]. If you ever have a spare moment to share your perspective on how you made that transition, I would truly value your guidance. No pressure at all."

    * Recruiter / TA Specialist Advice Request:
      "Hi {candidate_name}, Thank you for connecting. [role/status from USER DETAILS, one sentence]. I know you support technical recruiting at {candidate_company}, so I wanted to ask very humbly, what would you recommend I focus on to become a stronger candidate? I know your time is valuable, so even a single line of advice would be something I'd be incredibly grateful for."

    Before writing, check the USER DETAILS section above for the sender's actual current job/school
    status and use that exact reality in every draft. Never say "currently pursuing" or "student" if
    USER DETAILS indicates they have already graduated or hold a different status now.

    NEVER STATE VISA OR WORK-AUTHORIZATION STATUS UNPROMPTED: whether the sender is on OPT, CPT, H1B,
    needs sponsorship, or anything else in that category is background context ONLY, used to judge what
    kind of ask is appropriate (e.g. it's fine to ask about openings when actively job searching), never
    something to volunteer as a stated fact in the message itself. A cold first message is not the place
    to disclose immigration status, and the recipient did not ask. Only mention it if the draft is
    explicitly and specifically about work authorization/sponsorship (rare, and only when the strategy
    above calls for it directly). "I'm a software engineer" or "I recently graduated with a Master's in
    CS" is the right level of detail; "I'm on OPT" in an unrelated referral/coffee-chat/technical/
    relationship draft is not.

    Please generate EXACTLY 5 message variants:
    1. Referral Draft (Focuses on job opportunity referral or learning about open opportunities in their team/company)
    2. Coffee Chat Draft (A short chat/networking request. For high-seniority targets, adjust this to be a low-pressure question/connection request instead of a meeting ask)
    3. Technical Draft (Deep technical inquiry about their systems, codebase, tech stack, or engineering culture)
    4. Relationship Building Draft (Low-pressure initial connection, focused on common ground or mutual interest, with no immediate ask)
    5. Featured Draft (Longer, high-fidelity outreach message without word count restrictions, representing your best outreach style)
    
    Format the output with the headers below so they can be parsed programmatically:
    [REFERRAL_DRAFT]
    (Variant 1 text here)
    
    [COFFEE_CHAT_DRAFT]
    (Variant 2 text here)
    
    [TECHNICAL_DRAFT]
    (Variant 3 text here)
    
    [RELATIONSHIP_BUILDING_DRAFT]
    (Variant 4 text here)
    
    [FEATURED_DRAFT]
    (Variant 5 text here)
    """

    try:
        raw_output = _call_gemini(api_key, system_instruction, prompt)
        
        # Parse variants
        variants = {
            "referral": "Failed to generate referral variant.",
            "coffee": "Failed to generate coffee chat variant.",
            "technical": "Failed to generate technical variant.",
            "relationship": "Failed to generate relationship variant.",
            "featured": "Failed to generate featured variant.",
            # Retain old keys for backward compatibility
            "short": "Failed to generate short variant.",
            "warm": "Failed to generate warm variant.",
            "tech": "Failed to generate tech variant.",
            "mixed": "Failed to generate mixed variant."
        }

        ref_match = re.search(r"\[REFERRAL_DRAFT\](.*?)(\[COFFEE_CHAT_DRAFT\]|\[TECHNICAL_DRAFT\]|\[RELATIONSHIP_BUILDING_DRAFT\]|\[FEATURED_DRAFT\]|$)", raw_output, re.DOTALL | re.IGNORECASE)
        coffee_match = re.search(r"\[COFFEE_CHAT_DRAFT\](.*?)(\[REFERRAL_DRAFT\]|\[TECHNICAL_DRAFT\]|\[RELATIONSHIP_BUILDING_DRAFT\]|\[FEATURED_DRAFT\]|$)", raw_output, re.DOTALL | re.IGNORECASE)
        tech_match = re.search(r"\[TECHNICAL_DRAFT\](.*?)(\[REFERRAL_DRAFT\]|\[COFFEE_CHAT_DRAFT\]|\[RELATIONSHIP_BUILDING_DRAFT\]|\[FEATURED_DRAFT\]|$)", raw_output, re.DOTALL | re.IGNORECASE)
        rel_match = re.search(r"\[RELATIONSHIP_BUILDING_DRAFT\](.*?)(\[REFERRAL_DRAFT\]|\[COFFEE_CHAT_DRAFT\]|\[TECHNICAL_DRAFT\]|\[FEATURED_DRAFT\]|$)", raw_output, re.DOTALL | re.IGNORECASE)
        feat_match = re.search(r"\[FEATURED_DRAFT\](.*?)(\[REFERRAL_DRAFT\]|\[COFFEE_CHAT_DRAFT\]|\[TECHNICAL_DRAFT\]|\[RELATIONSHIP_BUILDING_DRAFT\]|$)", raw_output, re.DOTALL | re.IGNORECASE)

        def clean_placeholders(text: str) -> str:
            if not text:
                return text
            # Replace bracketed candidate placeholders. The sender-side
            # fallbacks are deliberately generic (not a hardcoded name/company
            # from whoever built this app) since this is multi-tenant -- they
            # should essentially never fire given the instructions above, but
            # if the model slips, "my current company" reads fine for anyone.
            text = re.sub(r'\[\s*(Candidate\s*)?Name\s*\]', candidate_name, text, flags=re.IGNORECASE)
            text = re.sub(r'\[\s*(Candidate\s*)?Company\s*\]', candidate_company, text, flags=re.IGNORECASE)
            text = re.sub(r'\[\s*Your\s*Name\s*\]', sender_name, text, flags=re.IGNORECASE)
            text = re.sub(r'\[\s*Your\s*Company\s*\]', "my current company", text, flags=re.IGNORECASE)

            # Direct text replaces
            text = text.replace("[Name]", candidate_name)
            text = text.replace("[Company]", candidate_company)
            text = text.replace("[Your Name]", sender_name)
            text = text.replace("[Your Company]", "my current company")
            text = text.replace("[Role Name]", "my role")
            text = text.replace("[Role]", "my role")
            return text

        if ref_match:
            val = clean_placeholders(clean_unicode_text(ref_match.group(1).strip()))
            variants["referral"] = val
            variants["short"] = val
        if coffee_match:
            val = clean_placeholders(clean_unicode_text(coffee_match.group(1).strip()))
            variants["coffee"] = val
            variants["warm"] = val
        if tech_match:
            val = clean_placeholders(clean_unicode_text(tech_match.group(1).strip()))
            variants["technical"] = val
            variants["tech"] = val
        if rel_match:
            val = clean_placeholders(clean_unicode_text(rel_match.group(1).strip()))
            variants["relationship"] = val
            variants["mixed"] = val
        if feat_match:
            val = clean_placeholders(clean_unicode_text(feat_match.group(1).strip()))
            variants["featured"] = val

        # Deliberately no profile link appended to the drafts. The notification
        # already carries the URL once at the top, and these drafts get pasted
        # straight into a LinkedIn DM to this person, where linking them to
        # their own profile makes no sense.
        return variants
    except Exception as e:
        print(f"Error generating variants: {e}")
        raise e


def analyze_candidate_bridge(api_key: str, twin_profile: str, candidate_name: str, candidate_profile: str, candidate_posts: str, screenshot_path: str = None, posts_screenshot_path: str = None, connection_count: Optional[int] = None, hiring_badge_status: Optional[str] = None) -> dict:
    """
    Stage 1: Multi-Agent Analysis Pipeline.
    Runs Profile Agent, Company Agent, Relationship Strategy Agent, Personalization Agent, and Context Synthesizer.
    Returns a unified dict containing structured JSONs, metrics, and retro-compatible keys.

    connection_count and hiring_badge_status are the real values off the Connection row
    (parsed from the PDF or entered by the user), passed straight through to the
    Relationship Strategy Agent instead of letting it re-guess either one.
    """
    # 1. Profile Intelligence
    profile_intel = run_profile_intelligence_agent(api_key, candidate_name, candidate_profile, candidate_posts, screenshot_path, posts_screenshot_path)

    # 2. Company Intelligence
    company_intel = run_company_intelligence_agent(api_key, profile_intel)

    # 3. Strategy
    strategy_intel = run_relationship_strategy_agent(api_key, profile_intel, company_intel, connection_count, hiring_badge_status)
    
    # 4. Personalization Hooks
    personalization_hooks = run_personalization_agent(api_key, profile_intel, company_intel, profile_intel.get("screenshot_observations"))
    
    # 5. Synthesize Context Summary
    context_summary = generate_context_summary(api_key, profile_intel, company_intel, strategy_intel, personalization_hooks)
    
    return {
        "profile_intelligence": json.dumps(profile_intel),
        "company_intelligence": json.dumps(company_intel),
        "relationship_strategy": json.dumps(strategy_intel),
        "personalization_data": json.dumps(personalization_hooks),
        "context_summary": context_summary,
        
        # New platform metrics and direct attributes
        "current_company_years_experience": profile_intel.get("current_company_years_experience", 0.0),
        "networking_score": strategy_intel.get("networking_score", 5.0),
        "reply_probability": strategy_intel.get("reply_probability", 50.0),
        "hiring_probability_score": strategy_intel.get("hiring_probability_score", "unknown"),
        "is_decision_maker": strategy_intel.get("is_decision_maker", "no"),
        "referral_potential": strategy_intel.get("referral_potential", "medium"),
        "networking_difficulty": strategy_intel.get("networking_difficulty", "medium"),
        "conversation_starter": personalization_hooks.get("conversation_starter", ""),
        "avoid_points": personalization_hooks.get("avoid_points", ""),
        "best_message_type": strategy_intel.get("strategy", "Technical Curiosity"),
        
        # Backward compatibility fields for DB and models
        "why_person": profile_intel.get("why_person") or strategy_intel.get("reason") or "Worth reaching out.",
        "bridge": profile_intel.get("bridge") or strategy_intel.get("strategy") or "Shared professional background.",
        "best_angle": profile_intel.get("best_angle") or strategy_intel.get("best_conversation_angle") or "Shared Domain"
    }


def generate_outreach_variants(api_key: str, twin_profile: str, candidate_name: str, candidate_profile: str, candidate_posts: str, bridge_data: dict, tone_examples: str = "", sender_name: str = "the user") -> dict:
    """
    Stage 2: Message Writing Agent.
    Runs the writing agent using synthesized intermediate outputs.
    """
    # Load JSON structures
    profile_intel = json.loads(bridge_data.get("profile_intelligence") or "{}")
    company_intel = json.loads(bridge_data.get("company_intelligence") or "{}")
    strategy_intel = json.loads(bridge_data.get("relationship_strategy") or "{}")
    personalization_hooks = json.loads(bridge_data.get("personalization_data") or "{}")
    context_summary = bridge_data.get("context_summary") or "Outreach targets backend and AI domains."

    return run_message_writing_agent(
        api_key=api_key,
        profile_json=profile_intel,
        company_json=company_intel,
        strategy_json=strategy_intel,
        personalization_json=personalization_hooks,
        context_summary=context_summary,
        twin_profile=twin_profile,
        tone_examples=tone_examples,
        sender_name=sender_name,
    )


def generate_thread_followup(api_key: str, twin_profile: str, candidate_profile: str, thread_history: list, user_intent: str = None, sender_name: str = "the user") -> str:
    """
    Generates a follow-up reply in an ongoing chat thread context.
    thread_history is a list of dicts: [{"sender": "user"|"connection", "message": "..."}]
    """
    system_instruction = (
        f"You are {sender_name}'s LinkedIn message assistant. You are drafting a follow-up message in an ongoing "
        "conversation thread. You write naturally, concisely, and with low pressure, like a real person continuing "
        "a real conversation, not a template. Never use an em dash or en dash. Never use AI-cliche phrasing "
        "('delve', 'leverage', 'excited to connect', 'hope this finds you well', 'circle back', 'touch base'). "
        "Contractions are normal. Vary sentence length. Say the specific thing, not the vague polished version of it."
    )

    # Format thread history
    history_str = ""
    for msg in thread_history:
        sender_label = f"{sender_name} (You)" if msg["sender"] == "user" else "Connection"
        history_str += f"{sender_label}: {msg['message']}\n"

    prompt = f"""
    {sender_name.upper()} (USER) PROFILE:
    {twin_profile}
    
    CANDIDATE PROFILE CONTEXT:
    {candidate_profile}
    
    CHRONOLOGICAL CONVERSATION HISTORY:
    {history_str}
    
    USER'S LATEST INTENT OR DIRECTIVE:
    {user_intent or "Respond naturally, continuing the conversation politely, moving gently toward a chat/referral if they seem open, or concluding gracefully if they seem busy."}
    
    Writing Rules:
    - Do not repeat your first message.
    - Write a short, conversational response (usually 2 to 4 sentences).
    - Respect what the candidate said. Do not push if they said no.
    - No forbidden buzzwords ("delve", "tapestry", "hope this finds you well").
    - Respond only with the message text. Do not include headers, tags, explanations, or quotes.
    """

    try:
        reply_text = _call_gemini(api_key, system_instruction, prompt)
        return clean_unicode_text(reply_text.strip())
    except Exception as e:
        return f"Error generating follow-up: {str(e)}"


def _clean_email_placeholders(text: str, candidate_name: str, sender_name: str) -> str:
    """
    Safety net for the rare case (usually a near-empty TwinAgent profile) where
    the model falls back to a bracketed placeholder instead of a real name,
    since a literal "[Your Name]" reaching a draft the user sends is worse
    than the plain fallback name already computed in Python.
    """
    if not text:
        return text
    text = re.sub(r'\[\s*(Candidate\s*)?Name\s*\]', candidate_name, text, flags=re.IGNORECASE)
    text = re.sub(r'\[\s*Your\s*Name\s*\]', sender_name, text, flags=re.IGNORECASE)
    text = re.sub(r'\[\s*Sender\s*Name\s*\]', sender_name, text, flags=re.IGNORECASE)
    return text


CONTACT_STATUS_STANDARD = "standard"
CONTACT_STATUS_COLD = "cold"
CONTACT_STATUS_MESSAGED_NO_REPLY = "messaged_no_reply"
CONTACT_STATUS_MESSAGED_REPLIED = "messaged_replied"

MODIFIER_REFERRAL = "referral"
MODIFIER_PUNCHY_OPENER = "punchy_opener"

LENGTH_SHORT = "short"
LENGTH_MID = "mid"
LENGTH_LONG = "long"


def _length_instruction(length: str) -> str:
    """
    The old fixed 80-130 word cap was making every email feel clipped, even
    ones with a real reason to run longer (a referral ask needs a sentence
    more than a technical question does, a reply to a genuine reply thread
    earns more room than a cold open). Length is now the user's call.
    """
    if length == LENGTH_SHORT:
        return (
            "- Length: short and direct, 50 to 90 words in the body. Say the one thing and stop. Cut "
            "every sentence that isn't the hook, the one line of context, and the ask.\n"
        )
    if length == LENGTH_LONG:
        return (
            "- Length: no strict word cap. Take the room you actually need to make the point properly, "
            "a second concrete detail, a fuller thought, more of the honest voice. This is permission to "
            "not cut a sentence that's earning its place, not permission to pad or ramble. Every sentence "
            "still has to be one a real person would say, and it should still feel tight for its length, "
            "not stretched. If the honest version is short, it's fine for it to stay short.\n"
        )
    # LENGTH_MID (default): a bit more breathing room than the old hard cap.
    return (
        "- Length: 110 to 160 words in the body. Enough room for the hook, one real line of context, "
        "and an ask that doesn't feel rushed. Still tight, not padded.\n"
    )


def _contact_status_block(contact_status: str, sender_name: str) -> str:
    """
    The one thing about a cold email that changes everything else: has this
    person heard from the sender before, and how did that go. Each branch
    below tells the model a different true thing to open with instead of
    guessing at a shared history that may or may not exist.
    """
    if contact_status == CONTACT_STATUS_MESSAGED_REPLIED:
        return (
            "SITUATION: THEY ALREADY REPLIED TO YOU ON LINKEDIN.\n"
            "This is not a cold email. You are continuing a conversation that already started on LinkedIn, "
            "moving it to email because it deserves more room than a DM thread gives it. Skip the formal "
            "self-introduction entirely, they already know who you are. Open by picking up a specific, real "
            "thread from what they actually said in the conversation below, not a generic 'great chatting' "
            "line. Reference one concrete thing they said or asked, and build the email on it. This should "
            "read like an email from someone they already have a rapport with, warmer and more specific than "
            "a first-touch cold email, never a repeat of the introduction they already got.\n\n"
        )
    if contact_status == CONTACT_STATUS_MESSAGED_NO_REPLY:
        return (
            "SITUATION: YOU MESSAGED THEM ON LINKEDIN AND THEY HAVEN'T REPLIED YET.\n"
            "Do not write this as a follow-up nag or imply they owe you a response, LinkedIn requests get "
            "lost or ignored for reasons that have nothing to do with interest. Acknowledge it in one short, "
            "low-key line, not an apology and not a guilt trip ('figured I'd try email too, in case LinkedIn "
            "buried it' is the right register, not 'following up on my message'). Then this becomes a normal "
            "cold email: same rules as a first-touch email otherwise, lead with a real hook, self-intro in "
            "one line after. Treat email as a second, lower-pressure channel, not a repeat of the same pitch "
            "with more urgency.\n\n"
        )
    if contact_status == CONTACT_STATUS_COLD:
        return (
            "SITUATION: NO PRIOR CONTACT OF ANY KIND. THIS IS THE FIRST TIME YOU ARE REACHING THIS PERSON.\n"
            "Do not reference LinkedIn, a prior message, or any shared history, because none exists. Write it "
            "as a genuine first introduction.\n\n"
        )
    # CONTACT_STATUS_STANDARD: no explicit framing either way, the default baseline.
    return ""


def _style_modifier_blocks(style_modifiers: List[str]) -> str:
    blocks = []
    if MODIFIER_REFERRAL in style_modifiers:
        blocks.append(
            "STYLE REQUIREMENT: THE ASK IN THIS EMAIL MUST BE A REFERRAL, NOT A QUESTION.\n"
            "The user has explicitly chosen a referral ask for this email. This is not optional and it "
            "overrides every other instruction about what the ask should be, including the DECIDED STRATEGY "
            "section's 'Do' if that section suggests a different kind of ask (like a technical question), "
            "and the general guidance elsewhere about not asking founders or senior leaders for referrals. "
            "If a specific open role or team is known from the research, name it. If not, ask generally for "
            "a referral or introduction into the company for roles matching the sender's actual background. "
            "The hook (observation or question) still opens the email and earns the ask, but the email must "
            "end by actually asking them to refer or introduce the sender, in one plain sentence, with a "
            "real out ('totally fine if that's not something you can do').\n\n"
        )
    if MODIFIER_PUNCHY_OPENER in style_modifiers:
        blocks.append(
            "STYLE REQUIREMENT: PUNCHY, EYE-CATCHING OPENING LINE.\n"
            "The first sentence should have more energy than the usual measured opener, a bold claim, a "
            "sharp specific detail, an unexpected angle, something that makes the reader's eyebrows go up "
            "for a second. Punchy does not mean gimmicky or clickbait, it still has to be true and specific "
            "to this person, it just lands with more force than a polite observation. Keep everything else "
            "(no em dashes, no exclamation marks, honesty rules) exactly as strict.\n\n"
        )
    return "".join(blocks)


def generate_outreach_email(
    api_key: str,
    twin_profile: str,
    candidate_name: str,
    candidate_email: str,
    candidate_profile: str,
    bridge_data: dict,
    tone_examples: str = "",
    sender_name: str = "the user",
    contact_status: str = CONTACT_STATUS_STANDARD,
    style_modifiers: Optional[List[str]] = None,
    conversation_context: str = "",
    length: str = LENGTH_MID,
    custom_instructions: str = "",
) -> dict:
    """
    Writes a real outreach EMAIL (subject + body), distinct from the short-form
    LinkedIn DM variants. Email is a different medium: more room, a subject line
    that has to earn the open, and a reader who is likely skimming in a crowded
    inbox. Draws its facts from the TwinAgent profile, so when the user's resume
    is re-uploaded, future emails automatically reflect the newer background.

    `contact_status` picks which real-world situation this email is actually
    being sent into (cold, already messaged and ignored, already messaged and
    replied), since that changes what's honest to say in the opening lines.
    `style_modifiers` are additive choices on top of that (asking for a
    referral, a punchier opening) the user can pick regardless of contact
    status. `length` controls how much room the email gets. `custom_instructions`
    is free text the user typed about this specific email (a situation to
    explain, a thing to mention, an instruction of their own), weighed
    alongside everything else rather than replacing it. All of these are
    surfaced as an explicit picker in the UI rather than generating every
    combination up front, since most of them are irrelevant to any given person.
    """
    style_modifiers = style_modifiers or []
    try:
        profile_intel = json.loads(bridge_data.get("profile_intelligence") or "{}")
        company_intel = json.loads(bridge_data.get("company_intelligence") or "{}")
        strategy_intel = json.loads(bridge_data.get("relationship_strategy") or "{}")
        personalization = json.loads(bridge_data.get("personalization_data") or "{}")
    except Exception:
        profile_intel, company_intel, strategy_intel, personalization = {}, {}, {}, {}

    context_summary = bridge_data.get("context_summary") or ""
    skip_formal_intro = contact_status == CONTACT_STATUS_MESSAGED_REPLIED

    system_instruction = (
        "You write outreach emails that get replies, in the voice of the user described below. "
        "You are not a marketing copywriter and you are not an assistant announcing itself. You are "
        "writing as this person, to another person, one human to another.\n\n"

        "THE READER GETS A HUNDRED EMAILS A DAY. YOURS HAS ABOUT SIX WORDS TO SURVIVE.\n"
        "They are skimming. They decide from the subject line and the first sentence alone, before they "
        "have consciously decided to read anything. Write for that moment, not for a careful reader who "
        "does not exist.\n\n"

        + _contact_status_block(contact_status, sender_name) +

        ("HOW TO OPEN THE EMAIL.\n"
        "Lead with a brief, natural self-introduction, one sentence, stated the way a person actually talks "
        "about themselves, not a resume line and not the tired 'Hi X, I'm Y, a student at Z' template. State "
        "who you are and what you actually do right now, plainly, then move immediately into the real reason "
        "you're writing. The self-intro earns its place by being short and specific (their actual current "
        "role and one concrete thing they work on), never a list of credentials.\n\n"
        "Immediately after that one line, the email needs a real hook, chosen from whichever of these the "
        "research actually supports:\n"
        "  1. THE SPECIFIC OBSERVATION. Name a real technical decision, tradeoff, or piece of work they "
        "own, precise enough that it could not be sent to anyone else. Specificity is the proof a human "
        "wrote this, and it flatters without complimenting.\n"
        "  2. THE QUESTION ONLY THEY CAN ANSWER. A genuine, concrete question about how their system or "
        "team handles something. People feel a pull to answer a question they are uniquely qualified for. "
        "It costs them one sentence to reply, which is the point.\n"
        "  3. THE NOTICED PATTERN. Point out something real about their trajectory or their company's "
        "direction that shows you thought about it, not just read a title.\n"
        "  4. THE HONEST OPEN. When the research is genuinely thin, say the true thing in a plain, "
        "slightly disarming way and get straight to the ask. Sincerity beats manufactured familiarity, "
        "and a short honest email outperforms a padded one.\n\n") if not skip_formal_intro else
        ("HOW TO OPEN THE EMAIL.\n"
        "No self-introduction, covered above: they already know who you are from the LinkedIn thread. Open "
        "directly on the specific thing from that conversation you're picking back up.\n\n") +

        "Leave one thread hanging. The best emails create a small, honest curiosity gap: a question posed "
        "and not answered, a specific problem named and not resolved. Do not explain everything. Give them "
        "a reason to want to write back, not a document to file away.\n\n"

        + _style_modifier_blocks(style_modifiers) +

        "BE WARM AND LOW-PRESSURE, NOT CLEVER.\n"
        "Specific does not mean sharp, and confident does not mean pushy. This email is one person asking "
        "another for a small piece of their time, and it should feel like that: genuine, a little humble, "
        "easy to say no to. Two things make that land. First, give them a real out, in their own words, "
        "near the ask ('no worries if you're slammed', 'totally fine if not'). Second, never imply they owe "
        "you a reply, never guilt ('I know you're busy but...' used as leverage), and never chase a clever "
        "line at the cost of sounding like a person. If a sentence would make you wince to receive it from "
        "a stranger, rewrite it plainer.\n"
        "Warmth is not flattery. Do not compliment them to buy goodwill. Being specific about their actual "
        "work, and being brief with their time, IS the respect.\n\n"

        "Never open with a fake-urgency or gimmick line, and never announce what the email is or is not. "
        "Writing 'this is not a template' or 'this is not an AI email' is self-defeating: it puts the "
        "suspicion in their head, spends the most valuable line in the email on defending yourself, and "
        "proves nothing because anyone can type it. Prove it by being specific instead.\n\n"

        "THE REST OF THE EMAIL:\n"
        "- Subject line: write it LAST, after the body exists, and make it the headline of the specific "
        "point the email actually makes. It must preview the real question or idea inside, not describe "
        "the recipient's job. 'building developer tools at console' is a label, it tells them something "
        "they already know about themselves and gives no reason to open. If the email asks where they draw "
        "the line between backend and client logic, the subject is about THAT.\n"
        "  Test it: reading only the subject, could they guess what the email asks? And does the subject "
        "connect directly to the first sentence of the body? If the subject and the opening line are about "
        "different things, the email feels stitched together and gets closed.\n"
        "  3 to 7 words, sentence case, concrete. Never use: 'Exciting Opportunity', 'Quick Question', "
        "'Reaching Out', 'Connecting', 'Introduction', exclamation marks, or emoji.\n"
        "- The ask must be small, singular, and answerable in two sentences without scheduling anything. "
        "One ask per email.\n"
        + _length_instruction(length) +
        "- End on the ask or a light out ('no worries if not'), never on a sign-off cliche.\n\n"

        "HOW TO SOUND HUMAN AND NOT LIKE A LANGUAGE MODEL:\n"
        "- Never use an em dash or en dash. Not once. If a sentence wants one, split it into two sentences or "
        "use a comma, a period, or 'and'/'but'. Em dashes are the single clearest tell that a machine wrote this.\n"
        "- Use contractions the way people actually type: I'm, I've, it's, that's, don't, wouldn't.\n"
        "- Vary sentence length hard. A long one, then a short one. Uniform medium-length sentences read as generated.\n"
        "- Write it the way you'd type it, not the way you'd format it. A short fragment on its own is fine "
        "('Long story.'). Starting a sentence with 'And' or 'But' is fine. One aside in parentheses is fine. "
        "Perfectly balanced, evenly weighted sentences are the tell.\n"
        "- Let one small human thing through: an admission ('I got this wrong for months'), a mild opinion, "
        "a specific frustration. Flawless and neutral reads as generated. A person has a point of view.\n"
        "- Do not repeat their name after the greeting. Using someone's name mid-email is a sales tactic and "
        "everyone can feel it.\n"
        "- Read the finished email out loud in your head. If any sentence is one you would never actually say "
        "to a person, rewrite it in the words you would really use.\n"
        "- Banned phrases, absolutely no exceptions: 'I hope this email finds you well', 'I hope you're doing well', "
        "'I wanted to reach out', 'I came across your profile', 'I was impressed by', 'I stumbled upon', 'as I was "
        "going through', 'delve', 'leverage', 'synergy', 'unlock', 'game-changer', 'passionate about', 'circle back', "
        "'touch base', 'pick your brain', 'thought leader', 'innovative', 'cutting-edge', 'in today's fast-paced "
        "world', 'navigate the landscape', 'I'd love to connect', 'excited to connect', 'Looking forward to hearing "
        "from you', 'Looking forward to connecting', 'Talk soon', 'Thanks in advance', 'at your earliest "
        "convenience', 'reach out if', 'let me know your thoughts'.\n"
        "- No stacked adjectives and no praise inflation ('incredible work', 'truly inspiring', 'amazing journey'). "
        "Describe concretely what they did. Specificity IS the compliment.\n"
        "- No listing two or more of their technologies/skills back at them in one clause ('your work with X, Y "
        "and Z') as a substitute for an actual observation. A list is not a thought.\n"
        "- No exclamation marks. Genuine interest reads as interest without one.\n"
        "- No rhetorical filler questions used as a paragraph transition ('Ever wonder how...', 'What if...'). "
        "The one real question in the email is the ask itself, not a warm-up act.\n"
        "- No bullet points, no headers, no bold. This is an email between two people, not a deck.\n"
        "- Sign off plainly: 'Thanks,' or 'Best,' then the name. Nothing more elaborate.\n\n"

        "HANDLING MISSING DATA:\n"
        "Some fields below may read 'Unknown' or 'None available' because the research didn't turn it up. Never "
        "write the word 'Unknown' into the email, and never reference a field that says it or apologize for not "
        "knowing something ('I couldn't find much about your role, but...'). Silently write around it: build the "
        "email only from what the profile actually established. If most fields are Unknown, that's a signal to "
        "use the HONEST OPEN and keep the email short, not a gap to paper over with invented specifics.\n\n"

        "HONESTY RULES, THESE OVERRIDE EVERYTHING ELSE:\n"
        "- Only state facts about the user that appear in the profile provided. Never invent a job, a school, a "
        "metric, a mutual connection, or a shared experience that is not there.\n"
        "- Never claim to have used their product, read their paper, or attended their talk unless the provided "
        "context explicitly says so.\n"
        "- If the research context is thin, write a shorter, plainer email. A short honest email beats a long "
        "email padded with invented familiarity.\n"
        "- Never state visa or work-authorization status (OPT, CPT, H1B, needs sponsorship, etc.) unless the "
        "email is explicitly and specifically about sponsorship. It's background context for judging what ask "
        "is appropriate, not something to volunteer in a cold email the recipient didn't ask about.\n\n"

        "CALIBRATION, showing what a good self-intro plus hook looks like together. The sender's status in "
        "these examples ('a CS Master's student') is illustrative only, it is NOT what to write. Always pull "
        "the sender's actual current status from the WHO IS WRITING THIS EMAIL section below, not from these "
        "examples, since that profile changes over time (e.g. they may have since graduated or changed roles).\n\n"

        "WEAK, because the self-intro is a résumé line and the rest is generic:\n"
        "  Subject: building developer tools at console\n"
        f"  'Hi Adithya, I'm {sender_name}, [whatever the sender's current status actually is] and a software "
        "engineer building full-stack AI systems at [their actual company]. I noticed your work spanning native iOS and web "
        "frameworks like React and Vue while building developer tools at Console...'\n"
        "  Why it fails: the self-intro reads like a LinkedIn headline, and the observation that follows is a "
        "list of technologies scraped from a profile, not a thought. Nothing here is unanswerable, so nothing "
        "gets answered. And the subject just restates the recipient's own job back at them, which tells "
        "them nothing they do not know and previews none of the actual question below.\n\n"

        "STRONG, a short natural self-intro immediately followed by a question only this person can answer, "
        "with a subject that previews it:\n"
        "  Subject: where you draw the shared-logic line\n"
        f"  'Hi Adithya, I'm {sender_name}, [one plain clause on the sender's actual current status, pulled "
        "from the profile below]. When you're shipping a developer tool across native iOS and web at the "
        "same time, where do you draw the line on shared logic? I keep landing on duplicating it and "
        "regretting it about a month later.\n\n"
        "  If you have a minute, I'd genuinely like to know how Console handles it. No worries if not.'\n"
        "  Why it works: the self-intro is one plain clause, not a pitch, and it immediately hands off to a "
        "real technical question aimed at their actual daily problem. It admits something ('regretting it') "
        "which reads human. The ask costs them two sentences. And the subject is the headline of that same "
        "question, so opening the email delivers exactly what the subject promised.\n\n"

        "The STRONG example above is an engineer-to-engineer email. The register has to shift with who is "
        "receiving it, and the two below show how. Same rules throughout: a short honest self-intro, then "
        "the recipient, the ask is small, and there is a real out at the end. Only the substance of the ask "
        "changes. As above, every bracketed part is filled from the sender's actual profile, never from "
        "these examples.\n\n"

        "RECRUITER / TALENT. They are not going to debate architecture with you, so do not ask them to. "
        "Be concrete about what you are and what you want, and make the reply cheap:\n"
        "  Subject: whether the [role type] pipeline is open\n"
        f"  'Hi [name], I'm {sender_name}, [one plain clause on current status]. Are you still filling "
        "[specific role or team they posted about], or has that closed? If it's open I'll send a proper "
        "application. If it's not, I'd rather not clog your inbox.\n\n"
        "  Either way, thanks. No worries if you're buried.'\n"
        "  Why it works: it asks one binary question they can answer in four words, it respects that their "
        "inbox is the worst inbox in the company, and it does not pretend to be a peer conversation.\n\n"

        "FOUNDER / VP / DIRECTOR. Unless the referral style requirement above says otherwise, do not ask for "
        "a meeting, a coffee chat, or a referral. Their scarcest resource is attention, and a meeting request "
        "from a stranger is the most expensive thing you can ask for. Ask one sharp question about a decision "
        "they actually made:\n"
        "  Subject: the [specific bet or decision] call\n"
        f"  'Hi [name], I'm {sender_name}, [one plain clause on current status and why this matters to them "
        "specifically]. You moved [specific thing their company did] before most people in the space did. "
        "Was that a conviction call or did the constraints just force it?\n\n"
        "  Genuinely curious, and no reply needed if you're heads-down.'\n"
        "  Why it works: senior people will answer a question about their own judgment when they will ignore "
        "everything else, because it is the one thing nobody else can answer. It asks for a sentence, not a "
        "calendar slot, and it gives them an explicit exit.\n\n"

        "Pick the register that matches the recipient's actual seniority from the profile below. Match the "
        "STRONG pattern. Never the WEAK one."
    )

    conversation_section = ""
    if conversation_context:
        conversation_section = f"""
    YOUR PRIOR LINKEDIN CONVERSATION WITH THEM, USE THIS AS REAL SHARED HISTORY:
    {conversation_context}
    """

    custom_instructions_section = ""
    if custom_instructions.strip():
        custom_instructions_section = f"""
    THE USER'S OWN INSTRUCTIONS FOR THIS SPECIFIC EMAIL, WEIGH THIS ALONGSIDE EVERYTHING ELSE ABOVE, IT DOES
    NOT REPLACE IT:
    {custom_instructions.strip()}
    Treat anything here about the sender or the situation (timing, a fact not in the profile above, a
    specific thing to mention, an instruction about tone or approach) as true and worth using, the user is
    the authority on their own situation. It does not grant permission to invent anything about the
    RECIPIENT that isn't in the research above, the honesty rules there still apply to them.
    """

    prompt = f"""
    WHO IS WRITING THIS EMAIL (the user). Every factual claim about the sender must come from here:
    {twin_profile}

    THE USER'S OWN WRITING SAMPLES, MATCH THIS VOICE:
    {tone_examples or "No samples provided. Default to plain, direct, warm but not effusive."}

    WHO IT IS GOING TO:
    - Name: {candidate_name}
    - Email: {candidate_email}
    - Role: {profile_intel.get("role") or profile_intel.get("title") or "Unknown"}
    - Company: {profile_intel.get("company") or "Unknown"}
    - Seniority: {profile_intel.get("seniority") or "Unknown"}
    - Technologies they work with: {profile_intel.get("technologies") or "Unknown"}
    - Their recent activity: {profile_intel.get("recent_posts") or "None available"}

    THEIR COMPANY:
    - Type / stage: {company_intel.get("company_type") or "Unknown"} ({company_intel.get("company_stage") or "Unknown"})
    - Engineering culture: {company_intel.get("engineering_culture") or "Unknown"}

    THE DECIDED STRATEGY FOR THIS PERSON:
    {context_summary}
    - Do: {strategy_intel.get("dos")}{" (IGNORE this if it conflicts with the referral style requirement above, the referral wins)" if MODIFIER_REFERRAL in style_modifiers else ""}
    - Do NOT: {strategy_intel.get("donts")}

    SPECIFIC HOOKS WORTH USING:
    - {personalization.get("conversation_hooks")}
    - Motivation / career pattern: {personalization.get("motivation_hooks")}
    - Avoid mentioning: {personalization.get("avoid_points")}
    {conversation_section}
    {custom_instructions_section}
    Write one email. Respect the strategy above, especially the DO NOTs, UNLESS the referral style requirement
    above is active, in which case the ask is the referral and this paragraph's guidance about what kind of ask
    fits their seniority does not apply, the referral requirement wins regardless of seniority or role. If the
    referral requirement is not active, adjust the ask to their seniority instead: a founder or VP gets a
    thoughtful question about their direction and no favor request; a recruiter gets a clear statement of what
    role is being targeted and an offer to send a resume; an engineer gets a specific technical question they
    would enjoy answering.

    Before you write, decide the single most specific true thing you know about this person, and build the
    hook on that. If the only honest answer is "not much", use the honest open and keep the whole email on
    the short side rather than padding it with invented familiarity, even if a longer length was picked
    below, since an honest short email always beats a padded long one.

    Write the body first, then write the subject from whatever the body actually ended up asking.

    Then check your draft against these, and rewrite if any fail:
      - {"Does the email skip a formal self-introduction, since they already know who you are from the LinkedIn thread? If it re-introduces the sender, rewrite it." if skip_formal_intro else "Is there a short, natural one-line self-introduction near the start, before the hook? If the email jumps straight into the hook with no self-intro, or the self-intro reads like a résumé line, rewrite it."}
      - Could this exact hook be sent to a different person unchanged? If yes, it is not specific enough.
      - Does the subject preview the specific question the body asks, rather than describing the recipient's
        job or company? If someone read only the subject, could they guess what is being asked?
      - Do the subject and the hook point at the same thing? If they are about different topics, rewrite the
        subject to match the body.
      - Is there a real question or unresolved thread that makes replying feel natural?
      - {"Is the body between 50 and 90 words?" if length == LENGTH_SHORT else "Is the body between 110 and 160 words?" if length == LENGTH_MID else "Does the length actually earn its place, no padding or repeated points, even though there's no hard cap?"}
      - Are there any em dashes? There must be none.
      - Does the word "Unknown" appear anywhere, or does any sentence reference a field you didn't actually have
        data for? If yes, rewrite that sentence using only confirmed facts.
      - Are there any exclamation marks? There must be none.
      - Does the ask give them an easy, genuine out, in plain words? If refusing would feel awkward, add one.
      - {"Is the actual ask a referral or introduction, in plain words, not a technical question or anything else? If the email ends on a question instead of an actual referral ask, rewrite the ending so it asks for the referral." if MODIFIER_REFERRAL in style_modifiers else "Does the register match their seniority (peer question / recruiter binary / senior judgment call)?"}
      - Is their name used anywhere after the greeting? Remove it.
      - Is every sentence one a real person would actually say out loud? Rewrite any that isn't.
      - Does it read as a person with a point of view rather than a flawless neutral assistant?

    Return ONLY raw JSON, no markdown fences, with exactly these fields:
    - "subject": the subject line
    - "body": the full email body including the greeting and sign-off, with real line breaks between paragraphs
    """

    try:
        raw_output = _call_gemini(api_key, system_instruction, prompt, json_mode=True)
        cleaned_output = _strip_json_codeblock(raw_output)
        data = json.loads(cleaned_output)
        return {
            "subject": _clean_email_placeholders(
                clean_unicode_text(data.get("subject", "")).strip(), candidate_name, sender_name
            ),
            "body": _clean_email_placeholders(
                clean_unicode_text(data.get("body", "")).strip(), candidate_name, sender_name
            ),
        }
    except Exception as e:
        print(f"Error generating outreach email: {e}")
        return {"subject": "", "body": f"Failed to generate email: {e}"}


def generate_twin_understanding(api_key: str, twin_profile: str) -> str:
    """
    Plays back, in plain language, what the system actually understands about
    the user from everything they have given it. This exists so the user can
    catch a wrong reading before it quietly shapes hundreds of messages, which
    is otherwise invisible until a draft says something untrue about them.
    """
    system_instruction = (
        "You are summarising what you understand about one person, addressed directly to them, "
        "so they can check it and correct anything wrong. Write as 'You are...', not third person.\n"
        "Only state what the source material supports. Where something important is missing or "
        "ambiguous, say so plainly instead of filling the gap with a guess, and say what would "
        "sharpen it. Being wrong here is worse than being incomplete, because everything you write "
        "later is built on this.\n"
        "Plain prose in short paragraphs, no headers, no bullet lists, under 220 words. "
        "Never use an em dash or en dash. No filler openers, start with the substance."
    )

    prompt = f"""
    Here is everything currently known about this person:
    {twin_profile}

    Write back what you understand about them: what they do, what they are looking for,
    what they can credibly claim, and how they come across in writing. Then, in one short
    closing paragraph, name anything that is unclear or missing that would make your
    outreach on their behalf noticeably better.
    """

    try:
        return clean_unicode_text(_call_gemini(api_key, system_instruction, prompt).strip())
    except Exception as e:
        return f"Could not generate the summary: {e}"


def chat_about_twin_profile(api_key: str, twin_profile: str, history: list, message: str) -> dict:
    """
    Conversational way to correct or extend the profile. Returns both a reply
    and any durable facts worth persisting, so the conversation actually
    changes future output rather than being a throwaway chat window.
    """
    system_instruction = (
        "You are helping one person tell you about themselves so you can represent them accurately "
        "in networking outreach. Be curious and specific. Ask about the things that would most "
        "change how you write on their behalf: what they actually built and their part in it, what "
        "they want next, what they would rather not claim, and how formal they want to sound.\n"
        "Ask one question at a time. Keep replies under 90 words. Never use an em dash or en dash. "
        "No AI-cliche phrasing, no 'great question', no restating what they just said back to them.\n\n"
        "Return ONLY raw JSON with these fields:\n"
        '  "reply": what you say back to them\n'
        '  "learned": a durable, self-contained fact worth remembering permanently, written in third '
        'person (e.g. "Led the retrieval pipeline rewrite at their company, owning it end to end"). '
        'Use an empty string when the message carried nothing new worth keeping, such as a greeting '
        'or a question directed at you.'
    )

    history_text = ""
    for turn in (history or [])[-10:]:
        who = "Them" if turn.get("role") == "user" else "You"
        history_text += f"{who}: {turn.get('content', '')}\n"

    prompt = f"""
    WHAT YOU ALREADY KNOW ABOUT THEM:
    {twin_profile}

    CONVERSATION SO FAR:
    {history_text or "(this is the first message)"}

    THEIR NEW MESSAGE:
    {message}

    Reply to them, and capture anything durable worth remembering.
    Return ONLY raw JSON, no markdown fences.
    """

    try:
        raw = _call_gemini(api_key, system_instruction, prompt, json_mode=True)
        data = json.loads(_strip_json_codeblock(raw))
        return {
            "reply": clean_unicode_text(data.get("reply", "")).strip(),
            "learned": clean_unicode_text(data.get("learned", "")).strip(),
        }
    except Exception as e:
        return {"reply": f"Something went wrong on my side: {e}", "learned": ""}


def answer_analytics_question(api_key: str, question: str, analytics_context: str) -> str:
    """
    Free-form Q&A over the user's own outreach data. The caller serializes the
    aggregate stats plus a per-person summary into `analytics_context`, so the
    model reasons over real numbers instead of guessing.
    """
    system_instruction = (
        "You are a sharp, blunt analyst looking at one person's real job-search outreach data. "
        "Answer only from the data provided. If the data cannot answer the question, say so plainly "
        "and say what would need to be tracked to answer it, rather than inventing a number.\n"
        "Give the answer first, then the reasoning. Cite actual names and numbers from the data. "
        "Be concrete about what to do next. Never use an em dash or en dash. No corporate filler, "
        "no 'it's worth noting', no restating the question back. Keep it under 200 words unless the "
        "question genuinely needs more."
    )

    prompt = f"""
    HERE IS THE USER'S COMPLETE OUTREACH DATA:
    {analytics_context}

    THEIR QUESTION:
    {question}

    Answer it using only the data above.
    """

    try:
        return clean_unicode_text(_call_gemini(api_key, system_instruction, prompt).strip())
    except Exception as e:
        return f"Could not analyze that: {e}"


def analyze_conversation_screenshot(
    api_key: str,
    candidate_name: str,
    screenshot_path: str,
    thread_history: Optional[list] = None,
    sender_name: str = "the user",
) -> dict:
    """
    Reads a screenshot of a LinkedIn conversation and judges how it's actually
    going: is this person genuinely engaged, being politely vague, or clearly
    not interested, plus what to do next. Meant to be run per uploaded
    screenshot so a busy pipeline of replies can be triaged at a glance
    instead of re-reading every thread by hand.
    """
    system_instruction = (
        "You are a blunt, experienced networking coach reviewing a screenshot of a real LinkedIn "
        "conversation. Your job is to judge how genuinely engaged the other person is, not to be polite "
        "about it. Read tone, specificity, and effort in their replies, not just whether they replied at "
        "all. A fast one-line reply can be genuinely warm; a long reply can still be a generic brush-off. "
        "Never use an em dash or en dash."
    )

    history_str = ""
    if thread_history:
        for msg in thread_history:
            sender_label = f"{sender_name} (sent)" if msg.get("sender") == "user" else "Them (received)"
            history_str += f"{sender_label}: {msg.get('message', '')}\n"

    prompt = f"""
    Look at the attached screenshot of a LinkedIn conversation with {candidate_name}.

    {"PRIOR TYPED THREAD LOG FOR CONTEXT (older messages, may overlap with the screenshot):" if history_str else ""}
    {history_str}

    Judge the conversation and return a JSON object with these fields:
    - "verdict": one of "interested", "lukewarm", "vague", "not_interested". Use "interested" only when
      they show real specificity or initiative (asking a follow-up question, offering to help, naming a
      concrete next step). Use "vague" when they replied politely but generically, with nothing to act on.
      Use "lukewarm" when it's positive but noncommittal. Use "not_interested" when they declined or the
      tone clearly signals they don't want to continue.
    - "reason": 1-2 sentences on specifically what in their reply led to that verdict. Quote or paraphrase
      the actual telling detail, don't just restate the verdict.
    - "recommended_action": one concrete next step in plain language (e.g. "Follow up in about a week with
      a specific question about their work", "Let this one go, they were clear they're not interested",
      "Reply now, they asked you a direct question", "Keep it warm, no urgency needed").

    Return ONLY raw JSON. Do not include markdown code blocks or wrapper text.
    """

    contents = [prompt]
    try:
        import PIL.Image
        img = PIL.Image.open(screenshot_path)
        contents.append(img)
    except Exception as e:
        return {
            "verdict": "vague",
            "reason": f"Could not read the uploaded screenshot: {e}",
            "recommended_action": "Try re-uploading the screenshot.",
        }

    try:
        raw_output = _call_gemini(api_key, system_instruction, contents, json_mode=True)
        cleaned_output = _strip_json_codeblock(raw_output)
        data = json.loads(cleaned_output)
        verdict = data.get("verdict", "vague")
        if verdict not in ("interested", "lukewarm", "vague", "not_interested"):
            verdict = "vague"
        return {
            "verdict": verdict,
            "reason": clean_unicode_text(data.get("reason", "")),
            "recommended_action": clean_unicode_text(data.get("recommended_action", "")),
        }
    except Exception as e:
        return {
            "verdict": "vague",
            "reason": f"Analysis failed: {e}",
            "recommended_action": "Try again, or judge this one manually.",
        }
