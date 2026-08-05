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

import json
import sqlite3
import time
import traceback
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from battlecard_pdf import build as build_pdf
from research import research_and_structure

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

        pdf_path = PDF_DIR / f"{lead_id}.pdf"
        build_pdf(data, str(pdf_path))

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


@app.get("/api/diag")
def diagnostics():
    """
    Temporary diagnostic route. Google's model lineup and free/paid access
    rules have shifted several times during this build, and guessing a
    model name from documentation alone has been wrong more than once.
    This asks the Gemini API directly, using this project's own key,
    which models it currently allows and what each one supports - real
    ground truth for this account instead of another guess. Safe to
    delete this route once research.py is confirmed working; it exposes
    only model names, no key or lead data.
    """
    from research import get_client

    try:
        client = get_client()
    except Exception as e:
        return {"ok": False, "stage": "get_client", "error": str(e)}

    try:
        models = []
        for m in client.models.list():
            actions = list(getattr(m, "supported_actions", None) or [])
            if "generateContent" in actions:
                models.append({"name": m.name, "supported_actions": actions})
        return {"ok": True, "count": len(models), "models": models}
    except Exception as e:
        return {"ok": False, "stage": "models.list", "error": str(e)}
