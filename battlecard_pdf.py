#!/usr/bin/env python3
"""
Builds the Pasolite Lead Intelligence one-page battlecard PDF.

Usage:
    python3 build_battlecard.py <input.json> <output.pdf>

See references/battlecard-schema.md for the exact JSON shape this expects.
This script draws a single fixed-layout page — it does not attempt to be a
general-purpose report engine. If the content needs a fundamentally
different layout, edit this script directly rather than routing around it.

This is a company-intelligence card, not a meeting script: every section
answers "what is this account actually doing," not "what should the rep
say." Keep it that way when editing — don't reintroduce talking points,
objection handling, or opening lines here.

Visual language: bold black headlines, white ground, red used as punctuation
(a small accent dot, the fit badge, bullet dots) rather than as a wash of
color or filled blocks. Navy is the quiet secondary label color for
categories and positioning, the same way Pasolite's own catalogue uses navy
on its INDEX pages. Tags (priority, category, positioning) are soft rounded
pill chips in a light tint of their color, not solid blocks — simple, but
with a bit of warmth rather than reading like a spreadsheet. Red, navy and
the wordmark are all sampled from Pasolite's own outdoor catalogue and
pasolite.com — if Pasolite's brand material changes, re-sample from the
current source rather than guessing new values.

The header band is a solid black panel — the same black-panel treatment
the catalogue itself uses for its narrative/brand-voice pages — with the
wordmark, company name, and one-liner reversed out in white, and red kept
as the one accent color inside it (the fit badge, the wordmark). The dense
two-column body underneath stays plain paper; only the header gets the
dark panel treatment.
"""

import io
import json
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

PAGE_W = A4[0]
MARGIN = 16 * mm
HEADER_H = 48.5 * mm

# The page height is not fixed - a lead with a short, thin research record
# (few product fits, a short strengths list) has real content that ends
# well before a lead with a full record does, and a single fixed page
# height for every card left a large, obviously dead gap between the last
# section and the bottom edge on the thinner cards. Instead, build() below
# does a two-pass render: a scratch pass on a generously tall canvas to
# measure where the content actually ends, then a real pass sized to that
# measurement plus a small constant footer margin. MEASURE_PAGE_H only
# needs to be tall enough to fit the fullest realistic card - it is never
# the height of the file that ships, so err generous rather than tune it
# per lead.
MEASURE_PAGE_H = 920
BOTTOM_MARGIN = 20 * mm
MIN_PAGE_H = 500

# ---- palette ---------------------------------------------------------
BLACK = (0.0, 0.0, 0.0)
INK = (0.07, 0.07, 0.07)          # near-black body/headline text
SUBINK = (0.30, 0.30, 0.30)       # secondary grey text
LOW = (0.52, 0.52, 0.52)          # tertiary / footnote grey
PAPER = (0.984, 0.980, 0.972)     # warm off-white — a little softer than
                                   # stark white, still light enough to
                                   # print clean and keep every other
                                   # color reading true.
RULE = (0.85, 0.85, 0.85)         # hairline rule grey
ACCENT = (0.761, 0.051, 0.059)    # Pasolite red #C20D0F
NAVY = (0.20, 0.196, 0.435)       # Pasolite catalogue navy #33326F — quiet
                                   # label color for categories/positioning,
                                   # never for emphasis or blocks.
RED_TINT = (0.98, 0.90, 0.90)     # soft pastel fill for "High" priority chips
NAVY_TINT = (0.90, 0.90, 0.95)    # soft pastel fill for category/medium chips
HEADER_PANEL = (0.086, 0.086, 0.086)  # Eerie Black #161616 — solid header
                                       # panel, the catalogue's own black
                                       # narrative-page treatment.
HEADER_TEXT = (1.0, 1.0, 1.0)          # reversed-out white, header only
HEADER_SUB = (0.80, 0.80, 0.80)        # light grey for one-liner/facts
HEADER_LOW = (0.62, 0.62, 0.62)        # dimmer grey, header captions
GREY_TINT = (0.94, 0.94, 0.94)    # soft pastel fill for low-emphasis chips

