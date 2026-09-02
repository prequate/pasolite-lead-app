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
- Outdoor lighting evidence specifically - this is the single most \
  important thing to establish, and it is a different question from "is \
  this a credible architecture/design/lighting firm." Being a respected \
  firm with excellent interior work is not evidence of outdoor lighting \
  relevance on its own. Actively search for, and report separately from \
  general lighting work, anything showing facade lighting, landscape \
  lighting, bollards or pathway/perimeter lighting, street or road \
  lighting, urban or public-realm lighting, architectural exterior \
  lighting, exterior commercial lighting, hospitality or resort outdoor \
  lighting, residential township outdoor lighting, or large-scale \
  infrastructure/exterior lighting. For each piece of evidence found, say \
  plainly whether it's a completed project, a recurring project type \
  across their portfolio, or just one occasion. If a project mentions \
  lighting only in interior terms (coves, ceilings, gallery walls, \
  interior fixtures), say so explicitly rather than letting it read as \
  ambiguous outdoor evidence - the distinction matters more than the \
  overall lighting mention.
- Landscape lighting and bollards specifically - search for these even \
  when the firm's other outdoor evidence is thin. These two are \
  Pasolite's own highest-alignment categories [CLIENT-PROVIDED - Pasolite \
  names landscape lighting and bollards as its strongest product areas], \
  so any genuine, even single-instance evidence of garden or landscape \
  lighting, pathway or perimeter lighting, bollard installations, or a \
  township/campus/resort/public-realm project with grounds that would \
  plausibly need them is a distinct, real signal on its own - report it \
  even if it's the only outdoor evidence the firm has.
- Pipeline and upcoming work that would plausibly require outdoor \
  lighting specifically (a live township, an exterior heritage \
  restoration, a hospitality build with landscaped grounds, a public \
  realm or campus project), as distinct from pipeline in general.
- Lighting requirements and patterns beyond outdoor: where else lighting \
  shows up in their work (interior, water features), architecture- \
  integrated vs decorative-led, and anything conspicuously absent (smart \
  controls, human-centric lighting, DALI/DMX).
- Project scale and price positioning: typical ticket size by project type \
  and where they sit in the market (premium, mass-premium, mass), \
  triangulated from client profile, project scale, and press coverage, \
  never a claimed disclosed figure.
- Which Pasolite categories genuinely fit their work (Architectural \
  Downlights, Linear Profiles, Magnetic Track, Spotlights, Wall Washers, \
  Facade Lighting, Landscape Lighting, Bollards, Decorative and Pendant \
  Lighting, Smart/DALI/DMX/Human-Centric Lighting), with real evidence \
  behind each one you name, and whether that evidence is indoor or \
  outdoor.
- Decision makers: who actually has influence, and any buying signals \
  (recent hires, new offices, awards, public statements about wanting new \
  vendor relationships), and whether they're positioned to influence, \
  specify, recommend, or procure lighting decisions at all.
- Competitor and vendor signals: what lighting brands, if any, this firm \
  already shows evidence of using, and how confident that evidence is.
- Peer-price-segment brand relationships specifically: search separately \
  for any evidence this firm already works with, specifies, or has \
  procured from K-Lite, Hybec, Ledlum, or Changi [PREQUATE ACCOUNT TEAM- \
  PROVIDED - these four are named by Pasolite's own account team as firms \
  in roughly Pasolite's own price segment, not yet independently verified \
  by Prequate]. A genuine, credited relationship with any one of these is \
  a distinct, strong signal on its own: it means this account already \
  buys, specifies, or serves clients at Pasolite's price point, \
  regardless of whether the lighting itself was indoor or outdoor. Note \
  exactly which brand and what the evidence is (a project credit, a \
  case study, a stated vendor relationship) - don't infer this from the \
  firm merely being "premium" or "high-end" without a named, credited \
  relationship to one of these four specifically.

If something can't be found after a genuine effort, say "not publicly \
available" rather than guessing. A firm with no outdoor lighting evidence \
after a genuine search is a normal, common outcome, say that plainly \
rather than stretching an interior project to sound like it might count. \
Write your findings as clear prose organized under those headings - this \
is a research write-up, not the final formatted deliverable.\
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
- quick_facts: 3-5 SHORT items only, about 5 words each, rendered as a \
  strip of short tags separated by slashes under the one-liner, not read \
  as sentences. Typically: city, founding year and/or years in operation \
  (these two can combine into one tag, e.g. "Est. 1996 · 30 yrs"), firm \
  size, and primary segment. Never combine multiple unrelated facts into \
  one item with "and"/commas/"led by" - each item is one short fact, not \
  a run-on sentence. Never put a person's name or title in quick_facts, \
  that belongs only in key_contact, which already carries it and renders \
  it separately. Good items: "Bangalore", "Est. 1996 · 30 yrs", "15-30 \
  architects", "Institutional & residential". Bad, do not do this: \
  "Established in 1996 in Bengaluru, led by Founder and Principal \
  Architect Ravindra Kumar" - that's a sentence, not a fact tag, and it \
  duplicates key_contact.
