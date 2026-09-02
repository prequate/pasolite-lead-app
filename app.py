"""
Pasolite Lead Intelligence - web app.

A rep pastes a website or Google Maps link into the page, the backend
researches the lead via the Gemini API (see research.py), builds the same
one-page PDF battlecard the pasolite-lead-intel skill produces (see
battlecard_pdf.py), stores the result in a local SQLite database, and
returns the PDF plus a WhatsApp-ready summary to the browser. Past leads
are listed on the same page so nothing gets lost.

Run locally:
    GEMINI_API_KEY=... uvicorn app:app --host 0.0.0.0 --port 8000

See DEPLOY.md before putting this in front of the sales team.

IMPORTANT: POST /api/leads returns immediately (just an INSERT), and the
actual research + PDF build happens in a background task, with the
frontend polling GET /api/leads/{id} until it's done. Do not change this
back to one long blocking request - a single request that waits through
both Gemini calls can run past 90 seconds, and most hosts (free tiers
especially) kill a connection that sits open that long, which shows up in
the browser as a plain "Failed to fetch" with no useful detail.
"""

import io
import json
import re
import sqlite3
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from battlecard_pdf import build as build_pdf
from research import research_and_structure

# ---------------- lead logo lookup (best-effort, never blocks a lead) ----------------
#
# Gemini can't return image bytes at all, grounded search gives back text
# and citations, not attachments, so this is a completely separate lookup
# from the research pipeline and adds no Gemini/API cost. It uses
# Clearbit's free, unauthenticated logo API (logo.clearbit.com), keyed off
# the rep's own pasted input, and only ever when that input is plausibly
# the lead's own website - not a Google Maps link, not a social profile,
# not a plain company name. A logo is shown on the card only when this
# whole path succeeds; anything else (no confident domain, network
# failure, timeout, a corrupt or too-small or oddly-shaped image) just
# means no logo, silently, never an error surfaced to the rep and never
# something that can delay or break a lead's research.
_LOGO_SKIP_HOSTS = {
    "google.com", "maps.google.com", "goo.gl", "maps.app.goo.gl",
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "indiamart.com",
}
LOGO_FETCH_TIMEOUT_SECONDS = 4
LOGO_MIN_DIMENSION_PX = 32
LOGO_MAX_ASPECT_RATIO = 3.0
LOGO_MAX_DOWNLOAD_BYTES = 2_000_000


