# Deploying networKING.agent

Backend on Render's free tier, database on Neon (free Postgres), keep-alive
pings from cron-job.org, frontend on Vercel. Every piece of this is free
with no credit card required anywhere.

**Live right now:**
- Frontend: https://frontend-psi-seven-fptzxsze1f.vercel.app
- Backend: https://networking-agent-api.onrender.com
- Neon project: `networking-agent` (org "Rishindra", AWS US East 2)
- Keep-alive: cron-job.org job "keep networking-agent awake", every 10 min

If you ever need to redeploy from scratch (new Render service, rotated
Neon password, etc.), the steps below still apply, just repeat whichever
step changed and re-wire the URLs above.

Why this combination: Render's free web services have no persistent disk,
so the app can't keep using a local SQLite file, hence the Postgres swap.
Render's free tier also sleeps after 15 minutes of no traffic, which would
otherwise kill the QueueOrchestrator's background workers between visits,
hence the keep-alive pinger. Fly.io was the cleaner architectural fit (an
always-on box with a real volume) but as of 2026 it requires a card even
for its now-time-limited trial, so it's off the table per your call.

Total time: about 20 minutes, mostly account signups and waiting on the
first deploy. Every login step needs your own browser, so those parts are
yours to do; I can drive everything else once you hand me the resulting
URLs and connection strings.

## 1. Database: Neon (free Postgres)

1. Go to [neon.tech](https://neon.tech) and sign up (GitHub login is fastest, no card).
2. Create a new project, any name, any region close to you.
3. On the project dashboard, copy the **connection string** it gives you.
   It looks like:
   `postgresql://user:password@ep-xxxx.us-east-2.aws.neon.tech/dbname?sslmode=require`
4. Save that somewhere, you'll paste it into Render as `DATABASE_URL` in step 2.

(Supabase is an equally good free alternative if you'd rather use that,
same idea: sign up, create a project, grab the Postgres connection string
from Project Settings -> Database.)

## 2. Backend: Render

1. Go to [render.com](https://render.com) and sign up (GitHub login again, no card).
2. Push this repo to GitHub if it isn't already up to date (I'll handle the
   commit/push when you're ready).
3. In Render, click **New -> Blueprint**, connect your GitHub account, and
   pick this repo. Render will detect `render.yaml` at the repo root and
   pre-fill the service from it.
4. It'll ask you to fill in four environment variables it found marked as
   "sync: false" in the blueprint (kept out of the repo on purpose):
   - `DATABASE_URL`: the Neon connection string from step 1
   - `JWT_SECRET_KEY`: use the value already in your local `backend/.env`
   - `ENCRYPTION_KEY`: same, from `backend/.env`
   - `CORS_ORIGINS`: leave this as `http://localhost:3000` for now, we'll
     update it once the Vercel URL exists (step 4)
5. Click **Apply**. Render builds and deploys. First build takes a few
   minutes. When it's live, you'll get a URL like
   `https://networking-agent-api.onrender.com`.
6. Confirm it's actually up:
   ```bash
   curl https://networking-agent-api.onrender.com/health
   ```
   Should return `{"status":"ok"}`.

Using the same `JWT_SECRET_KEY` / `ENCRYPTION_KEY` you already have locally
matters: if Render generated fresh ones instead, every existing session
would be invalidated and any API key you'd already encrypted and stored
would become undecryptable. Since this is a brand-new Postgres database
anyway (nothing to preserve there), this mostly matters if you want your
JWT signing to behave consistently between local dev and prod, but there's
no downside to just reusing the same values, so do that.

## 3. Keep the free tier awake: cron-job.org

Render's free tier spins the service down after 15 minutes of no incoming
requests. Since the background outreach queue needs to keep running even
when nobody's looking at the dashboard, ping it periodically:

1. Go to [cron-job.org](https://cron-job.org) and sign up (free, no card).
2. Create a new cron job:
   - URL: `https://networking-agent-api.onrender.com/health`
   - Schedule: every 10 minutes
3. Save it. That's the whole setup, it just needs to exist and fire.

This isn't a perfect always-on guarantee (a cold service can still take a
few seconds to wake if a ping happens to land right as it's spinning down),
but in practice it keeps the app responsive and the queue moving.

## 4. Frontend: Vercel

Already logged in via `vercel login` earlier in this session. From the
`frontend/` folder:

```bash
cd frontend
vercel link
```

Set the backend URL as an environment variable:

```bash
vercel env add NEXT_PUBLIC_BACKEND_URL production
```
Paste your Render URL (e.g. `https://networking-agent-api.onrender.com`)
when prompted.

Deploy:

```bash
vercel --prod
```

You'll get a URL like `https://networking-agent.vercel.app`.

## 5. Close the loop: let the frontend actually call the backend

Go back to Render, open the service's Environment tab, and update
`CORS_ORIGINS` to your real Vercel URL:

```
CORS_ORIGINS=https://networking-agent.vercel.app
```

(Comma-separate if you also want `http://localhost:3000` in there for
local dev against the prod backend.) Save, Render redeploys automatically
with the new value.

## 6. Verify end to end

1. Open the Vercel URL, register an account.
2. Add a Gemini API key under "API Key Workers" (free tier key from
   [Google AI Studio](https://aistudio.google.com/apikey)).
3. Add an outreach target.
4. Watch it move from Pending -> Processing -> Draft Ready.

If step 4 hangs, check the Render service logs (Render dashboard -> your
service -> Logs).

## Known limitation: profile screenshots

Uploaded LinkedIn screenshots are saved to local disk (`backend/uploads/`).
Render's free tier has no persistent disk, so uploaded screenshots will be
lost whenever the service restarts or redeploys. This doesn't affect
anything else (screenshots are an optional enrichment input, not required
for the pipeline to work), but if you want those to survive too, the fix
is routing uploads to a free object store (Supabase Storage pairs
naturally with a Supabase Postgres setup) instead of local disk. Not done
here since it's a real feature addition, not a deploy-config change, ask
if you want it.

## Notes on the "10 users" requirement

- The orchestrator spins up one background worker per active Gemini API
  key, per user, inside a single process. Render's free web service runs
  exactly one instance, which matches this design; don't scale it to
  multiple instances without also redesigning the orchestrator, since two
  instances would run duplicate, uncoordinated worker pools against the
  same database.
- SQLite's WAL mode change from earlier doesn't apply once you're on
  Postgres (it's a no-op there, guarded in `database.py`), Postgres already
  handles concurrent readers/writers properly on its own.
- The free Render machine is CPU-light work; the actual bottleneck at scale
  is Gemini API rate limits per key, which the existing key-pool failover
  in `orchestrator.py` already handles.
