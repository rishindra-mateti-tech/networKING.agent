# networKING.agent

**A multi-agent AI system I built to research and draft networking outreach more thoughtfully — I still read, edit, and personally send every single message.**

I'm Rishindra, an MS Computer Science student at Wright State University, building AI/ML systems (most recently as an AI Engineer Intern at ZUZU.AI, working on RAG pipelines and FastAPI backends). This is a personal project born out of a very unglamorous problem: doing real, well-researched networking outreach on LinkedIn — the kind that references someone's actual work instead of a generic "loved your profile!" — takes real time per person. I wanted to see if I could build an agent system that does the *research* part well, so the time I spend is on judgment (who to reach out to, what to actually say, whether to hit send), not on re-reading the same profile five times to find something honest to say.

**If you're a recruiter, founder, or someone I reached out to and ended up here out of curiosity: hi 👋** Nothing here auto-sends anything to anyone. There's no LinkedIn bot, no bulk blasting, no API hook into LinkedIn's messaging at all. Every message this generates is a draft that lands in my own dashboard for me to read, edit, and copy-paste myself. What you're looking at is the "research assistant + first draft" layer of something I'd have done manually anyway — and honestly, if this repo is how you found me, that probably means it worked.

## What it actually does

1. I drop in a LinkedIn profile (PDF export, or just paste details) for someone I'm curious about reaching out to.
2. A pipeline of Gemini-backed agents reads the profile and works out useful context: what they actually work on, what their company is like, what kind of ask (if any) would be appropriate for their seniority, and what's genuinely worth mentioning.
3. It drafts several message options — one respects that a VP's inbox is different from a recruiter's, and none of them are allowed to use AI-cliché phrases like "hope this finds you well" or "quick chat."
4. Everything lands in a Kanban board (Pending → Draft Ready → Sent → Replied → Closed) so I can track a real pipeline instead of losing track of who I talked to.
5. I review, personalize further if needed, and send it myself, from my own LinkedIn account, like a person.

## Why I actually built it this way (the engineering, not just the pitch)

- **Multi-agent pipeline, not one big prompt.** Profile Intelligence → Company Intelligence → Relationship Strategy → Personalization → Context Synthesis → Message Writing are separate agents with separate responsibilities, so the model writing the message is working from a structured brief instead of guessing.
- **Async worker orchestrator.** A `QueueOrchestrator` dynamically spins up a pool of background workers sized to how many Gemini API keys I have active, pulls from a pending queue, and handles rate-limit cooldown + automatic failover to standby keys without dropping a task.
- **Security-conscious by default.** JWT signing secrets and API-key encryption keys are generated per-install (never hardcoded in source), and stored Gemini API keys are encrypted at rest, not plaintext.
- **Full-stack**: FastAPI + SQLAlchemy backend, Next.js/React dashboard, JWT auth, Telegram notifications for when a draft's ready, PDF parsing for LinkedIn exports.

## Tech stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy, SQLite |
| AI | Google Gemini (`google-genai`), 5-stage agent pipeline |
| Auth | JWT (`python-jose`), bcrypt password hashing |
| Security | Fernet (AES) encryption at rest for API keys, per-install generated secrets |
| Frontend | Next.js, React, Tailwind |
| Ops | Async task orchestration with key-pool failover, Telegram bot notifications |

## Running it locally

```bash
python run.py
```

This bootstraps a virtualenv, installs backend + frontend dependencies, and starts FastAPI on `:8000` and Next.js on `:3000`. On first run it auto-generates the JWT/encryption secrets into a local `.env` file (see `backend/.env.example`) — nothing sensitive ships in this repo.

You'll need your own Gemini API key (free tier from [Google AI Studio](https://aistudio.google.com/apikey)), added from the app's "API Key Workers" screen after you sign up.

---

*This is a personal side project, not a product — feedback and PRs welcome, but expect it to keep evolving as I use it.*