- ticket_size ranges and any other figure that isn't a disclosed fact must \
  read as an estimate in the text itself, e.g. "Est. Rs. 15-40L lighting \
  scope per villa, based on project scale and finish level [ESTIMATED]" - \
  write "Rs." not the rupee symbol, which doesn't render in the PDF font.
- overall_fit is a short badge label only, two or three words: "Strong \
  Fit", "Medium Fit", "Weak Fit", or "No Fit". It renders inside a small \
  colored pill at the top of the card (the color itself signals which \
  one), so it must never be a sentence, a clause, or a description of who \
  the fit is for - that reasoning belongs in one_liner or the \
  product_fits reasons, not here. Which of the four \
  words to use is the single highest-stakes judgment call on this card, \
  and it follows this exact hierarchy, not a general impression of how \
  credible or prestigious the firm is:
    - Strong Fit: earned either of two ways, and only one needs to be \
      true.
        (a) Outdoor lighting evidence: clear, specific evidence of a \
        meaningful outdoor lighting project base and/or pipeline - a \
        real history of facade, landscape, street/road, \
        urban/public-realm, architectural-exterior, exterior-commercial, \
        hospitality/resort-outdoor, residential-township-outdoor, or \
        large-scale infrastructure lighting work, ideally more than one \
        instance of it, or strong relationships (with developers, \
        contractors, project owners) that plausibly generate recurring \
        outdoor lighting opportunities. Being an architecture, interior \
        design, or lighting-adjacent firm is not by itself evidence, and \
        none of the following, alone, earn Strong Fit this way: being \
        described as an "architectural firm," having designed \
        prestigious or luxury buildings, working with well-known \
        developers, having "some exterior work" with no further detail, \
        having lighting experience in general, or having exactly one \
        outdoor lighting project on record. Landscape lighting and \
        bollards are the one exception to "exactly one project isn't \
        enough": these two are Pasolite's own highest-alignment \
        categories [CLIENT-PROVIDED], so a single, genuine, credited \
        instance of landscape lighting or bollard work (or a live \
        township/campus/resort/public-realm project whose grounds would \
        plausibly need them) is on its own enough to satisfy path (a) - \
        it does not need the "more than one instance" bar that other \
        outdoor categories (facade, street lighting, and so on) still do.
        (b) Peer-price-segment brand relationship: genuine, credited \
        evidence the firm already works with, specifies, or has \
        procured from K-Lite, Hybec, Ledlum, or Changi - named by \
        Pasolite's own account team as peers in Pasolite's price \
        segment. This applies regardless of whether that brand's work \
        with the firm was indoor or outdoor, since the point of this \
        signal is proven buying behavior at Pasolite's price point, not \
        outdoor relevance specifically. It must be a real, named, \
        credited relationship (a project credit, a case study, a stated \
        vendor relationship), not an inference from the firm simply \
        being "premium" or "high-end."
      If in doubt on either path, do not round up to Strong Fit.
    - Medium Fit: a real, relevant player in Pasolite's ecosystem \
      (architecture, interior design, hospitality design, MEP/lighting \
      consulting) whose work is predominantly interior-focused, or where \
      outdoor lighting comes up only occasionally or ambiguously rather \
      than as a real pattern. This is the default landing spot for a \
      credible design firm when the outdoor lighting evidence itself is \
      thin, not Strong Fit with a caveat.
    - Weak Fit: indirect relevance only - an adjacent architecture, \
      engineering, or design business where lighting procurement overlap \
      is limited or incidental, or where the firm could theoretically \
      influence a project but is unlikely to drive meaningful outdoor \
      lighting demand.
    - No Fit: little or no credible connection to Pasolite's business at \
      all.
  Be conservative and say so plainly when evidence is thin - an honest \
  Medium Fit with a clear reason is more useful to the rep than an \
  optimistic Strong Fit that overstates what the research actually found.
