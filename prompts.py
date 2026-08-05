"""
The two prompts and the JSON schema that drive lead research and battlecard
generation, run against Google's Gemini API (free tier), not Anthropic.

Same two-call shape as before: one call researches the lead with Google
Search grounding and writes up findings in prose; a second, separate call
takes that prose and forces it into the exact JSON shape the PDF builder
(battlecard_pdf.py) expects. Gemini's free-tier flash-lite models don't
support combining grounding and a forced JSON schema in one call as of this
writing, hence two calls - see research.py.

Keep this in sync with pasolite-lead-intel/references/battlecard-schema.md
if that schema ever changes - the PDF builder is shared between the skill
and this app, so the fields must match exactly.
"""

RESEARCH_PROMPT_TEMPLATE = """\
You are Pasolite's sales intelligence research analyst. Pasolite is a Bangalore \
LED architectural and decorative lighting company. A sales rep has given you a \
lead: an architect, interior designer, lighting consultant, MEP consultant, \
builder, developer, PMC firm, or corporate client. Research this lead thoroughly \
before a rep walks into a meeting with them.

Lead given by the rep: {lead_input}

Identify the organization from whatever you're given (a website link, a Google \
Maps link, or just a name). If two firms could plausibly share the name, pick \
the more likely one given any other context you have, and say so plainly \
rather than silently guessing.

The website is the least useful source on its own - it's marketing copy the \
firm already chose to say about itself. Search news coverage, design and \
architecture publications, award-body sites, magazine features, interviews, \
recruitment posts, and public professional profiles. Cross-check anything \
important across more than one source where you can.

Cover, in your written findings:
- Firm identity and scale: founders, current principals, how long it's \
  operated, city, rough size.
- Design DNA: modern vs traditional, minimal vs maximal, luxury vs value, \
  residential vs commercial vs hospitality, indoor vs landscape.
- Project portfolio and patterns: what they've actually built, especially \
  recently - named projects, repeat developers, anything live or ongoing.
- Lighting requirements and patterns: where lighting shows up in their work \
  (facade, landscape, interior, water features), architecture-integrated vs \
  decorative-led, and anything conspicuously absent (smart controls, \
  human-centric lighting, DALI/DMX).
- Project scale and price positioning: typical ticket size by project type \
  and where they sit in the market (premium, mass-premium, mass), \
  triangulated from client profile, project scale, and press coverage, \
  never a claimed disclosed figure.
- Which Pasolite categories genuinely fit their work (architectural \
  downlights, linear profiles, magnetic track, spotlights, wall washers, \
  facade lighting, landscape lighting, bollards, decorative and pendant \
  lighting, smart/DALI/DMX/human-centric lighting), with real evidence \
  behind each one you name.
- Decision makers: who actually has influence, and any buying signals \
  (recent hires, new offices, awards, public statements about wanting new \
  vendor relationships).
- Competitor and vendor signals: what lighting brands, if any, this firm \
  already shows evidence of using, and how confident that evidence is.

If something can't be found after a genuine effort, say "not publicly \
available" rather than guessing. Write your findings as clear prose \
organized under those headings - this is a research write-up, not the final \
formatted deliverable.\
"""