# Fit-badge palette: each fit level gets its own soft tint + a deeply
# saturated version of the same hue for its text, the identical pairing
# system already used above for priority/category chips, just extended to
# four states and lifted onto the black header. Reads as a quiet
# traffic-light logic (green reads "go," orange reads "worth a look but
# thinner," grey reads "low signal," white reads "empty") without ever
# using a loud, saturated block color - the same restraint as the rest of
# this card's palette.
STRONG_FIT_TINT = (0.85, 0.94, 0.88)   # soft green
STRONG_FIT_TEXT = (0.11, 0.45, 0.29)   # deep emerald green
MEDIUM_FIT_TINT = (0.99, 0.88, 0.73)   # light/pastel orange
MEDIUM_FIT_TEXT = (0.70, 0.40, 0.05)   # deep amber
WEAK_FIT_TINT = (0.88, 0.88, 0.88)     # light grey
WEAK_FIT_TEXT = (0.40, 0.40, 0.40)     # mid grey
NO_FIT_TINT = (1.0, 1.0, 1.0)          # white
NO_FIT_TEXT = INK                       # near-black

# Prequate wordmark colors (Prequate Advisory brand standard: "PRE" in grey,
# "QUATE" in orange), used only for the small credit mark at the foot of the
# page — this card is Pasolite's sales tool, so the Pasolite palette above
# owns the page; Prequate gets one quiet, fixed-position imprint, not a share
# of the brand system.
PREQUATE_GREY = (0.439, 0.439, 0.439)    # Prequate Grey #707070
PREQUATE_ORANGE = (1.0, 0.588, 0.2)      # Prequate Orange #FF9633

FONT = "Helvetica"
FONT_B = "Helvetica-Bold"
FONT_I = "Helvetica-Oblique"


def tracked(text, sep=" "):
    """Insert visual letter-spacing for small caption/eyebrow text."""
    return sep.join(list(text))


def clip_text(text, font, size, max_width):
    """Truncates text with an ellipsis if it's wider than max_width, so a
    single unexpectedly long value - a verbose model output, an unusually
    long project or company name - can never overlap a neighboring chip
    or run past the page edge. A no-op for text that already fits, so
    correctly-shaped short labels (the normal case) render exactly as
    before."""
    if not text:
        return text
    if stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "…"
    while text and stringWidth(text + ellipsis, font, size) > max_width:
        text = text[:-1]
    return (text.rstrip() + ellipsis) if text else ellipsis


def wrap(c, text, font, size, max_width):
    c.setFont(font, size)
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if stringWidth(trial, font, size) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def draw_wrapped(c, text, x, y, font, size, max_width, leading, color=INK, max_lines=None):
    c.setFillColorRGB(*color)
    lines = wrap(c, text, font, size, max_width)
    if max_lines:
        lines = lines[:max_lines]
    c.setFont(font, size)
    for i, line in enumerate(lines):
        c.drawString(x, y - i * leading, line)
    return y - len(lines) * leading


def hline(c, x1, x2, y, color=RULE, width=1):
    c.setStrokeColorRGB(*color)
    c.setLineWidth(width)
    c.line(x1, y, x2, y)


def section_label(c, text, x, y, right_edge):
    """Bold black section title with a small red accent dot — friendlier
    than a hard-edged block. Underlined with a hairline rule, the
    section-break motif used throughout."""
    c.setFillColorRGB(*ACCENT)
    c.circle(x + 2.6, y + 2.6, 2.6, stroke=0, fill=1)
    c.setFillColorRGB(*BLACK)
    c.setFont(FONT_B, 11)
    c.drawString(x + 11, y, text.upper())
    hline(c, x, right_edge, y - 5.5, color=RULE, width=1)


def sub_label(c, text, x, y, color=NAVY):
    c.setFont(FONT_B, 7.6)
    c.setFillColorRGB(*color)
    c.drawString(x, y, tracked(text))


