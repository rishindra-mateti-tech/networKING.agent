# Deploying networKING.agent

Backend on Fly.io (free, stays on, supports the persistent SQLite volume the
background workers need). Frontend on Vercel (free, built for Next.js).

Why not Render's free tier: it spins the process down after 15 minutes of no
traffic, which kills the QueueOrchestrator's background workers between
requests. Fly's free allowance keeps one small machine running continuously.

Total time: about 15 minutes, mostly waiting on builds. Two steps need your
own browser login (Fly and Vercel), so I can't run those for you.

## 1. Backend on Fly.io

Both CLIs (`flyctl`, `vercel`) are already installed on this machine. Open a
**new** terminal window first so the updated PATH takes effect, then log in
(opens a browser):

```bash
fly auth login
```

From the `backend/` folder, create the app (it will detect `fly.toml`, say
no to the "would you like to deploy now" prompt, we need to set secrets and
the volume first):

```bash
cd backend
fly launch --no-deploy --copy-config
```

If it says the app name `networking-agent-api` is taken, edit `app = "..."`
at the top of `fly.toml` to something unique, then continue.

Create the persistent volume (must match the region you picked, and the
`source = "networking_data"` name in `fly.toml`):

```bash
fly volumes create networking_data --size 1 --region iad
```

Set the JWT/encryption secrets so they survive redeploys. Use the values
already in your local `backend/.env` so nothing already encrypted breaks,
or generate fresh ones if this is a clean start:

```bash
fly secrets set JWT_SECRET_KEY="<value from backend/.env>" ENCRYPTION_KEY="<value from backend/.env>"
```

This part matters: without pinning these as Fly secrets, `config.py`
regenerates them on every redeploy, which logs every user out and makes
every previously-stored Gemini API key undecryptable. Do this before the
first deploy.

Deploy:

```bash
fly deploy
```

Your API is now live at `https://<your-app-name>.fly.dev`. Confirm it's up:

```bash
curl https://<your-app-name>.fly.dev/docs
```

## 2. Frontend on Vercel

Log in (opens a browser):

```bash
vercel login
```

From the `frontend/` folder:

```bash
cd frontend
vercel link
```

Set the backend URL as an environment variable (repeat for Production,
Preview, and Development if it asks, or just Production for now):

```bash
vercel env add NEXT_PUBLIC_BACKEND_URL production
```
Paste `https://<your-app-name>.fly.dev` when prompted.

Deploy:

```bash
vercel --prod
```

You'll get a URL like `https://networking-agent.vercel.app`.

## 3. Close the loop: allow the frontend to call the backend

Add the Vercel URL to the backend's CORS allowlist:

```bash
fly secrets set CORS_ORIGINS="https://networking-agent.vercel.app" --app <your-app-name>
```

(If you also want to keep using it locally, use a comma-separated list:
`CORS_ORIGINS=http://localhost:3000,https://networking-agent.vercel.app`)

That's a new deploy trigger, so Fly will restart the machine automatically
with the new value applied.

## 4. Verify end to end

1. Open the Vercel URL, register an account.
2. Add a Gemini API key under "API Key Workers" (free tier key from
   [Google AI Studio](https://aistudio.google.com/apikey)).
3. Add an outreach target (paste details manually is fastest to test).
4. Watch it move from Pending -> Processing -> Draft Ready.

If step 4 hangs on Processing, check backend logs:

```bash
fly logs --app <your-app-name>
```

## Notes on the "10 users" requirement

- The orchestrator spins up one background worker per active Gemini API key,
  per user, inside a single process. Fly must stay pinned at exactly 1
  machine (already set in `fly.toml` via `min_machines_running = 1` and no
  autoscaling) or you'd get duplicate uncoordinated worker pools hitting the
  same database from two machines.
- SQLite is now running in WAL mode (`database.py`), so reads and writes
  from the API and from background workers don't lock each other out. Fine
  for 10 concurrent users; if this grows well past that, the next real step
  is Postgres, not a bigger SQLite hack.
- The free Fly machine (`shared-cpu-1x`, 512MB) is CPU-light work; the
  actual bottleneck at scale is Gemini API rate limits per key, which the
  existing key-pool failover in `orchestrator.py` already handles.
