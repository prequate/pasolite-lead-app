"""
Exercises the full app (routes, SQLite storage, PDF generation, and the
create-then-poll flow) without calling the real Gemini API, by stubbing
research_and_structure with the same sample data used to test the
pasolite-lead-intel skill. Run this after any change to
app.py/battlecard_pdf.py to catch integration bugs before a real API key
is involved.
"""

import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

with open("/tmp/work/test_khosla.json") as f:
    SAMPLE = json.load(f)
SAMPLE["whatsapp_summary"] = (
    "Khosla Associates is a Bangalore boutique studio, AD100-listed, premium "
    "residential and hospitality work. Typical project ticket size runs from "
    "an estimated 15 lakh to over a crore depending on scope. Strongest "
    "signal: the principal has publicly said the firm wants new manufacturer "
    "relationships. Worth confirming the Cona Lighting vendor relationship "
    "before the meeting, since it's only documented on one project."
)


def poll_until_done(client, lead_id, timeout_s=10):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = client.get(f"/api/leads/{lead_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        if data["status"] in ("done", "error"):
            return data
        time.sleep(0.1)
    raise AssertionError(f"Lead {lead_id} never finished within {timeout_s}s")


def run():
    with patch("app.research_and_structure", return_value=dict(SAMPLE)):
        from fastapi.testclient import TestClient
        import app as app_module
        client = TestClient(app_module.app)

        r = client.get("/")
        assert r.status_code == 200 and "Generate battlecard" in r.text
        print("GET /              OK")

        r = client.get("/api/leads")
        assert r.status_code == 200
        print("GET /api/leads     OK ->", len(r.json()), "existing leads")

        r = client.post("/api/leads", json={"input_text": "khosla-associates.com"})
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["status"] in ("pending", "done")  # TestClient may run the
        # background task inline before returning - either is fine here, a real
        # deployed server returns 'pending' and finishes asynchronously.
        lead_id = created["id"]
        print("POST /api/leads    OK -> id", lead_id, "status", created["status"])

        data = poll_until_done(client, lead_id)
        assert data["status"] == "done", data
        assert data["company_name"] == "Khosla Associates"
        assert data["pdf_url"].endswith(".pdf")
        assert len(data["whatsapp_summary"]) > 20
        print("poll -> done       OK ->", data["company_name"], data["pdf_url"])

        r = client.get(data["pdf_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 5000
        print("GET  pdf           OK ->", len(r.content), "bytes")

        r = client.post("/api/leads", json={"input_text": "   "})
        assert r.status_code == 400
        print("empty-input 400   OK")

    print("\nAll pipeline checks passed.")


if __name__ == "__main__":
    run()