def chip(c, text, x, y, fill, text_color, font_size=7.3, pad_x=7, h=None,
         align="left", max_width=150):
    """A soft, rounded pill — simple but a little more fun than a plain
    label or a hard rectangle. Used for priority, category, and
    positioning tags, always in a light pastel tint, never a solid block.
    max_width caps how wide the pill can ever grow - tag vocabulary
    (High/Medium/Low, Pasolite's category names) is always short, so this
    is purely a safety net against a stray long value, not something
    correctly-shaped tags will ever hit."""
    if h is None:
        h = font_size + 6.6
    label = text.upper()
    c.setFont(FONT_B, font_size)
    label = clip_text(label, FONT_B, font_size, max_width - pad_x * 2)
    w = stringWidth(label, FONT_B, font_size) + pad_x * 2
    x0 = x - w if align == "right" else x
    c.setFillColorRGB(*fill)
    c.roundRect(x0, y, w, h, h / 2, stroke=0, fill=1)
    c.setFillColorRGB(*text_color)
    c.drawCentredString(x0 + w / 2, y + h / 2 - font_size * 0.34, label)
    return x0, w


def priority_chip(c, right_edge, y_top, priority):
    """A small rounded chip, tinted by priority — warmer than plain text,
    still simple, never a solid saturated block."""
    p = (priority or "").strip().lower()
    fill, text_color = {
        "high": (RED_TINT, ACCENT),
        "medium": (NAVY_TINT, NAVY),
        "low": (GREY_TINT, LOW),
    }.get(p, (GREY_TINT, LOW))
    if not p:
        return
    chip(c, priority, right_edge, y_top - 6.6, fill, text_color, align="right")


def fit_badge(c, right_edge, top_y, label):
    """A soft, rounded pill on the black header panel, tinted by the fit
    level itself so a rep can read lead strength from color alone before
    the word even registers - Strong Fit green ("go"), Medium Fit a warm
    light orange ("worth a look, evidence is thinner"), Weak Fit a quiet
    grey ("low signal"), No Fit a stark white ("nothing here"). Falls back
    to the neutral grey pairing for anything that doesn't match one of the
    four expected labels, the same defensive pattern priority_chip already
    uses for an unrecognized priority value. overall_fit is meant to be a
    short two-or-three-word label ("Strong Fit"); max_w below caps how
    wide this pill can ever grow, so if a model ever sends a full sentence
    here instead, it clips to something that still fits the header row
    rather than overlapping the wordmark or running off the page."""
    key = (label or "").strip().lower()
    fill, text_color = {
        "strong fit": (STRONG_FIT_TINT, STRONG_FIT_TEXT),
        "medium fit": (MEDIUM_FIT_TINT, MEDIUM_FIT_TEXT),
        "weak fit": (WEAK_FIT_TINT, WEAK_FIT_TEXT),
        "no fit": (NO_FIT_TINT, NO_FIT_TEXT),
    }.get(key, (WEAK_FIT_TINT, WEAK_FIT_TEXT))

    label = label.upper()
    c.setFont(FONT_B, 9)
    pad_x = 12
    max_w = 230
    label = clip_text(label, FONT_B, 9, max_w - pad_x * 2)
    text_w = stringWidth(label, FONT_B, 9)
    w = pad_x * 2 + text_w
    h = 8.5 * mm
    x = right_edge - w
    y = top_y - h
    c.setFillColorRGB(*fill)
    c.roundRect(x, y, w, h, h / 2, stroke=0, fill=1)
    c.setFillColorRGB(*text_color)
    c.drawString(x + pad_x, y + h / 2 - 3.2, label)
    return x, y


def dot_list(c, items, x, y, col_w, dot_color, max_items, leading=10.2, size=8.6, max_lines=2):
    for item in items[:max_items]:
        c.setFillColorRGB(*dot_color)
        c.setFont(FONT_B, 9)
        c.drawString(x, y, "•")
        y = draw_wrapped(c, item, x + 9, y, FONT, size, col_w - 9, leading,
                          color=INK, max_lines=max_lines)
        y -= 3.2 * mm
    return y


