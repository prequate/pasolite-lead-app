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

MODEL AVAILABILITY: Google has changed, more than once during this build,
which specific model names it will actually let a given account call, even
when its own "list models" endpoint says the model supports generateContent.
Rather than hard-code one model name and have it silently rot, every call in
this file goes through _call_with_fallback, which tries each entry in
prompts.CANDIDATE_MODELS in order and moves on to the next if a model comes
back "not found" / "no longer available" for this account. The first model
that actually works gets cached in _working_model so later requests skip
straight to it. See the long comment above CANDIDATE_MODELS in prompts.py
before changing any of this.

TRANSIENT OVERLOAD (503 UNAVAILABLE, "high demand"): different problem from
the above, and needs a different response. A "not found" error means this
model will never work for this account, so the right move is to skip to the
next candidate. A 503 means Google's servers for that model are briefly
saturated with everyone's traffic, not just ours - Google's own error text
says this is usually temporary. The right move there is to wait a few
seconds and try the same model again before giving up on it, since giving
up immediately would mean a rep sees an error for something that would have
worked five seconds later. _call_with_fallback retries transient errors a
couple of times per model before moving on to the next candidate.
"""

import json
import os
import time

from google import genai
from google.genai import types

from prompts import (
    BATTLECARD_SCHEMA,
    CANDIDATE_MODELS,
    RESEARCH_PROMPT_TEMPLATE,
    STRUCTURE_PROMPT_TEMPLATE,
)

_client = None

# Once one of CANDIDATE_MODELS is confirmed to work against the real API,
# it's remembered here so every later call goes straight to it instead of
# re-discovering it from scratch each time.
_working_model = None

# A thin wrapper around time.sleep so tests can swap in a no-op and run
# instantly instead of actually waiting out the retry delays.
_sleep = time.sleep

# How many times to retry the same model on a transient (503/overload)
# error before giving up on it and moving to the next candidate, and how
# long to wait before the first retry (doubles each attempt after that).
# Kept small - this runs inside a background task with a few minutes of
# headroom before the frontend stops polling, but every extra second here
# is a rep staring at a spinner.
TRANSIENT_RETRY_ATTEMPTS = 3
TRANSIENT_RETRY_BASE_DELAY = 4


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


def _is_model_unavailable_error(e: Exception) -> bool:
    """
    True for the class of error Google has been sending for a model this
    account currently can't call ("no longer available to new users",
    "no longer available... use the Interactions API", plain 404
    NOT_FOUND) - the exact wording has changed more than once, so this
    matches loosely on purpose. False for anything else (bad API key,
    network error, real quota exhaustion), which should fail loudly
    instead of silently skipping to the next model.
    """
    msg = str(e).lower()
    return (
        "not_found" in msg
        or "404" in msg
        or "no longer available" in msg
        or "not supported" in msg
    )


def _is_transient_error(e: Exception) -> bool:
    """
    True for Google's "this model is temporarily overloaded, try again"
    class of error - 503 UNAVAILABLE with "high demand" wording, or a 429
    rate limit - as opposed to a permanent block on this account. Google's
    own message for this explicitly calls it usually temporary, so this is
    worth a short retry rather than an immediate failure or an immediate
    jump to a different model.
    """
    msg = str(e).lower()
    return (
        "503" in msg
        or "unavailable" in msg
        or "high demand" in msg
        or "429" in msg
        or "resource_exhausted" in msg
        or "rate limit" in msg
    )


def _call_with_fallback(fn):
    """
    Calls fn(model_name) against each candidate model in turn - the
    remembered working model first, if there is one, then
    CANDIDATE_MODELS in order - and returns the first successful result.
    fn should be a function that takes a model name string and returns
    whatever the caller needs (a response object), raising on failure.

    Two different failure modes are handled differently here: a "not
    found"/"no longer available" error means this model will never work
    for this account, so it moves straight to the next candidate. A
    transient 503/overload error gets a few short retries on the SAME
    model first (it's usually gone within seconds), and only moves on to
    the next candidate if it's still failing after those retries.
    """
    global _working_model

    candidates = list(CANDIDATE_MODELS)
    if _working_model and _working_model in candidates:
        candidates.remove(_working_model)
        candidates.insert(0, _working_model)

    last_err = None
    for model in candidates:
        for attempt in range(TRANSIENT_RETRY_ATTEMPTS):
            try:
                result = fn(model)
                if model != _working_model:
                    # Logged once per model switch, not per request - this
                    # is the answer to "which model is actually costing
                    # money" without needing another round of manual
                    # diagnosis. Check the host's logs (e.g. Render's
                    # "Logs" tab) if that question comes up again.
                    print(f"[gemini] using model: {model}")
                _working_model = model
                return result
            except Exception as e:
                last_err = e
                if _is_transient_error(e) and attempt < TRANSIENT_RETRY_ATTEMPTS - 1:
                    delay = TRANSIENT_RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"[gemini] {model} temporarily unavailable, "
                          f"retrying in {delay}s (attempt {attempt + 2}/"
                          f"{TRANSIENT_RETRY_ATTEMPTS})...")
                    _sleep(delay)
                    continue
                if _is_model_unavailable_error(e) or _is_transient_error(e):
                    break  # retries (if any) exhausted - try next candidate
                raise

    raise RuntimeError(
        "None of the candidate Gemini models are available on this "
        f"account right now: {candidates}. Last error from "
        f"'{candidates[-1] if candidates else '?'}': {last_err}. "
        "If the last error was a 503/high-demand message, this may just "
        "be a bad-luck moment where every candidate was briefly "
        "overloaded at once - it's worth trying the lead again. If it was "
        "a 404/not-found message instead, check "
        "https://ai.google.dev/gemini-api/docs/models for whatever "
        "Google currently recommends and add it to CANDIDATE_MODELS in "
        "prompts.py."
    )


def _generate_structured(client, prompt, schema):
    """
    Calls generate_content forcing JSON output matching `schema`, trying
    every candidate model. Tries the config shape documented at the time
    this was built; if Google has since renamed the field (this API
    surface moved once already, from response_mime_type/response_schema
    toward a newer response_format shape), fall back to the alternate
    shape rather than hard-failing. Check
    https://ai.google.dev/gemini-api/docs/structured-output if both of
    these ever start erroring.
    """

    def call(model):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            return response.text
        except TypeError:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_format": {
                        "text": {"mime_type": "application/json", "schema": schema}
                    }
                },
            )
            return response.text

    return _call_with_fallback(call)


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
    def research_call(model):
        resp = client.models.generate_content(
            model=model,
            contents=RESEARCH_PROMPT_TEMPLATE.format(lead_input=lead_input),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            ),
        )
        if not resp.text or not resp.text.strip():
            raise RuntimeError(
                "Research call returned no text from model "
                f"'{model}'. Check GEMINI_API_KEY and CANDIDATE_MODELS "
                "in prompts.py."
            )
        return resp.text

    research_text = _call_with_fallback(research_call)

    # ---- call 2: force the battlecard JSON shape ----
    structure_text = _generate_structured(
        client,
        STRUCTURE_PROMPT_TEMPLATE.format(lead_input=lead_input, research_text=research_text),
        BATTLECARD_SCHEMA,
    )
    return json.loads(structure_text)