- Judgment calls (overall_fit, strengths, weaknesses, price_positioning) \
  are plain-language points, never numeric scores.
- product_fits[].name is ONLY the short Pasolite category name itself \
  (Architectural Downlights, Linear Profiles, Magnetic Track, Spotlights, \
  Wall Washers, Facade Lighting, Landscape Lighting, Bollards, Decorative \
  and Pendant Lighting, Smart/DALI/DMX/Human-Centric Lighting, or a close \
  two-to-four-word variant of one of these) - never a longer descriptive \
  phrase and never anything in parentheses. Always title case, every \
  principal word capitalized (e.g. "Architectural Downlights", not \
  "architectural downlights" or "ARCHITECTURAL DOWNLIGHTS"), matching how \
  a category name would appear as a label, not as a word inside a \
  sentence. It renders on a single line next to a priority chip, so a \
  long name will visually collide with that chip. Any technical detail \
  (deep-recessed, low glare/UGR, specific CRI or color temperature, \
  DALI/DMX capability, and so on) belongs in `reason`, not folded into \
  `name`.
- product_fits: only the 4-6 categories with genuine evidence behind them, \
  ordered highest priority first, each reason tying it to actual observed \
  work. Outdoor categories (Facade Lighting, Landscape Lighting, Bollards) \
  earn High priority only when the reason cites specific outdoor project \
  evidence, not general design philosophy - a firm's stated preference \
  for "architectural-grade specifications" is not, on its own, evidence \
  for an outdoor category. If a category's only support is indoor work \
  (interior coves, ceilings, gallery walls), its priority should reflect \
  that it's an indoor use case, not be inflated because the category name \
  sounds exterior. Landscape Lighting and Bollards specifically are \
  Pasolite's own highest-alignment categories [CLIENT-PROVIDED] - unlike \
  Facade Lighting, a single genuine project or a plausible live \
  opportunity (a township, campus, resort, or public-realm project with \
  grounds) is enough on its own to earn either of these two a High \
  priority, not just a repeated pattern across the portfolio.
- lighting_profile: the account's own behavior (where lighting shows up, \
  architecture-integrated vs decorative, what's conspicuously absent), \
  explicitly distinguishing indoor from outdoor evidence rather than \
  blending them into one impression - not a restatement of product_fits.
- projects: 3-7 of the most relevant/recent named projects that tell the \
  rep something concrete, most recent or most relevant first. Where a \
  project is genuine outdoor lighting evidence (facade, landscape, \
  street, public realm, exterior commercial or hospitality, township, \
  infrastructure), the note should say so plainly rather than leaving it \
  to be inferred from the project name or category tag alone.
- strengths: 4-5 concrete, specific reasons this lead is worth pursuing, \
  covering both current outdoor lighting evidence and credible pipeline - \
  upcoming or live work plausibly requiring outdoor lighting - where \
  either genuinely exists; don't invent pipeline that isn't supported by \
  the research. If overall_fit reached Strong Fit through a peer-price- \
  segment brand relationship (K-Lite, Hybec, Ledlum, Changi) rather than \
  through outdoor lighting evidence, say so explicitly and name the brand \
  - a rep should see plainly why the badge says Strong Fit even without \
  outdoor project history to point to. Likewise, if overall_fit reached \
  Strong Fit on the strength of a single landscape lighting or bollard \
  project or opportunity rather than a broader outdoor pattern, say that \
  plainly and name the specific project - a rep should see why the badge \
  says Strong Fit even with only one piece of outdoor evidence. \
  weaknesses: 3-4 real risks or \
  gaps, stated as plainly as the strengths - if the overall_fit is Medium \
  or Weak specifically because outdoor lighting evidence is thin or \
  absent, say that directly here rather than only implying it through \
  the fit badge.
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