def _render(c, data, page_h):
    """Draws the full card onto canvas `c`, sized to `page_h`, and returns
    the y-coordinate reached right after the last content section (before
    the credit mark, which is always drawn a fixed distance from y=0
    regardless of page height). build() below calls this twice: once to
    measure, once for real."""
    c.setFillColorRGB(*PAPER)
    c.rect(0, 0, PAGE_W, page_h, stroke=0, fill=1)

    # ---------------- header: solid black panel, reversed-out text ----------------
    c.setFillColorRGB(*HEADER_PANEL)
    c.rect(0, page_h - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)

    c.setFillColorRGB(*ACCENT)
    c.setFont(FONT_B, 10)
    c.drawString(MARGIN, page_h - 10 * mm, "PASOLITE")
    c.setFont(FONT, 6.3)
    c.setFillColorRGB(*HEADER_LOW)
    c.drawString(MARGIN + stringWidth("PASOLITE", FONT_B, 10) + 8,
                  page_h - 10 * mm + 0.5, tracked("SALES INTELLIGENCE BRIEF"))

    fit = data.get("overall_fit", "")
    if fit:
        fit_badge(c, PAGE_W - MARGIN, page_h - 6.5 * mm, fit)

    c.setFillColorRGB(*HEADER_TEXT)
    c.setFont(FONT_B, 25)
    company_name = data.get("company_name", "Unnamed lead")
    company_name = clip_text(company_name, FONT_B, 25, PAGE_W - 2 * MARGIN)
    c.drawString(MARGIN, page_h - 21 * mm, company_name)

    c.setFont(FONT, 10)
    one_liner = data.get("one_liner", "")
    draw_wrapped(c, one_liner, MARGIN, page_h - 27.5 * mm, FONT, 10,
                 max_width=390, leading=12, color=HEADER_SUB, max_lines=2)

    y_facts = page_h - 40 * mm
    facts = data.get("quick_facts", [])
    if facts:
        c.setFont(FONT, 8.5)
        c.setFillColorRGB(*HEADER_LOW)
        facts_line = clip_text("   /   ".join(facts), FONT, 8.5, PAGE_W - 2 * MARGIN)
        c.drawString(MARGIN, y_facts, facts_line)

    kc = data.get("key_contact", {})
    if kc and kc.get("name"):
        # "LED BY" is a small tracked caption, the same treatment as
        # "SALES INTELLIGENCE BRIEF" next to the wordmark above, so the
        # name reads unambiguously as leadership rather than an
        # unexplained name sitting in the header. Sits inline before the
        # name rather than on its own line, since the header's fixed
        # height has no spare vertical room for an extra line.
        kc_y = y_facts - 5.5 * mm
        caption = tracked("LED BY")
        c.setFont(FONT, 6.3)
        c.setFillColorRGB(*HEADER_LOW)
        c.drawString(MARGIN, kc_y + 0.6, caption)
        caption_w = stringWidth(caption, FONT, 6.3)

        line = kc["name"]
        if kc.get("role"):
            line += f", {kc['role']}"
        c.setFont(FONT_B, 8.3)
        c.setFillColorRGB(*HEADER_TEXT)
        name_x = MARGIN + caption_w + 8
        c.drawString(name_x, kc_y,
                      clip_text(line, FONT_B, 8.3, PAGE_W - MARGIN - name_x))

    hline(c, 0, PAGE_W, page_h - HEADER_H, color=ACCENT, width=1.6)
    y = page_h - HEADER_H - 9 * mm

    col_gap = 8 * mm
    col_w = (PAGE_W - 2 * MARGIN - col_gap) / 2
    left_x = MARGIN
    right_x = MARGIN + col_w + col_gap
    col_top = y

    # ---------------- LEFT: what to pitch ----------------
    ly = col_top
    section_label(c, "What to pitch", left_x, ly, right_edge=left_x + col_w)
    ly -= 9 * mm

    for item in data.get("product_fits", [])[:6]:
        name = item.get("name", "")
        priority = item.get("priority", "")
        reason = item.get("reason", "")
        c.setFont(FONT_B, 9.7)
        c.setFillColorRGB(*BLACK)
        # The name shares its line with the priority chip on the right, so
        # its available width has to account for the chip - otherwise a
        # longer-than-expected name (this is meant to be a short 2-4 word
        # category name) runs straight into or past the chip.
        chip_w = 0
        p = (priority or "").strip().lower()
        if p:
            chip_label = clip_text(priority.upper(), FONT_B, 7.3, 150 - 14)
            chip_w = stringWidth(chip_label, FONT_B, 7.3) + 14
        name_max_w = col_w - (chip_w + 6 if chip_w else 0)
        c.drawString(left_x, ly, clip_text(name, FONT_B, 9.7, name_max_w))
        priority_chip(c, left_x + col_w, ly + 1, priority)
        ly -= 6.8 * mm
        ly = draw_wrapped(c, reason, left_x, ly, FONT, 8.3, col_w, 10.2,
                           color=SUBINK, max_lines=2)
        ly -= 5 * mm

    # ---------------- LEFT (cont): projects ----------------
    projects = data.get("projects", [])
    if projects:
        section_label(c, "Projects they're known for", left_x, ly, right_edge=left_x + col_w)
        ly -= 9 * mm
        for p in projects[:7]:
            name = p.get("name", "")
            category = p.get("category", "")
            note = p.get("note", "")
            c.setFont(FONT_B, 9)
            c.setFillColorRGB(*BLACK)
            cat_chip_w = 0
            if category:
                cat_label = clip_text(category.upper(), FONT_B, 6.6, 150 - 14)
                cat_chip_w = stringWidth(cat_label, FONT_B, 6.6) + 14
            proj_name_max_w = col_w - (cat_chip_w + 6 if cat_chip_w else 0)
            c.drawString(left_x, ly, clip_text(name, FONT_B, 9, proj_name_max_w))
            if category:
                chip(c, category, left_x + col_w, ly - 4.9, NAVY_TINT, NAVY,
                     font_size=6.6, align="right")
            ly -= 4.6 * mm
            if note:
                ly = draw_wrapped(c, note, left_x, ly, FONT, 7.8, col_w, 9.4,
                                   color=LOW, max_lines=1)
            ly -= 3.4 * mm

    # ---------------- RIGHT: lighting profile ----------------
    ry = col_top
    section_label(c, "Lighting profile", right_x, ry, right_edge=right_x + col_w)
    ry -= 9 * mm
    profile = data.get("lighting_profile", [])
    if profile:
        ry = dot_list(c, profile, right_x, ry, col_w, ACCENT, 5, leading=10.4, max_lines=3)
        ry -= 2 * mm

    # ---------------- RIGHT (cont): project scale & positioning ----------------
    ticket = data.get("ticket_size", [])
    positioning = data.get("price_positioning", {})
    if ticket or positioning:
        section_label(c, "Project scale & positioning", right_x, ry, right_edge=right_x + col_w)
        ry -= 9 * mm

        if positioning and positioning.get("tier"):
            c.setFont(FONT_B, 9.5)
            c.setFillColorRGB(*BLACK)
            c.drawString(right_x, ry, "Positioning:")
            label_w = stringWidth("Positioning: ", FONT_B, 9.5)
            chip(c, positioning["tier"], right_x + label_w, ry - 3.6,
                 RED_TINT, ACCENT, font_size=7.5)
            ry -= 6.4 * mm
            if positioning.get("note"):
                ry = draw_wrapped(c, positioning["note"], right_x, ry, FONT, 8.3,
                                   col_w, 10.2, color=SUBINK, max_lines=3)
            ry -= 5 * mm

        for t in ticket[:4]:
            segment = t.get("segment", "")
            rng = t.get("range", "")
            c.setFont(FONT_B, 8.6)
            c.setFillColorRGB(*BLACK)
            c.drawString(right_x, ry, clip_text(segment, FONT_B, 8.6, col_w))
            ry -= 4.4 * mm
            ry = draw_wrapped(c, rng, right_x, ry, FONT, 8, col_w, 9.8,
                               color=SUBINK, max_lines=2)
            ry -= 4 * mm

    y = min(ly, ry) - 3 * mm

    # ---------------- strengths / weaknesses ----------------
    strengths = data.get("strengths", [])
    weaknesses = data.get("weaknesses", [])
    if strengths or weaknesses:
        section_label(c, "Strengths & watch-outs", MARGIN, y, right_edge=PAGE_W - MARGIN)
        y -= 9 * mm
        sw_top = y
        sy = sw_top
        if strengths:
            sub_label(c, "STRENGTHS", left_x, sy, color=ACCENT)
            sy -= 5 * mm
            sy = dot_list(c, strengths, left_x, sy, col_w, ACCENT, 5)
        wy = sw_top
        if weaknesses:
            sub_label(c, "WATCH-OUTS", right_x, wy, color=NAVY)
            wy -= 5 * mm
            wy = dot_list(c, weaknesses, right_x, wy, col_w, NAVY, 4)
        y = min(sy, wy) - 2 * mm

    # ---------------- footer: verify + confidence ----------------
    flags = data.get("verify_before_meeting", [])
    confidence = data.get("data_confidence", "")
    footer_bits = []
    if confidence:
        footer_bits.append(f"Data confidence: {confidence}")
    if flags:
        footer_bits.append("Verify before the meeting: " + "; ".join(flags))
    if footer_bits:
        hline(c, MARGIN, PAGE_W - MARGIN, y, color=RULE, width=1)
        y -= 5 * mm
        y = draw_wrapped(c, footer_text := "   |   ".join(footer_bits), MARGIN, y,
                          FONT_I, 7, PAGE_W - 2 * MARGIN, 8.6, color=LOW, max_lines=2)

    content_bottom_y = y

    # ---------------- Prequate credit mark ----------------
    # Fixed position, independent of the footer's variable-length text above,
    # so it never collides regardless of how long data_confidence/verify_
    # before_meeting run. A small tracked "PREPARED BY" caption sits above
    # the wordmark so the mark reads unambiguously on a first glance rather
    # than needing to be hunted for in the corner - this is the one place
    # Prequate's own identity appears on a card that is otherwise entirely
    # Pasolite's, so it needs to actually register, not just technically
    # be present.
    wm_size = 9.5
    c.setFont(FONT_B, wm_size)
    quate_w = stringWidth("QUATE", FONT_B, wm_size)
    pre_w = stringWidth("PRE", FONT_B, wm_size)
    credit_y = 9 * mm
    credit_x = PAGE_W - MARGIN - quate_w
    c.setFillColorRGB(*PREQUATE_GREY)
    c.drawString(credit_x - pre_w, credit_y, "PRE")
    c.setFillColorRGB(*PREQUATE_ORANGE)
    c.drawString(credit_x, credit_y, "QUATE")

    caption = tracked("PREPARED BY")
    c.setFont(FONT, 6.2)
    caption_w = stringWidth(caption, FONT, 6.2)
    c.setFillColorRGB(*PREQUATE_GREY)
    c.drawString(PAGE_W - MARGIN - caption_w, credit_y + 5.2 * mm, caption)

    return content_bottom_y


