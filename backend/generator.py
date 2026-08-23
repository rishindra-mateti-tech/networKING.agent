import re
import json
import os
from typing import Optional
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
    keys run in true parallel — unlike the legacy `google.generativeai` module-global
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


def run_profile_intelligence_agent(api_key: str, name: str, profile_text: str, posts_text: str, screenshot_path: str = None) -> dict:
    """
    Agent 1: Profile Intelligence Agent
    Extracts name, role (title), seniority, company, follower count, connection count, education,
    technologies, mutual interests, recent posts, hiring badge status (ON/OFF), and screenshot visual details.
    """
    system_instruction = (
        "You are a Profile Intelligence Agent. Your job is to extract detailed professional profile details "
        "about a candidate from their LinkedIn PDF export and optional profile screenshot."
    )

    prompt = f"""
    Extract the following details from the LinkedIn profile of candidate: {name}.
    
    PROFILE PDF TEXT:
    {profile_text or "No PDF text provided."}
    
    RECENT POSTS TEXT:
    {posts_text or "No posts text provided."}
    
    Analyze the profile text and optional screenshot (if provided) to return a JSON object with the following fields:
    - "name": Candidate's full name.
    - "role": Current title/role.
    - "title": Current title (same as role).
    - "seniority": Seniority category. Must be one of: "CEO", "Founder", "Recruiter", "Senior SWE", "Principal Engineer", "Engineering Manager", "University Alum", "HR", "VP", "Director", "Other".
    - "company": Current company name.
    - "follower_count": Candidate's follower count if visible (e.g. "1,200", "50k", or "Under 500"). If not found, output "Under 500".
    - "connection_count": Candidate's connections count (integer or "500+").
    - "years_experience": Approximate total years of professional experience (float/number).
    - "education": Summary of their education (e.g. degrees, universities).
    - "mutual_interests": Any mutual interests, topics, or domains.
    - "technologies": Core programming languages, systems, stacks, or tools they work with.
    - "recent_posts": Summary of their recent activities/posts if provided.
    - "tone": Tone of their writing or posts (e.g., direct, technical, academic, casual).
    - "company_size": Estimate company size category: "Enterprise", "Mid-size", "Startup", "Scaleup".
    - "hiring_badge_status": Inferred "Open to Work" or "Hiring" banner/badge status. Output "ON" if they have an active "Open to Work" or "Hiring" badge, otherwise output "OFF".
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
            "connection_count": data.get("connection_count", "0"),
            "years_experience": float(data.get("years_experience") or 0.0),
            "education": clean_unicode_text(data.get("education", "")),
            "mutual_interests": clean_unicode_text(data.get("mutual_interests", "")),
            "technologies": clean_unicode_text(data.get("technologies", "")),
            "recent_posts": clean_unicode_text(data.get("recent_posts", "")),
            "tone": clean_unicode_text(data.get("tone", "")),
            "company_size": data.get("company_size", "Startup"),
            "hiring_badge_status": data.get("hiring_badge_status", "OFF"),
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
            "connection_count": "0",
            "years_experience": 0.0,
            "education": "",
            "mutual_interests": "",
            "technologies": "",
            "recent_posts": "",
            "tone": "professional",
            "company_size": "Startup",
            "hiring_badge_status": "OFF",
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


def run_relationship_strategy_agent(api_key: str, profile_json: dict, company_json: dict) -> dict:
    """
    Agent 3: Relationship Strategy Agent
    Decides the best outreach approach, calculates key networking metrics (networking score, reply probability,
    decision maker status, networking difficulty, referral potential, hiring probability), and establishes strict DOs and DONTs.
    """
    system_instruction = (
        "You are a Relationship Strategy Agent. Your job is to decide the best outreach approach, "
        "calculate networking intelligence metrics, and establish strict DOs and DONTs rules based on the candidate's seniority and company context."
    )

    prompt = f"""
    Determine the relationship strategy and networking metrics for contacting the following candidate:
    
    CANDIDATE PROFILE:
    - Name: {profile_json.get("name")}
    - Seniority Category: {profile_json.get("seniority")}
    - Role: {profile_json.get("role")}
    - Company: {profile_json.get("company")}
    - Follower Count: {profile_json.get("follower_count")}
    - Connection Count: {profile_json.get("connection_count")}
    - Hiring Badge Status: {profile_json.get("hiring_badge_status")}
    
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

        return {
            "networking_score": net_score,
            "reply_probability": reply_prob,
            "is_decision_maker": data.get("is_decision_maker", "no"),
            "networking_difficulty": data.get("networking_difficulty", "medium"),
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
    profile_url: Optional[str] = None
) -> dict:
    """
    Agent 5: Message Writing Agent
    Takes reasoning JSONs and the reasoning context summary, plus twin profile and tone guidelines.
    Writes exactly 5 objective-specific outreach message drafts in the voice of the user (Rishindra).
    Fills in the candidate's actual name and company instead of outputting placeholders like [Name].
    No conversational clichés are allowed. Follows explicit strategy guidelines.
    """
    candidate_name = profile_json.get("name", "there")
    candidate_company = profile_json.get("company", "your company")

    system_instruction = (
        "You are a Message Writing Agent. Your ONLY job is to draft outreach messages. "
        "You have NO reasoning responsibility. Follow the decided strategy, dos, donts, and context summary strictly. "
        "Write in the voice of the user (Rishindra). You must substitute actual candidate details (name, company) "
        "and never output bracketed placeholders like [Name] or [Company]. "
        "Rishindra's voice is highly polite, humble, requesting, and professional. Always acknowledge that their "
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
    USER DETAILS (RISHINDRA):
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
    
    Write exactly 5 message variants in the voice of Rishindra following these instructions:
    - Do not do any reasoning. Just output the drafts.
    - Strictly respect all DONTs and Things to Avoid.
    - Write short messages (usually 2 to 5 sentences) for variants 1-4.
    - Write a longer, natural message for variant 5 (Featured Draft) without word count restrictions, modeled after Rishindra's templates.
    - **CRITICAL**: Fill in actual candidate details. Substitute '[Name]' with '{candidate_name}' and '[Company]' with '{candidate_company}' directly in the drafts. Do NOT output bracketed placeholders like '[Name]' or '[Company]'.
    - **TONE RULE**: Make the drafts sound polite, humble, and requesting. You MUST include phrases like: 'I know your time is valuable, so there is absolutely no pressure', 'I would be incredibly grateful for any advice you could share', 'I would truly value your perspective', or 'If you ever have a few spare minutes to share your insights, I'd genuinely appreciate it'.
    - CRITICAL NEGATIVE CONSTRAINT: Never use an em dash (—) or en dash (–). Ban all AI clichés: "Hope this finds you well", "Hope you are doing well", "I was impressed by your profile", "Quick chat", "15-minute coffee chat", "delve", "leverage", "synergy", "unlock", "game-changer", "passionate about", "reaching out because", "pick your brain", "thought leader", "excited to connect", "would love to connect", "in today's fast-paced world", "navigate the landscape of", "incredible work", "truly inspiring", "Looking forward to hearing from you!", "Thanks in advance!".
    - COFFEE CHAT CONSTRAINT: If the candidate's seniority is Founder, CEO, VP, or Director, DO NOT request a coffee chat or a meeting in the Coffee Chat draft. Instead, write it as a brief, respectful request to connect/follow their work or ask a quick strategic question.
    
    FEW-SHOT TONE REFERENCE TEMPLATES:
    * Referral / Opportunity Inquiry:
      "Hi {candidate_name}, I'm Rishindra, currently an AI Engineer Intern at ZUZU.AI, where I build RAG pipelines and FastAPI backends. I saw that your team at {candidate_company} focuses on shipping fast, which caught my attention. With my background in backend engineering and building AI tools like CodeStory, I'm curious if your team is currently looking for additional engineering support. I know your time is valuable, so there is absolutely no pressure, but I would be grateful to connect and learn more about what you're building."
    
    * Low-Pressure Career Advice Request (Connection Accepted Follow-up):
      "Hi {candidate_name}, thanks for connecting. I'm currently finishing my Master's in CS at Wright State and working as an AI Engineer Intern at ZUZU.AI. I spent some time going through your profile, and I was genuinely impressed by your journey at {candidate_company}. I'm trying to learn from developers who have successfully navigated this path. If you ever have a few spare minutes, I'd be incredibly grateful for any advice or insights you could share on what skills are critical for your team. I know your time is valuable, so there is absolutely no pressure at all."
    
    * Alumni / Common Ground Builder:
      "Fellow Wright State Builder 👋 Hi {candidate_name}, fellow Wright State alum here. I came across your profile while learning about {candidate_company} and really enjoyed seeing how you approached building resilient engineering teams. I'm currently pursuing my MS in CS at WSU and working as an AI Engineer Intern at ZUZU.AI. If you ever have a spare moment to share your perspective on how you made that transition, I would truly value your guidance. No pressure at all."
    
    * Recruiter / TA Specialist Advice Request:
      "Hi {candidate_name}, Thank you for connecting. I'm a CS Master's student at Wright State University working on AI/ML projects, including an IEEE-published paper and the Google × Kaggle AI Agents Intensive. I know you support technical recruiting at {candidate_company}, so I wanted to ask very humbly — what would you recommend students like me focus on to become stronger candidates in the future? I know your time is valuable, so even a single line of advice would be something I'd be incredibly grateful for."
    
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
            # Replace bracketed candidate placeholders
            text = re.sub(r'\[\s*(Candidate\s*)?Name\s*\]', candidate_name, text, flags=re.IGNORECASE)
            text = re.sub(r'\[\s*(Candidate\s*)?Company\s*\]', candidate_company, text, flags=re.IGNORECASE)
            text = re.sub(r'\[\s*Your\s*Name\s*\]', "Rishindra", text, flags=re.IGNORECASE)
            text = re.sub(r'\[\s*Your\s*Company\s*\]', "ZUZU.AI", text, flags=re.IGNORECASE)
            
            # Direct text replaces
            text = text.replace("[Name]", candidate_name)
            text = text.replace("[Company]", candidate_company)
            text = text.replace("[Your Name]", "Rishindra")
            text = text.replace("[Your Company]", "ZUZU.AI")
            text = text.replace("[Role Name]", "Software Engineer")
            text = text.replace("[Role]", "Software Engineer")
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

        # Append Profile URL link to each draft variant if available
        if profile_url:
            clean_url = profile_url.strip()
            for key in ["referral", "coffee", "technical", "relationship", "featured", "short", "warm", "tech", "mixed"]:
                if key in variants and not variants[key].startswith("Failed to"):
                    variants[key] = f"{variants[key]}\n\nProfile Link: {clean_url}"

        return variants
    except Exception as e:
        print(f"Error generating variants: {e}")
        raise e


def analyze_candidate_bridge(api_key: str, twin_profile: str, candidate_name: str, candidate_profile: str, candidate_posts: str, screenshot_path: str = None) -> dict:
    """
    Stage 1: Multi-Agent Analysis Pipeline.
    Runs Profile Agent, Company Agent, Relationship Strategy Agent, Personalization Agent, and Context Synthesizer.
    Returns a unified dict containing structured JSONs, metrics, and retro-compatible keys.
    """
    # 1. Profile Intelligence
    profile_intel = run_profile_intelligence_agent(api_key, candidate_name, candidate_profile, candidate_posts, screenshot_path)
    
    # 2. Company Intelligence
    company_intel = run_company_intelligence_agent(api_key, profile_intel)
    
    # 3. Strategy
    strategy_intel = run_relationship_strategy_agent(api_key, profile_intel, company_intel)
    
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


def generate_outreach_variants(api_key: str, twin_profile: str, candidate_name: str, candidate_profile: str, candidate_posts: str, bridge_data: dict, tone_examples: str = "", profile_url: Optional[str] = None) -> dict:
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
        profile_url=profile_url
    )