# IMPORTANT - read this before ever touching a model name by hand again.
#
# We spent a long stretch guessing model names one at a time
# (gemini-2.5-flash-lite, then gemini-2.5-flash, then gemini-2.0-flash),
# and each one eventually 404'd even though Google's own "list models"
# endpoint reports all of them as supporting generateContent on this
# account. That mismatch is the real lesson: what Google's API says a
# project CAN see and what it will actually let you call right now are two
# different things, and that gap has moved more than once during this
# build without notice.
#
# So instead of pinning to one model name, research.py now tries a list of
# candidates in order and automatically moves to the next one if a model
# comes back "not found" / "no longer available" - the exact error text
# Google has been changing. Whichever one actually works gets cached for
# the rest of that server's uptime, so this costs nothing after the first
# request.
#
# COST ORDERING - updated a second time, from the account's real Spend
# dashboard, not just documentation or logs. This is the important lesson
# from that update: gemini-flash-latest and gemini-flash-lite-latest are
# FLOATING POINTERS, not fixed models - Google can and does repoint them to
# a newer model generation without notice. When we put gemini-flash-latest
# first, it quietly resolved to "Gemini 3.6 Flash," a full flagship model,
# not a lite one, and that's what actually ran up the token bill. Putting a
# floating alias first optimizes for "something that works," not for
# "something cheap" - those turned out to be two different models.
#
# [CATEGORY RESEARCH, NOT CLIENT-CONFIRMED - re-check
# ai.google.dev/gemini-api/docs/pricing before treating any of this as
# final, this whole model line has moved more than once during this build]
# Per-million-token pricing as of this update:
#   gemini-3.1-flash-lite:   $0.25 in / $1.50 out   <- cheapest confirmed-real model
#   gemini-3.5-flash-lite:   $0.30 in / $2.50 out
#   gemini-2.0-flash:        $0.10 in / $0.40 out   <- cheaper on paper, but 404s
#   gemini-2.5-flash-lite:   $0.10 in / $0.40 out   <- on this account (see below)
#   gemini-flash-latest  -> currently "Gemini 3.6 Flash": $1.50 in / $7.50 out
#   gemini-2.5-flash:        $0.30 in / $2.50 out
# Grounding differs by generation too, not just by model: the 2.x line gets
# 1,500 free grounded requests A DAY; the entire 3.x line shares one pool of
# 5,000 free grounded requests A MONTH, after which each extra request is
# actually cheaper on 3.x ($14/1,000 vs $35/1,000). So 2.x, if it ever works
# again on this account, is the better deal on volume - it's just blocked
# right now (see below).
#
# gemini-3.1-flash-lite and gemini-3.5-flash-lite are real, specific,
# non-alias models - not moving targets - and both showed up as
# generateContent-capable in this account's own /api/diag output, so they
# go first, cheapest first. gemini-2.0-flash and gemini-2.5-flash-lite come
# next: Render's logs show them failing INSTANTLY with no retry logged,
# meaning a permanent "not available" 404 on this account right now, not a
# transient error - dead ends today, but cheap and worth leaving in in case
# Google lifts whatever block that is. The two floating aliases and
# full-price gemini-2.5-flash are last resort only, specifically because
# they're the expensive/unpredictable options, not the cheap ones.
#
# Whichever model actually succeeds gets cached in research.py for the
# rest of that server's uptime, so re-ordering this list costs nothing
# extra - it only changes which model wins on a cold start.
#
# If every candidate below ever fails at once, the error message from the
# app will say so explicitly (it lists which model was tried last) -
# that's the moment to open https://ai.google.dev/gemini-api/docs/models
# and https://ai.google.dev/gemini-api/docs/pricing for whatever Google
# currently recommends, and add it to the front of this list. Don't
# replace the whole list with a single new guess again - check the
# account's real Spend dashboard first, the way this update was made,
# since that's the only place that shows what a model actually resolved to
# and actually cost, as opposed to what its name implies.
CANDIDATE_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-2.5-flash",
    # Added after a live outage on Aug 19, 2026: every candidate above
    # failed at once on the deployed account, and the 404 from
    # gemini-2.5-flash (the last one tried) told us directly what to do -
    # "This model ... is no longer available to new users. Please update
    # your code to use models/gemini-3.6-flash." gemini-flash-latest above
    # is already believed to resolve to the same underlying "Gemini 3.6
    # Flash" model, but it's a floating alias, not a fixed name, so it can
    # silently repoint again the way it already has once before in this
    # project. This entry is the literal, specific model name Google's own
    # error named, so it stays addressable even if that alias drifts.
    # Deliberately last and only reached if every cheaper candidate above
    # has failed - at roughly 5-6x the per-token cost of the flash-lite
    # models, it's an emergency backstop against a total outage, not a
    # model this app should be routing to normally. If this app starts
    # actually using this fallback regularly, that's the signal to go
    # re-verify pricing and availability at
    # https://ai.google.dev/gemini-api/docs/pricing and reconsider the
    # whole list, not just leave it running on the expensive option.
    "gemini-3.6-flash",
]

# Kept for anything that still wants a single display name (e.g. logging).
# Not used to pick which model is actually called - see CANDIDATE_MODELS.
MODEL = CANDIDATE_MODELS[0]
