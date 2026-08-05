"""
The two-call pipeline against Google's Gemini API (free tier):
call 1 researches the lead with Google Search grounding, call 2 forces that
research into the battlecard's exact JSON shape.

Needs GEMINI_API_KEY set in the environment (free, no credit card - get one
at https://aistudio.google.com/apikey). Nothing here talks to a database or
builds the PDF - see app.py for that.

Gemini's free-tier flash-lite models don't support combining Google Search
grounding with a forced JSON schema in a single call as of when this was
built, so this stays a two-call pipeline rather than one - see the module
docstring in prompts.py for why.
"""

import json
import os

from google import genai
from google.genai import types

from prompts import (
    BATTLECARD_SCHEMA,
    MODEL,
    RESEARCH_PROMPT_TEMPLATE,
    STRUCTURE_PROMPT_TEMPLATE,
)

_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and add it to the "
                "environment before starting the server - see DEPLOY.md."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def _generate_structured(client, prompt, schema):
    """
    Calls generate_content forcing JSON output matching `schema`. Tries the
    config shape documented at the time this was built; if Google has since
    renamed the field (this API surface moved once already, from
    response_mime_type/response_schema toward a newer response_format
    shape), fall back to the alternate shape rather than hard-failing.
    Check https://ai.google.dev/gemini-api/docs/structured-output if both
    of these ever start erroring.
    """
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        return response.text
    except TypeError:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={
                "response_format": {
                    "text": {"mime_type": "application/json", "schema": schema}
                }
            },
        )
        return response.text


def research_and_structure(lead_input: str) -> dict:
    """
    lead_input: whatever the rep pasted - a website URL, a Google Maps
    link, or just a company/person name.

    Returns a dict matching BATTLECARD_SCHEMA (the same shape
    battlecard_pdf.py expects), plus a 'whatsapp_summary' key the caller
    should pop off before handing the rest to the PDF builder.
    """
    client = get_client()

    # ---- call 1: research, with Google Search grounding ----
    research_resp = client.models.generate_content(
        model=MODEL,
        contents=RESEARCH_PROMPT_TEMPLATE.format(lead_input=lead_input),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        ),
    )
    research_text = research_resp.text
    if not research_text or not research_text.strip():
        raise RuntimeError(
            "Research call returned no text. Check GEMINI_API_KEY and the "
            "model name in prompts.py."
        )

    # ---- call 2: force the battlecard JSON shape ----
    structure_text = _generate_structured(
        client,
        STRUCTURE_PROMPT_TEMPLATE.format(lead_input=lead_input, research_text=research_text),
        BATTLECARD_SCHEMA,
    )
    return json.loads(structure_text)