def build(data, out_path):
    """Renders the one-page battlecard, sizing the page to how much this
    particular lead's content actually needs rather than one fixed height
    for every card. A thin research record (few product fits, a short
    strengths list) still has to fit inside the same page height as a
    fully-populated one under a fixed-size layout, which leaves a large,
    visibly dead gap between the last section and the bottom edge - not a
    look a one-page sales tool should ship with. Pass 1 renders onto a
    scratch, never-saved canvas just to measure where the content actually
    ends; pass 2 renders the real file at exactly that height plus a
    constant bottom margin for the footer rule and the Prequate credit
    mark. Text wrapping only depends on column width, not page height, so
    the two passes lay out identically and the measurement is reliable."""
    scratch = canvas.Canvas(io.BytesIO(), pagesize=(PAGE_W, MEASURE_PAGE_H))
    content_bottom_y = _render(scratch, data, MEASURE_PAGE_H)

    used_height = MEASURE_PAGE_H - content_bottom_y
    fitted_height = max(MIN_PAGE_H, used_height + BOTTOM_MARGIN)

    c = canvas.Canvas(out_path, pagesize=(PAGE_W, fitted_height))
    _render(c, data, fitted_height)
    c.showPage()
    c.save()


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 build_battlecard.py <input.json> <output.pdf>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        data = json.load(f)
    build(data, sys.argv[2])
    print(f"Wrote {sys.argv[2]}")


if __name__ == "__main__":
    main()
