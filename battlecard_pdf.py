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

import json
import sys

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth

PAGE_W = A4[0]
PAGE_H = 920
MARGIN = 16 * mm
HEADER_H = 48.5 * mm

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

FONT = "Helvetica"
FONT_B = "Helvetica-Bold"
FONT_I = "Helvetica-Oblique"


def tracked(text, sep=" "):
    """Insert visual letter-spacing for small caption/eyebrow text."""
    return sep.join(list(text))


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


def chip(c, text, x, y, fill, text_color, font_size=7.3, pad_x=7, h=None, align="left"):
    """A soft, rounded pill — simple but a little more fun than a plain
    label or a hard rectangle. Used for priority, category, and
    positioning tags, always in a light pastel tint, never a solid block."""
    if h is None:
        h = font_size + 6.6
    label = text.upper()
    c.setFont(FONT_B, font_size)
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
    """Solid red pill, plain white text, sitting on the black header panel —
    the one accent-color "stamp" inside an otherwise black-and-white band,
    rounded into a full pill for a friendlier finish."""
    label = label.upper()
    c.setFont(FONT_B, 9)
    text_w = stringWidth(label, FONT_B, 9)
    pad_x = 12
    w = pad_x * 2 + text_w
    h = 8.5 * mm
    x = right_edge - w
    y = top_y - h
    c.setFillColorRGB(*ACCENT)
    c.roundRect(x, y, w, h, h / 2, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
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


def build(data, out_path):
    c = canvas.Canvas(out_path, pagesize=(PAGE_W, PAGE_H))
    c.setFillColorRGB(*PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    # ---------------- header: solid black panel, reversed-out text ----------------
    c.setFillColorRGB(*HEADER_PANEL)
    c.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, stroke=0, fill=1)

    c.setFillColorRGB(*ACCENT)
    c.setFont(FONT_B, 10)
    c.drawString(MARGIN, PAGE_H - 10 * mm, "PASOLITE")
    c.setFont(FONT, 6.3)
    c.setFillColorRGB(*HEADER_LOW)
    c.drawString(MARGIN + stringWidth("PASOLITE", FONT_B, 10) + 8,
                  PAGE_H - 10 * mm + 0.5, tracked("SALES INTELLIGENCE BRIEF"))

    fit = data.get("overall_fit", "")
    if fit:
        fit_badge(c, PAGE_W - MARGIN, PAGE_H - 6.5 * mm, fit)

    c.setFillColorRGB(*HEADER_TEXT)
    c.setFont(FONT_B, 25)
    c.drawString(MARGIN, PAGE_H - 21 * mm, data.get("company_name", "Unnamed lead"))

    c.setFont(FONT, 10)
    one_liner = data.get("one_liner", "")
    draw_wrapped(c, one_liner, MARGIN, PAGE_H - 27.5 * mm, FONT, 10,
                 max_width=390, leading=12, color=HEADER_SUB, max_lines=2)

    y_facts = PAGE_H - 40 * mm
    facts = data.get("quick_facts", [])
    if facts:
        c.setFont(FONT, 8.5)
        c.setFillColorRGB(*HEADER_LOW)
        c.drawString(MARGIN, y_facts, "   /   ".join(facts))

    kc = data.get("key_contact", {})
    if kc and kc.get("name"):
        line = kc["name"]
        if kc.get("role"):
            line += f", {kc['role']}"
        c.setFont(FONT_B, 8.3)
        c.setFillColorRGB(*HEADER_TEXT)
        c.drawString(MARGIN, y_facts - 5.5 * mm, line)

    hline(c, 0, PAGE_W, PAGE_H - HEADER_H, color=ACCENT, width=1.6)
    y = PAGE_H - HEADER_H - 9 * mm

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
        c.drawString(left_x, ly, name)
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
            c.drawString(left_x, ly, name)
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
            c.drawString(right_x, ry, segment)
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
        footer_text = "   |   ".join(footer_bits)
        draw_wrapped(c, footer_text, MARGIN, y, FONT_I, 7,
                     PAGE_W - 2 * MARGIN, 8.6, color=LOW, max_lines=2)

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