def generate_thread_followup(api_key: str, twin_profile: str, candidate_profile: str, thread_history: list, user_intent: str = None) -> str:
    """
    Generates a follow-up reply in an ongoing chat thread context.
    thread_history is a list of dicts: [{"sender": "user"|"connection", "message": "..."}]
    """
    system_instruction = (
        "You are Rishindra's LinkedIn message assistant. You are drafting a follow-up message in an ongoing "
        "conversation thread. You write naturally, concisely, and with low pressure, like a real person continuing "
        "a real conversation, not a template. Never use an em dash or en dash. Never use AI-cliche phrasing "
        "('delve', 'leverage', 'excited to connect', 'hope this finds you well', 'circle back', 'touch base'). "
        "Contractions are normal. Vary sentence length. Say the specific thing, not the vague polished version of it."
    )

    # Format thread history
    history_str = ""
    for msg in thread_history:
        sender_label = "Rishindra (You)" if msg["sender"] == "user" else "Connection"
        history_str += f"{sender_label}: {msg['message']}\n"

    prompt = f"""
    RISHINDRA (USER) PROFILE:
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


def analyze_conversation_screenshot(
    api_key: str,
    candidate_name: str,
    screenshot_path: str,
    thread_history: Optional[list] = None,
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
            sender_label = "Rishindra (sent)" if msg.get("sender") == "user" else "Them (received)"
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
