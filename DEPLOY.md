# Deploying the Pasolite Lead Intelligence app

## What this is

A small web app: one page, one form. A rep pastes a website, a Google Maps
link, or a company name, and the backend researches the lead with Google's
Gemini API (free tier, with web search built in), builds the same one-page
PDF battlecard as the pasolite-lead-intel skill, and lists every lead
generated so far. Leads are stored in a local SQLite file
(`data/leads.db`) - that's the "database," no separate server to set up.

This version does not use Claude or any Anthropic billing. It uses Google's
Gemini API, which has a genuine, permanent free tier for the volume this
is built for.

## What you need before this can go live

1. **A free Gemini API key.** Go to https://aistudio.google.com/apikey,
   sign in with any Google account, and create a key. No credit card, no
   trial period that expires. Set it as an environment variable named
   `GEMINI_API_KEY` wherever this app runs. Never put the key in the HTML
   or any file that reaches a browser - it lives only on the server.
2. **A host that runs a real backend process**, since this needs Python
   running continuously to build PDFs with `reportlab`. A plain "upload
   the HTML somewhere" host will not work.

## Running it locally first (recommended before deploying anywhere)

```
cd pasolite-lead-app
pip install -r requirements.txt
export GEMINI_API_KEY=...            # your real free key
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` and try a real lead. Do this before deploying,
since it's the first time the research call runs against the live API
rather than the stubbed test data used to build this.

## Where to host it, and what "free" actually means on each

**Render (recommended starting point).** Free web service tier, no credit
card required to sign up. Push this folder to a Git repo, connect it on
Render, set `GEMINI_API_KEY` in the dashboard, deploy. The one real
tradeoff: a free Render service spins down after 15 minutes with no
traffic, and the next request after that takes about a minute to wake it
back up [source: Render's own docs]. For a handful of reps checking in
occasionally through the day, this means the first lead of a work session
might take an extra minute, not a repeat annoyance.

**Why "Failed to fetch" happens, and how this app avoids it.** Generating
one battlecard means two sequential Gemini calls, which can take 30 to 90
seconds even on a warm server, longer on a cold-started free instance. A
web request held open that long gets killed by most hosting platforms'
own reverse proxy before Gemini even finishes, and the browser reports
that as a bare "Failed to fetch" with no useful detail. To avoid this,
`POST /api/leads` returns almost immediately (it only queues the work),
and the actual research runs in a background task while the page polls
`GET /api/leads/{id}` every few seconds until it's done. No single HTTP
request ever stays open long enough for a timeout to matter. Don't change
this back to one long blocking call.

**If you deploy to Google Cloud Run instead of Render**, one setting
matters for this to keep working: Cloud Run by default can pause a
container's CPU the instant it finishes sending an HTTP response, which
would kill the background research task before it completes. Turn on
"CPU is always allocated" in the service's settings (not the default,
which is "CPU is only allocated during request processing") so the
background task keeps running after the response goes out.

**Google Cloud Run (alternative, if the minute-long wake-up bothers you).**
Also has a generous permanent free tier (2 million requests a month), and
since you're already using a Google API for research, it keeps everything
in one ecosystem. Its cold starts are typically faster than Render's. The
tradeoff: Google Cloud requires attaching a billing account to your
project even to use the free tier, which feels like friction even though
nothing gets charged within the free allowance.

A `Dockerfile` is included and works on either platform, or any other host
that runs containers.

One thing to get right on whichever host you choose: `data/` and `pdfs/`
need to persist across restarts, or every generated lead disappears when
the container redeploys. Both Render and Cloud Run offer a small
persistent disk or volume option - turn it on.

## What "free" actually costs, with sources

Hosting: $0 on Render's free tier (with the cold-start tradeoff above) or
within Google Cloud Run's free monthly allowance.

Research: Gemini 2.5 Flash-Lite's free tier allows 1,000 requests a day,
with Google Search grounding free up to 500 grounded requests a day,
shared across Flash and Flash-Lite models [CATEGORY RESEARCH: sourced from
Google's published pricing page, cross-checked against independent
trackers, since Google's own rate-limit page no longer publishes a static
table - confirm current numbers at https://aistudio.google.com/rate-limit
before assuming this holds indefinitely]. Each lead costs two API calls
(one research call, one structuring call), so this comfortably covers many
leads a day across a small team. Google tightened this free tier once
already, in December 2025, without much notice, so treat it as generous
today rather than a permanent guarantee.

## If this outgrows SQLite

SQLite is genuinely fine at this scale. If Pasolite later wants multiple
people editing simultaneously at high volume, migrate to a hosted Postgres
database (a free add-on on most of these platforms) - a small code change
in `app.py`, not a rebuild.

## Before rolling this out to reps

- Test with 3 to 5 real leads a rep would actually paste in, including a
  messy one (just a name, no link).
- Check a generated PDF against the reference (`test_khosla.pdf` from the
  pasolite-lead-intel skill) to confirm the visual output still matches
  once real research data flows through it instead of the test fixture.
- If research calls start failing outright, the two most likely causes
  are: the model ID in `prompts.py` (`MODEL = "gemini-2.5-flash-lite"`)
  being renamed or retired, or the structured-output config in
  `research.py` needing an update - both are called out with comments at
  the exact lines to check, and links to Google's current docs.