def _looks_like_bare_domain(text: str) -> bool:
    """True for a plausible domain pasted without the http(s):// scheme in
    front - "honestylighting.in" or "www.honestylighting.in/about". Browsers
    hide the scheme in the address bar, so a rep copying straight from
    there very often pastes it this way, and that should not silently
    disable the logo lookup. Deliberately conservative: a plain company
    name ("Honesty Lighting", "Pragrup") has no dot and/or contains a
    space, so it never matches this and is correctly skipped, same as
    before."""
    if not text or " " in text or "\t" in text:
        return False
    if re.match(r"^https?://", text, re.IGNORECASE):
        return False  # handled by the scheme branch already
    candidate = text.split("/")[0]
    return bool(re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", candidate, re.IGNORECASE))


def _extract_company_domain(input_text: str) -> str | None:
    """Only returns a domain when the rep's own input was a real website
    for the lead itself - confidence starts here, not with what research
    later says the company's site might be. This accepts both a full
    https://... URL and a bare domain typed or pasted without the scheme
    (see _looks_like_bare_domain). A Maps link, a social profile, or a
    plain company name all return None, which means the logo lookup is
    skipped entirely for that lead."""
    text = (input_text or "").strip()
    if not text:
        return None
    if re.match(r"^https?://", text, re.IGNORECASE):
        try:
            host = urlparse(text).netloc.lower().split("@")[-1].split(":")[0]
        except Exception:
            return None
    elif _looks_like_bare_domain(text):
        host = text.split("/")[0].lower()
    else:
        return None
    if not host:
        return None
    bare = host[4:] if host.startswith("www.") else host
    if bare in _LOGO_SKIP_HOSTS:
        return None
    if "." not in bare:
        return None
    return bare


def fetch_logo_png(input_text: str) -> bytes | None:
    """Best-effort lead logo lookup. Returns clean, normalized PNG bytes
    only when confident: a real domain to try, a successful fetch inside
    a short timeout, and an image that actually looks like a usable logo
    (real dimensions, a sane aspect ratio) rather than a placeholder or a
    broken file. Returns None on any failure at any step - a missing logo
    is a normal, expected outcome for plenty of leads, not an error."""
    domain = _extract_company_domain(input_text)
    if not domain:
        print(f"[logo] no confident domain in input, skipping: {input_text!r}")
        return None
    print(f"[logo] trying {domain}")

    url = f"https://logo.clearbit.com/{domain}?size=256&format=png"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pasolite-lead-app/1.0"})
        with urllib.request.urlopen(req, timeout=LOGO_FETCH_TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                print(f"[logo] {domain}: HTTP {resp.status}, no logo")
                return None
            raw = resp.read(LOGO_MAX_DOWNLOAD_BYTES + 1)
        if not raw or len(raw) > LOGO_MAX_DOWNLOAD_BYTES:
            print(f"[logo] {domain}: empty or oversized response, no logo")
            return None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        print(f"[logo] {domain}: fetch failed ({e}), no logo")
        return None
    except Exception as e:
        print(f"[logo] {domain}: unexpected fetch error ({e}), no logo")
        return None

    try:
        from PIL import Image
    except ImportError:
        # Pillow not installed - fail safe to no logo rather than guess at
        # the image's validity with no way to actually check it.
        print(f"[logo] {domain}: Pillow not installed, no logo")
        return None

    try:
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img = Image.open(io.BytesIO(raw))  # verify() consumes the parser, reopen
        w, h = img.size
        if w < LOGO_MIN_DIMENSION_PX or h < LOGO_MIN_DIMENSION_PX:
            print(f"[logo] {domain}: image too small ({w}x{h}), no logo")
            return None
        if max(w, h) / max(1, min(w, h)) > LOGO_MAX_ASPECT_RATIO:
            print(f"[logo] {domain}: aspect ratio too extreme ({w}x{h}), no logo")
            return None
        img = img.convert("RGBA")
        out = io.BytesIO()
        img.save(out, format="PNG")
        print(f"[logo] {domain}: accepted ({w}x{h})")
        return out.getvalue()
    except Exception as e:
        print(f"[logo] {domain}: corrupt/unparseable image ({e}), no logo")
        return None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "leads.db"
PDF_DIR = BASE_DIR / "pdfs"
PDF_DIR.mkdir(exist_ok=True)
DB_PATH.parent.mkdir(exist_ok=True)

app = FastAPI(title="Pasolite Lead Intelligence")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            input_text TEXT NOT NULL,
            company_name TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            json_data TEXT,
            whatsapp_summary TEXT,
            error TEXT,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


init_db()


class LeadRequest(BaseModel):
    input_text: str


def _process_lead(lead_id: int, input_text: str):
    """
    Runs in the background, after the HTTP response for POST /api/leads has
    already gone back to the browser. Nothing here can time out a request,
    since there's no request left waiting on it - the frontend finds out
    it's done by polling GET /api/leads/{id}.
    """
    try:
        data = research_and_structure(input_text)
        whatsapp_summary = data.pop("whatsapp_summary", "")

        # Best-effort only - never let a logo problem affect the lead
        # itself. fetch_logo_png already fails safe internally, this outer
        # guard is just belt and suspenders against something unexpected.
        try:
            logo_bytes = fetch_logo_png(input_text)
        except Exception:
            logo_bytes = None

        pdf_path = PDF_DIR / f"{lead_id}.pdf"
        build_pdf(data, str(pdf_path), logo_bytes=logo_bytes)

        conn = get_db()
        conn.execute(
            "UPDATE leads SET status='done', company_name=?, json_data=?, "
            "whatsapp_summary=? WHERE id=?",
            (data.get("company_name", "Unnamed lead"), json.dumps(data),
             whatsapp_summary, lead_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[lead {lead_id}] failed: {e}\n{traceback.format_exc()}")
        conn = get_db()
        conn.execute("UPDATE leads SET status='error', error=? WHERE id=?", (str(e), lead_id))
        conn.commit()
        conn.close()


@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE_DIR / "static" / "index.html").read_text()


@app.get("/api/leads")
def list_leads():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, input_text, company_name, status, error, created_at "
        "FROM leads ORDER BY id DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/leads")
def create_lead(req: LeadRequest, background_tasks: BackgroundTasks):
    input_text = req.input_text.strip()
    if not input_text:
        raise HTTPException(400, "Paste a website, Google Maps link, or company name first.")

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO leads (input_text, status, created_at) VALUES (?, 'pending', ?)",
        (input_text, int(time.time())),
    )
    lead_id = cur.lastrowid
    conn.commit()
    conn.close()

    background_tasks.add_task(_process_lead, lead_id, input_text)

    # Returns almost instantly - the research itself hasn't started the
    # moment this response goes out, it starts right after.
    return {"id": lead_id, "status": "pending"}


@app.get("/api/leads/{lead_id}")
def get_lead(lead_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Lead not found.")
    result = dict(row)
    if result.get("json_data"):
        result["json_data"] = json.loads(result["json_data"])
    if result["status"] == "done":
        result["pdf_url"] = f"/pdfs/{lead_id}.pdf"
    return result


@app.get("/pdfs/{lead_id}.pdf")
def get_pdf(lead_id: int):
    path = PDF_DIR / f"{lead_id}.pdf"
    if not path.exists():
        raise HTTPException(404, "PDF not found.")
    return FileResponse(path, media_type="application/pdf", filename=f"{lead_id}.pdf")