STRUCTURE_PROMPT_TEMPLATE = """\
Turn the research write-up below into the exact fields of Pasolite's one-page \
sales battlecard, matching the schema you've been given.

This card is company intelligence, not a meeting script. Every field \
describes what the account is actually doing - what they build, what \
lighting they need, what scale and price tier they operate at - never what \
the rep should say. Do not write opening lines, objection handling, or "do \
not lead with" advice into any field.

Writing rules, followed exactly:
- No em dashes anywhere. Use a comma or a second sentence instead.
- No filler description. State findings the research actually supports \
  plainly, without hedging ("might," "could potentially"). Hedge only where \
  the gap is real (write "Not publicly available" rather than guessing).
- ticket_size ranges and any other figure that isn't a disclosed fact must \
  read as an estimate in the text itself, e.g. "Est. Rs. 15-40L lighting \
  scope per villa, based on project scale and finish level [ESTIMATED]" - \
  write "Rs." not the rupee symbol, which doesn't render in the PDF font.
- Judgment calls (overall_fit, strengths, weaknesses, price_positioning) \
  are plain-language points, never numeric scores.
- product_fits: only the 4-6 categories with genuine evidence behind them, \
  ordered highest priority first, each reason tying it to actual observed \
  work.
- lighting_profile: the account's own behavior (where lighting shows up, \
  architecture-integrated vs decorative, what's conspicuously absent), not \
  a restatement of product_fits.
- projects: 3-7 of the most relevant/recent named projects that tell the \
  rep something concrete, most recent or most relevant first.
- strengths: 4-5 concrete, specific reasons this lead is worth pursuing. \
  weaknesses: 3-4 real risks or gaps, stated as plainly as the strengths.
- verify_before_meeting: only genuinely uncertain items worth a live \
  sanity-check, or an empty list if the research was solid.
- whatsapp_summary: three to five plain sentences for a phone screen - who \
  this is, their price positioning and typical project scale, the \
  strongest signal they're worth pursuing, and the one thing worth \
  double-checking. No headers, no bullets, factual register, not a pitch.

If the research left a field thin (a very small or informal firm), write \
fewer, shorter entries rather than padding them.

Lead requested: {lead_input}

Research findings:
{research_text}\
"""

# Plain JSON Schema (not a Pydantic model) so it's easy to keep in sync with
# pasolite-lead-intel/references/battlecard-schema.md by eye. Gemini's
# structured-output config accepts a schema dict directly.
BATTLECARD_SCHEMA = {
    "type": "object",
    "properties": {
        "company_name": {"type": "string"},
        "one_liner": {"type": "string"},
        "quick_facts": {"type": "array", "items": {"type": "string"}},
        "overall_fit": {"type": "string"},
        "key_contact": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "role": {"type": "string"},
            },
            "required": ["name"],
        },
        "product_fits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                    "reason": {"type": "string"},
                },
                "required": ["name", "priority", "reason"],
            },
        },
        "lighting_profile": {"type": "array", "items": {"type": "string"}},
        "ticket_size": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segment": {"type": "string"},
                    "range": {"type": "string"},
                },
                "required": ["segment", "range"],
            },
        },
        "price_positioning": {
            "type": "object",
            "properties": {
                "tier": {"type": "string"},
                "note": {"type": "string"},
            },
            "required": ["tier", "note"],
        },
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["name", "category"],
            },
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "data_confidence": {"type": "string"},
        "verify_before_meeting": {"type": "array", "items": {"type": "string"}},
        "whatsapp_summary": {"type": "string"},
    },
    "required": [
        "company_name", "one_liner", "quick_facts", "overall_fit",
        "product_fits", "lighting_profile", "ticket_size",
        "price_positioning", "projects", "strengths", "weaknesses",
        "data_confidence", "whatsapp_summary",
    ],
}

# Google is actively (and inconsistently) restricting its 2.5 model line
# for brand-new API keys as of August 2026 - both gemini-2.5-flash-lite and
# gemini-2.5-flash are confirmed blocked for new users on this project's
# key. gemini-2.0-flash is the last model that still lists free Google
# Search grounding on the free tier (every 3.x model dropped free search
# entirely, charging for it even on otherwise-free-tier accounts) - and
# it's a different generation number than the "2.5 models" Google's own
# restriction announcement named, so it may not be affected the same way.
# If this ALSO 404s as "no longer available to new users," free grounded
# research isn't available to this API key at all right now - see
# DEPLOY.md for what to do next (billing vs. the manual-entry version).
# Check https://ai.google.dev/gemini-api/docs/pricing for the current
# state of the "Grounding with Google Search" free tier column.
MODEL = "gemini-2.0-flash"
