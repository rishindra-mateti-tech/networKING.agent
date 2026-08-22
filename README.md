<p align="center">
  <img src="frontend/public/logo-full.png" alt="networKING.agent" width="420">
</p>

# networKING.agent

**A multi-agent AI system I built to research and draft networking outreach more thoughtfully. I still read, edit, and personally send every single message.**

**[Live Demo](https://frontend-psi-seven-fptzxsze1f.vercel.app)** (needs your own free Gemini API key to actually run anything, see "Running it locally" below for where to get one)

I'm Rishindra, an MS Computer Science student at Wright State University, building AI/ML systems (most recently as an AI Engineer Intern at ZUZU.AI, working on RAG pipelines and FastAPI backends). This is a personal project born out of a very unglamorous problem: doing real, well-researched networking outreach on LinkedIn (the kind that references someone's actual work instead of a generic "loved your profile!") takes real time per person. I wanted to see if I could build an agent system that does the *research* part well, so the time I spend is on judgment (who to reach out to, what to actually say, whether to hit send), not on re-reading the same profile five times to find something honest to say.

**If you got a LinkedIn message from me and ended up here out of curiosity: hi.** That message was real. I wrote it, read it over, and sent it myself, this project is just the thing that helped me get there. There's no LinkedIn bot, no bulk blasting, no API hook into LinkedIn's messaging at all. It reads a profile, does the research I'd otherwise do by hand, and drafts a few message options into my own dashboard for me to pick from, edit, and send myself. If you're wondering why the message referenced something specific about your work instead of a generic "great profile!", that's the part this project exists to do well.

## What it actually does

1. I drop in a LinkedIn profile (PDF export, or just paste details) for someone I'm curious about reaching out to.
2. A pipeline of Gemini-backed agents reads the profile and works out useful context: what they actually work on, what their company is like, what kind of ask (if any) would be appropriate for their seniority, and what's genuinely worth mentioning.
3. It drafts several message options, tuned so a VP's inbox gets treated differently from a recruiter's, and none of them are allowed to use AI-cliché phrases like "hope this finds you well" or "quick chat."
4. Everything lands in a Kanban board (Pending → Draft Ready → Sent → Replied → Closed) so I can track a real pipeline instead of losing track of who I talked to.
5. I review, personalize further if needed, and send it myself, from my own LinkedIn account, like a person.

## Why I actually built it this way (the engineering, not just the pitch)

- **Multi-agent pipeline, not one big prompt.** Profile Intelligence → Company Intelligence → Relationship Strategy → Personalization → Context Synthesis → Message Writing are separate agents with separate responsibilities, so the model writing the message is working from a structured brief instead of guessing.
- **Async worker orchestrator.** A `QueueOrchestrator` dynamically spins up a pool of background workers sized to how many Gemini API keys I have active, pulls from a pending queue, and handles rate-limit cooldown + automatic failover to standby keys without dropping a task.
- **Security-conscious by default.** JWT signing secrets and API-key encryption keys are generated per-install (never hardcoded in source), and stored Gemini API keys are encrypted at rest, not plaintext.
- **Full-stack**: FastAPI + SQLAlchemy backend, Next.js/React dashboard, JWT auth, Telegram and Slack notifications for when a draft's ready, PDF parsing for LinkedIn exports.

## Tech stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, SQLAlchemy (SQLite locally, Postgres in production) |
| AI | Google Gemini (`google-genai`), 5-stage agent pipeline |
| Auth | JWT (`python-jose`), bcrypt password hashing |
| Security | Fernet (AES) encryption at rest for API keys, per-install generated secrets |
| Frontend | Next.js, React, Tailwind |
| Ops | Async task orchestration with key-pool failover, Telegram bot + Slack webhook notifications |

## Running it locally

```bash
python run.py
```

This bootstraps a virtualenv, installs backend + frontend dependencies, and starts FastAPI on `:8000` and Next.js on `:3000`. On first run it auto-generates the JWT/encryption secrets into a local `.env` file (see `backend/.env.example`); nothing sensitive ships in this repo.

You'll need your own Gemini API key (free tier from [Google AI Studio](https://aistudio.google.com/apikey)), added from the app's "API Key Workers" screen after you sign up.

Deploying this somewhere real (Render + Neon Postgres + Vercel, entirely free, no card required): see [DEPLOY.md](DEPLOY.md).

***

*This is a personal side project, not a product. Feedback and PRs welcome, but expect it to keep evolving as I use it.*
