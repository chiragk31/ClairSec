"""
Builds the ClairSec mid-project presentation as an editable .pptx.

Design goals: one consistent layout system, restrained colour, low text
density, and native PowerPoint shapes throughout so every element stays
editable (no flattened images).

Run:  ../venv/Scripts/python.exe build_presentation.py
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUT = Path(__file__).parent / "ClairSec_Mid_Project_Presentation.pptx"

# ---------------------------------------------------------------------------
# Design tokens — change these once and the whole deck follows
# ---------------------------------------------------------------------------
INK = RGBColor(0x14, 0x1B, 0x26)        # primary text
MUTED = RGBColor(0x5A, 0x66, 0x75)      # secondary text
FAINT = RGBColor(0x8C, 0x96, 0xA3)      # tertiary / captions
ACCENT = RGBColor(0x1F, 0x6F, 0xEB)     # brand blue
ACCENT_SOFT = RGBColor(0xE8, 0xF0, 0xFE)
SUCCESS = RGBColor(0x1A, 0x7F, 0x37)
SUCCESS_SOFT = RGBColor(0xE6, 0xF4, 0xEA)
DANGER = RGBColor(0xCF, 0x22, 0x2E)
DANGER_SOFT = RGBColor(0xFC, 0xEC, 0xEA)
WARN = RGBColor(0x9A, 0x66, 0x00)
WARN_SOFT = RGBColor(0xFD, 0xF3, 0xDD)
SURFACE = RGBColor(0xF6, 0xF8, 0xFA)
LINE = RGBColor(0xD8, 0xDE, 0xE4)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

FONT = "Calibri"
FONT_MONO = "Consolas"

W = Inches(13.333)
H = Inches(7.5)

MARGIN = Inches(0.85)
BODY_TOP = Inches(1.85)
CONTENT_W = W - (MARGIN * 2)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def textbox(slide, x, y, w, h, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.paragraphs[0].alignment = align
    return tf


def para(tf, text, size=16, color=INK, bold=False, space_after=8,
         first=False, font=FONT, italic=False, space_before=0, line=1.15):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.space_after = Pt(space_after)
    p.space_before = Pt(space_before)
    p.line_spacing = line
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = font
    return p


def rect(slide, x, y, w, h, fill=None, outline=None, radius=True):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, x, y, w, h
    )
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if outline is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = outline
        shape.line.width = Pt(1)
    shape.shadow.inherit = False
    if radius:
        try:
            shape.adjustments[0] = 0.06
        except (IndexError, KeyError):
            pass
    return shape


def blank(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def slide_header(slide, title, kicker=None):
    """Consistent header used on every content slide."""
    rect(slide, Emu(0), Emu(0), Inches(0.16), H, fill=ACCENT, radius=False)
    if kicker:
        tf = textbox(slide, MARGIN, Inches(0.62), CONTENT_W, Inches(0.3))
        para(tf, kicker.upper(), size=11, color=ACCENT, bold=True, first=True,
             space_after=0)
        y = Inches(0.95)
    else:
        y = Inches(0.75)
    tf = textbox(slide, MARGIN, y, CONTENT_W, Inches(0.7))
    para(tf, title, size=30, color=INK, bold=True, first=True, space_after=0)
    rect(slide, MARGIN, Inches(1.62), Inches(0.9), Inches(0.035),
         fill=ACCENT, radius=False)


def footer(slide, number):
    tf = textbox(slide, W - Inches(1.3), H - Inches(0.62), Inches(0.7),
                 Inches(0.3), align=PP_ALIGN.RIGHT)
    para(tf, str(number), size=11, color=FAINT, first=True, space_after=0)


def bullets(slide, items, x, y, w, size=16, gap=0.52, dot=ACCENT):
    """Bulleted list with hanging dots, laid out on an explicit grid."""
    for i, item in enumerate(items):
        cy = y + Inches(gap * i)
        rect(slide, x, cy + Inches(0.09), Inches(0.09), Inches(0.09),
             fill=dot, radius=True)
        tf = textbox(slide, x + Inches(0.26), cy - Inches(0.04),
                     w - Inches(0.26), Inches(0.5))
        if isinstance(item, tuple):
            head, tail = item
            p = tf.paragraphs[0]
            p.line_spacing = 1.1
            r1 = p.add_run()
            r1.text = head + "  "
            r1.font.size = Pt(size)
            r1.font.bold = True
            r1.font.color.rgb = INK
            r1.font.name = FONT
            r2 = p.add_run()
            r2.text = tail
            r2.font.size = Pt(size)
            r2.font.color.rgb = MUTED
            r2.font.name = FONT
        else:
            para(tf, item, size=size, color=MUTED, first=True, space_after=0,
                 line=1.1)


def stat_card(slide, x, y, w, h, value, label, color=ACCENT,
              soft=ACCENT_SOFT, sub=None):
    rect(slide, x, y, w, h, fill=soft, outline=None)
    tf = textbox(slide, x, y + Inches(0.22), w, Inches(0.6),
                 align=PP_ALIGN.CENTER)
    para(tf, value, size=34, color=color, bold=True, first=True, space_after=2)
    tf2 = textbox(slide, x, y + Inches(0.82), w, Inches(0.4),
                  align=PP_ALIGN.CENTER)
    para(tf2, label, size=12, color=MUTED, first=True, space_after=0)
    if sub:
        tf3 = textbox(slide, x, y + Inches(1.12), w, Inches(0.34),
                      align=PP_ALIGN.CENTER)
        para(tf3, sub, size=10, color=FAINT, first=True, space_after=0)


def pill(slide, x, y, w, h, text, fill, text_color, size=13, bold=True):
    rect(slide, x, y, w, h, fill=fill)
    tf = textbox(slide, x, y, w, h, align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE)
    para(tf, text, size=size, color=text_color, bold=bold, first=True,
         space_after=0)


def arrow(slide, x, y, w=Inches(0.34), h=Inches(0.26)):
    a = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, x, y, w, h)
    a.fill.solid()
    a.fill.fore_color.rgb = LINE
    a.line.fill.background()
    a.shadow.inherit = False
    return a


# ---------------------------------------------------------------------------
# Slides
# ---------------------------------------------------------------------------
def s_title(prs):
    s = blank(prs)
    rect(s, Emu(0), Emu(0), Inches(0.22), H, fill=ACCENT, radius=False)

    tf = textbox(s, MARGIN, Inches(1.75), Inches(10.4), Inches(0.4))
    para(tf, "MID-PROJECT PRESENTATION", size=13, color=ACCENT, bold=True,
         first=True, space_after=0)

    tf = textbox(s, MARGIN, Inches(2.25), Inches(11.0), Inches(1.1))
    para(tf, "ClairSec", size=54, color=INK, bold=True, first=True,
         space_after=0)

    tf = textbox(s, MARGIN, Inches(3.32), Inches(10.6), Inches(1.0))
    para(tf,
         "An adversarial multi-agent platform that finds, fixes and verifies "
         "REST API vulnerabilities",
         size=21, color=MUTED, first=True, space_after=0, line=1.25)

    rect(s, MARGIN, Inches(4.5), Inches(0.9), Inches(0.035), fill=ACCENT,
         radius=False)

    tf = textbox(s, MARGIN, Inches(4.95), Inches(6.0), Inches(0.9))
    para(tf, "Zaid Sayyed", size=17, color=INK, bold=True, first=True,
         space_after=4)
    para(tf, "Chirag Kadam", size=17, color=INK, bold=True, space_after=0)

    # Quiet visual anchor
    rect(s, Inches(9.4), Inches(2.2), Inches(3.1), Inches(2.6),
         fill=SURFACE, outline=LINE)
    tf = textbox(s, Inches(9.7), Inches(2.5), Inches(2.5), Inches(2.0))
    para(tf, "Builder", size=15, color=INK, bold=True, first=True, space_after=6)
    para(tf, "Attacker", size=15, color=INK, bold=True, space_after=6)
    para(tf, "Evaluator", size=15, color=INK, bold=True, space_after=6)
    para(tf, "Fixer", size=15, color=INK, bold=True, space_after=6)
    para(tf, "Verifier", size=15, color=ACCENT, bold=True, space_after=0)


def s_problem(prs, n):
    s = blank(prs)
    slide_header(s, "The problem we set out to solve", "Context")

    tf = textbox(s, MARGIN, BODY_TOP, Inches(6.6), Inches(1.2))
    para(tf,
         "Most web applications today are collections of REST APIs. The "
         "security burden has moved to that API layer — and the most common "
         "flaw there is not a coding mistake a tool can pattern-match.",
         size=16, color=MUTED, first=True, space_after=0, line=1.3)

    bullets(s, [
        ("Broken authorization is #1.",
         "The top API risk is code that checks who you are, but forgets to "
         "check what you're allowed to touch."),
        ("It looks completely normal.",
         "The request is valid, authenticated, passes a firewall, returns 200. "
         "Only the meaning is wrong."),
        ("So scanners miss it.",
         "There is no signature for \"this user shouldn't own this record\" — "
         "it depends on the app's own data model."),
    ], MARGIN, Inches(3.35), Inches(6.6), size=15, gap=0.92)

    rect(s, Inches(8.0), BODY_TOP, Inches(4.5), Inches(3.5),
         fill=SURFACE, outline=LINE)
    tf = textbox(s, Inches(8.35), Inches(2.05), Inches(3.8), Inches(0.4))
    para(tf, "WHAT A VULNERABLE ENDPOINT LOOKS LIKE", size=10, color=FAINT,
         bold=True, first=True, space_after=10)
    tf = textbox(s, Inches(8.35), Inches(2.5), Inches(3.9), Inches(2.6))
    for line_text, col in [
        ("@app.get(\"/documents/{doc_id}\")", MUTED),
        ("def read(doc_id, user = Depends(auth)):", MUTED),
        ("    doc = DOCUMENTS.get(doc_id)", MUTED),
        ("    # authenticated, but never checks", DANGER),
        ("    # whether this user owns the doc", DANGER),
        ("    return doc", MUTED),
    ]:
        para(tf, line_text, size=11.5, color=col, first=(line_text.startswith("@app")),
             space_after=5, font=FONT_MONO, line=1.1)
    tf = textbox(s, Inches(8.35), Inches(4.55), Inches(3.9), Inches(0.6))
    para(tf, "Any logged-in user can read anyone's document.",
         size=12, color=DANGER, bold=True, first=True, space_after=0)

    footer(s, n)


def s_gap(prs, n):
    s = blank(prs)
    slide_header(s, "Why the existing options fall short", "Context")

    cols = [
        ("Traditional scanners", DANGER, DANGER_SOFT,
         ["Reliable and repeatable", "But cannot reason about your app's "
          "ownership rules", "So authorization flaws slip through"]),
        ("A single AI agent", WARN, WARN_SOFT,
         ["Can read and reason about code", "But reports things that aren't "
          "really there", "And confirms its own guesses"]),
        ("What we wanted", SUCCESS, SUCCESS_SOFT,
         ["Reason like the AI approach", "Prove it like a real attacker would",
          "Judge it with something independent"]),
    ]
    x = MARGIN
    cw = Inches(3.72)
    for title, col, soft, points in cols:
        rect(s, x, BODY_TOP, cw, Inches(3.4), fill=soft)
        rect(s, x, BODY_TOP, cw, Inches(0.075), fill=col, radius=False)
        tf = textbox(s, x + Inches(0.3), Inches(2.15), cw - Inches(0.6),
                     Inches(0.45))
        para(tf, title, size=17, color=col, bold=True, first=True,
             space_after=0)
        for i, pt in enumerate(points):
            tf2 = textbox(s, x + Inches(0.3), Inches(2.75) + Inches(0.62 * i),
                          cw - Inches(0.6), Inches(0.6))
            para(tf2, pt, size=13.5, color=MUTED, first=True, space_after=0,
                 line=1.15)
        x += cw + Inches(0.29)

    rect(s, MARGIN, Inches(5.65), CONTENT_W, Inches(0.95), fill=ACCENT_SOFT)
    tf = textbox(s, MARGIN + Inches(0.35), Inches(5.82), CONTENT_W - Inches(0.7),
                 Inches(0.7))
    para(tf,
         "Our approach: never report a vulnerability the system hasn't actually "
         "exploited — and never let the agent that found it be the one that "
         "confirms it.",
         size=16, color=ACCENT, bold=True, first=True, space_after=0, line=1.2)
    footer(s, n)


def s_what(prs, n):
    s = blank(prs)
    slide_header(s, "What ClairSec does", "Our solution")

    tf = textbox(s, MARGIN, BODY_TOP, Inches(11.0), Inches(0.6))
    para(tf,
         "You point it at a FastAPI project. It runs the app in a sealed "
         "container and puts five specialists to work on it.",
         size=17, color=MUTED, first=True, space_after=0)

    steps = [
        ("Builder", "Learns the API — routes, logins, who owns what"),
        ("Attacker", "Actually attacks it, and records every request"),
        ("Evaluator", "Judges the evidence, independently"),
        ("Fixer", "Writes a patch for what was confirmed"),
        ("Verifier", "Re-attacks it, and checks nothing broke"),
    ]
    x = MARGIN
    cw = Inches(2.16)
    for i, (name, desc) in enumerate(steps):
        rect(s, x, Inches(3.0), cw, Inches(1.85), fill=SURFACE, outline=LINE)
        rect(s, x, Inches(3.0), cw, Inches(0.075),
             fill=ACCENT if i < 4 else SUCCESS, radius=False)
        tf = textbox(s, x + Inches(0.18), Inches(3.2), cw - Inches(0.36),
                     Inches(0.35))
        para(tf, f"0{i+1}", size=11, color=FAINT, bold=True, first=True,
             space_after=2)
        tf = textbox(s, x + Inches(0.18), Inches(3.5), cw - Inches(0.36),
                     Inches(0.35))
        para(tf, name, size=16, color=INK, bold=True, first=True, space_after=4)
        tf = textbox(s, x + Inches(0.18), Inches(3.88), cw - Inches(0.36),
                     Inches(0.85))
        para(tf, desc, size=12, color=MUTED, first=True, space_after=0,
             line=1.15)
        if i < len(steps) - 1:
            arrow(s, x + cw + Inches(0.055), Inches(3.83))
        x += cw + Inches(0.33)

    rect(s, MARGIN, Inches(5.35), CONTENT_W, Inches(1.1), fill=SUCCESS_SOFT)
    tf = textbox(s, MARGIN + Inches(0.35), Inches(5.55), CONTENT_W - Inches(0.7),
                 Inches(0.8))
    para(tf,
         "Throughout all of this, your original code is never touched. Every "
         "change happens inside an isolated copy.",
         size=16, color=SUCCESS, bold=True, first=True, space_after=0)
    footer(s, n)


def s_principle(prs, n):
    s = blank(prs)
    slide_header(s, "The decision everything rests on", "Key idea")

    tf = textbox(s, MARGIN, BODY_TOP, Inches(11.4), Inches(0.9))
    para(tf,
         "An AI never decides whether a security test passed. Ordinary code "
         "does, by looking at what actually came back over HTTP.",
         size=19, color=INK, bold=True, first=True, space_after=0, line=1.25)

    rect(s, MARGIN, Inches(2.95), Inches(5.85), Inches(2.25),
         fill=DANGER_SOFT)
    tf = textbox(s, MARGIN + Inches(0.32), Inches(3.15), Inches(5.2),
                 Inches(0.4))
    para(tf, "IF THE MODEL JUDGED ITSELF", size=11, color=DANGER, bold=True,
         first=True, space_after=8)
    tf = textbox(s, MARGIN + Inches(0.32), Inches(3.55), Inches(5.25),
                 Inches(1.6))
    para(tf,
         "We would only be measuring whether the AI agrees with itself. "
         "It could confidently report a vulnerability that was never really "
         "there — and nothing in the system could catch it.",
         size=14.5, color=MUTED, first=True, space_after=0, line=1.25)

    rect(s, Inches(7.05), Inches(2.95), Inches(5.45), Inches(2.25),
         fill=SUCCESS_SOFT)
    tf = textbox(s, Inches(7.37), Inches(3.15), Inches(4.8), Inches(0.4))
    para(tf, "HOW WE ACTUALLY DO IT", size=11, color=SUCCESS, bold=True,
         first=True, space_after=8)
    tf = textbox(s, Inches(7.37), Inches(3.55), Inches(4.85), Inches(1.6))
    para(tf,
         "User A asks for User B's document. If the reply is 200 and contains "
         "B's data, that's a real flaw. That check is plain code — same input, "
         "same answer, every time.",
         size=14.5, color=MUTED, first=True, space_after=0, line=1.25)

    rect(s, MARGIN, Inches(5.55), CONTENT_W, Inches(1.0), fill=SURFACE,
         outline=LINE)
    tf = textbox(s, MARGIN + Inches(0.35), Inches(5.73), CONTENT_W - Inches(0.7),
                 Inches(0.7))
    para(tf,
         "The AI is used where it's genuinely good — understanding code and "
         "writing fixes. It is kept away from deciding what counts as proof.",
         size=15.5, color=INK, first=True, space_after=0, line=1.2)
    footer(s, n)


def s_stack(prs, n):
    s = blank(prs)
    slide_header(s, "How it's built", "Architecture")

    layers = [
        ("Desktop app", "Flutter · Dart · Riverpod",
         "What the user sees and clicks", ACCENT),
        ("Backend", "Python · FastAPI · MongoDB",
         "Runs the agents, owns all the logic", ACCENT),
        ("Isolation", "Docker · internal network",
         "Where the target app actually runs", SUCCESS),
    ]
    y = BODY_TOP
    for name, tech, desc, col in layers:
        rect(s, MARGIN, y, Inches(7.4), Inches(1.15), fill=SURFACE,
             outline=LINE)
        rect(s, MARGIN, y, Inches(0.075), Inches(1.15), fill=col, radius=False)
        tf = textbox(s, MARGIN + Inches(0.35), y + Inches(0.16),
                     Inches(3.2), Inches(0.4))
        para(tf, name, size=17, color=INK, bold=True, first=True, space_after=2)
        tf = textbox(s, MARGIN + Inches(0.35), y + Inches(0.58),
                     Inches(4.0), Inches(0.4))
        para(tf, tech, size=12, color=col, first=True, space_after=0,
             font=FONT_MONO)
        tf = textbox(s, MARGIN + Inches(4.3), y + Inches(0.36),
                     Inches(2.9), Inches(0.5))
        para(tf, desc, size=13, color=MUTED, first=True, space_after=0,
             line=1.1)
        y += Inches(1.35)

    rect(s, Inches(8.85), BODY_TOP, Inches(3.65), Inches(3.65),
         fill=ACCENT_SOFT)
    tf = textbox(s, Inches(9.15), Inches(2.05), Inches(3.1), Inches(0.4))
    para(tf, "SAFETY RULES", size=11, color=ACCENT, bold=True, first=True,
         space_after=10)
    for i, item in enumerate([
        "Target runs with no network access out",
        "No root, no writable filesystem",
        "The AI can propose, never execute",
        "Your source is never modified",
    ]):
        tf = textbox(s, Inches(9.15), Inches(2.5) + Inches(0.78 * i),
                     Inches(3.1), Inches(0.75))
        para(tf, item, size=13, color=MUTED, first=True, space_after=0,
             line=1.15)
    footer(s, n)


def s_testing(prs, n):
    s = blank(prs)
    slide_header(s, "How we know it actually works", "Method")

    tf = textbox(s, MARGIN, BODY_TOP, Inches(11.2), Inches(0.6))
    para(tf,
         "We built two versions of the same small API — so we can measure both "
         "what it catches and what it wrongly flags.",
         size=17, color=MUTED, first=True, space_after=0)

    rect(s, MARGIN, Inches(2.85), Inches(5.85), Inches(2.5), fill=DANGER_SOFT)
    tf = textbox(s, MARGIN + Inches(0.32), Inches(3.05), Inches(5.2),
                 Inches(0.45))
    para(tf, "The vulnerable version", size=17, color=DANGER, bold=True,
         first=True, space_after=8)
    for i, item in enumerate([
        "3 flaws planted on purpose, recorded before any scan",
        "Broken authorization · mass assignment · misconfiguration",
        "Every flaw has a script that proves it is exploitable",
    ]):
        tf = textbox(s, MARGIN + Inches(0.32), Inches(3.6) + Inches(0.56 * i),
                     Inches(5.25), Inches(0.55))
        para(tf, item, size=13.5, color=MUTED, first=True, space_after=0,
             line=1.15)

    rect(s, Inches(7.05), Inches(2.85), Inches(5.45), Inches(2.5),
         fill=SUCCESS_SOFT)
    tf = textbox(s, Inches(7.37), Inches(3.05), Inches(4.8), Inches(0.45))
    para(tf, "The secure version", size=17, color=SUCCESS, bold=True,
         first=True, space_after=8)
    for i, item in enumerate([
        "Same endpoints, same behaviour — but written correctly",
        "Anything reported here is a false alarm, by definition",
        "Without this, a tool could 'pass' by flagging everything",
    ]):
        tf = textbox(s, Inches(7.37), Inches(3.6) + Inches(0.56 * i),
                     Inches(4.85), Inches(0.55))
        para(tf, item, size=13.5, color=MUTED, first=True, space_after=0,
             line=1.15)

    rect(s, MARGIN, Inches(5.7), CONTENT_W, Inches(0.9), fill=SURFACE,
         outline=LINE)
    tf = textbox(s, MARGIN + Inches(0.35), Inches(5.87), CONTENT_W - Inches(0.7),
                 Inches(0.6))
    para(tf,
         "We wrote both applications ourselves so the AI could not have seen "
         "them, or their fixes, anywhere before.",
         size=15, color=INK, first=True, space_after=0)
    footer(s, n)


def s_results(prs, n):
    s = blank(prs)
    slide_header(s, "Results so far", "Findings")

    stat_card(s, MARGIN, BODY_TOP, Inches(2.85), Inches(1.6), "3 / 3",
              "Planted flaws found", ACCENT, ACCENT_SOFT, "on the vulnerable app")
    stat_card(s, MARGIN + Inches(3.05), BODY_TOP, Inches(2.85), Inches(1.6),
              "0", "False alarms", SUCCESS, SUCCESS_SOFT, "on the secure app")
    stat_card(s, MARGIN + Inches(6.1), BODY_TOP, Inches(2.85), Inches(1.6),
              "3 / 3", "Fixes verified", SUCCESS, SUCCESS_SOFT,
              "attack blocked, app still works")
    stat_card(s, MARGIN + Inches(9.15), BODY_TOP, Inches(2.45), Inches(1.6),
              "~15s", "Full scan", ACCENT, ACCENT_SOFT, "after the first build")

    tf = textbox(s, MARGIN, Inches(3.75), Inches(11.4), Inches(0.4))
    para(tf, "WHAT IT FOUND", size=11, color=FAINT, bold=True, first=True,
         space_after=0)

    rows = [
        ("Broken object authorization", "GET /documents/{doc_id}", "CWE-639",
         "Fix verified"),
        ("Mass assignment", "PUT /users/{user_id}/profile", "CWE-915",
         "Fix verified"),
        ("Security misconfiguration", "GET /debug/config", "CWE-16",
         "Fix verified"),
    ]
    y = Inches(4.15)
    for i, (name, route, cwe, status) in enumerate(rows):
        rect(s, MARGIN, y, CONTENT_W, Inches(0.62),
             fill=SURFACE if i % 2 == 0 else WHITE, outline=LINE)
        tf = textbox(s, MARGIN + Inches(0.28), y + Inches(0.16),
                     Inches(3.6), Inches(0.4))
        para(tf, name, size=14, color=INK, bold=True, first=True, space_after=0)
        tf = textbox(s, MARGIN + Inches(4.0), y + Inches(0.17),
                     Inches(3.9), Inches(0.4))
        para(tf, route, size=12, color=MUTED, first=True, space_after=0,
             font=FONT_MONO)
        tf = textbox(s, MARGIN + Inches(8.0), y + Inches(0.17),
                     Inches(1.4), Inches(0.4))
        para(tf, cwe, size=12, color=FAINT, first=True, space_after=0,
             font=FONT_MONO)
        pill(s, MARGIN + Inches(9.5), y + Inches(0.13), Inches(1.7),
             Inches(0.36), status, SUCCESS_SOFT, SUCCESS, size=11.5)
        y += Inches(0.72)
    footer(s, n)


def s_proof(prs, n):
    s = blank(prs)
    slide_header(s, "\"Fixed\" has to mean something", "Findings")

    tf = textbox(s, MARGIN, BODY_TOP, Inches(11.3), Inches(0.85))
    para(tf,
         "Any tool can stop an attack by deleting the feature it targets. So we "
         "refuse to call a fix successful unless two things are true at once.",
         size=17, color=MUTED, first=True, space_after=0, line=1.25)

    checks = [
        ("The attack no longer works",
         "We rebuild the app with the patch and run the exact same attack again.",
         SUCCESS),
        ("Nothing else broke",
         "We run the app's own test suite. All 6 tests still pass — the feature "
         "still works for legitimate users.", SUCCESS),
        ("It holds up to a variation",
         "We try a modified version of the attack, to check we fixed the real "
         "weakness and not just one route to it.", SUCCESS),
    ]
    y = Inches(3.0)
    for title, desc, col in checks:
        rect(s, MARGIN, y, CONTENT_W, Inches(0.98), fill=SUCCESS_SOFT)
        tick = s.shapes.add_shape(MSO_SHAPE.OVAL, MARGIN + Inches(0.3),
                                  y + Inches(0.27), Inches(0.42), Inches(0.42))
        tick.fill.solid()
        tick.fill.fore_color.rgb = col
        tick.line.fill.background()
        tick.shadow.inherit = False
        tf = textbox(s, MARGIN + Inches(0.3), y + Inches(0.27), Inches(0.42),
                     Inches(0.42), align=PP_ALIGN.CENTER,
                     anchor=MSO_ANCHOR.MIDDLE)
        para(tf, "✓", size=17, color=WHITE, bold=True, first=True,
             space_after=0)
        tf = textbox(s, MARGIN + Inches(0.95), y + Inches(0.13),
                     Inches(10.2), Inches(0.38))
        para(tf, title, size=16, color=INK, bold=True, first=True,
             space_after=0)
        tf = textbox(s, MARGIN + Inches(0.95), y + Inches(0.5),
                     Inches(10.4), Inches(0.42))
        para(tf, desc, size=13, color=MUTED, first=True, space_after=0)
        y += Inches(1.12)

    rect(s, MARGIN, Inches(6.42), CONTENT_W, Inches(0.62), fill=ACCENT_SOFT)
    tf = textbox(s, MARGIN + Inches(0.35), Inches(6.53), CONTENT_W - Inches(0.7),
                 Inches(0.45))
    para(tf,
         "All three checks passed on all three fixes.",
         size=15, color=ACCENT, bold=True, first=True, space_after=0)
    footer(s, n)


def s_screens(prs, n):
    s = blank(prs)
    slide_header(s, "What it looks like to use", "Demo")

    screens = [
        ("Projects", "Pick a project. One click puts it in a sealed container."),
        ("Scan", "Watch the five agents work through the pipeline."),
        ("Vulnerabilities", "Each finding with severity, endpoint and evidence."),
        ("Fix Review", "The actual code change, side by side with the flaw."),
    ]
    x = MARGIN
    cw = Inches(2.79)
    for i, (title, desc) in enumerate(screens):
        rect(s, x, BODY_TOP, cw, Inches(2.9), fill=SURFACE, outline=LINE)
        rect(s, x + Inches(0.22), Inches(2.08), cw - Inches(0.44),
             Inches(1.45), fill=WHITE, outline=LINE)
        # suggestion of a UI inside the frame
        rect(s, x + Inches(0.36), Inches(2.24), cw - Inches(1.5),
             Inches(0.12), fill=ACCENT, radius=False)
        for r in range(3):
            rect(s, x + Inches(0.36), Inches(2.5) + Inches(0.26 * r),
                 cw - Inches(0.72), Inches(0.14), fill=LINE, radius=False)
        tf = textbox(s, x + Inches(0.22), Inches(3.62), cw - Inches(0.44),
                     Inches(0.35))
        para(tf, title, size=15, color=INK, bold=True, first=True,
             space_after=4)
        tf = textbox(s, x + Inches(0.22), Inches(3.95), cw - Inches(0.44),
                     Inches(0.85))
        para(tf, desc, size=12, color=MUTED, first=True, space_after=0,
             line=1.15)
        if i < len(screens) - 1:
            arrow(s, x + cw + Inches(0.03), Inches(3.2))
        x += cw + Inches(0.29)

    rect(s, MARGIN, Inches(5.3), CONTENT_W, Inches(1.1), fill=ACCENT_SOFT)
    tf = textbox(s, MARGIN + Inches(0.35), Inches(5.5), CONTENT_W - Inches(0.7),
                 Inches(0.8))
    para(tf,
         "Replace this slide with your own screenshots before presenting — the "
         "Fix Review screen showing a real diff is the strongest one to show.",
         size=14, color=ACCENT, italic=True, first=True, space_after=0,
         line=1.2)
    footer(s, n)


def s_status(prs, n):
    s = blank(prs)
    slide_header(s, "Where we are", "Progress")

    done = [
        ("Phase 0–2", "Setup, desktop app, project import"),
        ("Phase 3", "Docker isolation and container lifecycle"),
        ("Phase 4", "Builder agent and the whole AI layer"),
        ("Phase 5", "Attacker agent and the deterministic checks"),
        ("Phase 6", "Evaluator agent, severity scoring"),
        ("Phase 7", "Fixer agent and patch safety"),
        ("Phase 8", "Re-testing and verification"),
    ]
    tf = textbox(s, MARGIN, BODY_TOP, Inches(6.4), Inches(0.4))
    para(tf, "COMPLETED", size=11, color=SUCCESS, bold=True, first=True,
         space_after=0)
    y = Inches(2.3)
    for tag, desc in done:
        rect(s, MARGIN, y, Inches(6.4), Inches(0.52), fill=SUCCESS_SOFT)
        tf = textbox(s, MARGIN + Inches(0.25), y + Inches(0.11),
                     Inches(1.3), Inches(0.35))
        para(tf, tag, size=12.5, color=SUCCESS, bold=True, first=True,
             space_after=0)
        tf = textbox(s, MARGIN + Inches(1.6), y + Inches(0.11),
                     Inches(4.6), Inches(0.35))
        para(tf, desc, size=13, color=MUTED, first=True, space_after=0)
        y += Inches(0.6)

    tf = textbox(s, Inches(8.1), BODY_TOP, Inches(4.4), Inches(0.4))
    para(tf, "STILL TO COME", size=11, color=FAINT, bold=True, first=True,
         space_after=0)
    y = Inches(2.3)
    for tag, desc in [
        ("Phase 9", "Live progress streaming in the UI"),
        ("Phase 10", "Exportable reports"),
        ("Phase 11", "Full comparison study"),
    ]:
        rect(s, Inches(8.1), y, Inches(4.4), Inches(0.52), fill=SURFACE,
             outline=LINE)
        tf = textbox(s, Inches(8.32), y + Inches(0.11), Inches(1.3),
                     Inches(0.35))
        para(tf, tag, size=12.5, color=FAINT, bold=True, first=True,
             space_after=0)
        tf = textbox(s, Inches(9.6), y + Inches(0.11), Inches(2.8),
                     Inches(0.35))
        para(tf, desc, size=13, color=MUTED, first=True, space_after=0)
        y += Inches(0.6)

    rect(s, Inches(8.1), Inches(4.25), Inches(4.4), Inches(1.85),
         fill=ACCENT_SOFT)
    tf = textbox(s, Inches(8.35), Inches(4.45), Inches(3.9), Inches(0.35))
    para(tf, "BUILT SO FAR", size=11, color=ACCENT, bold=True, first=True,
         space_after=8)
    for i, item in enumerate([
        "171 automated tests, all passing",
        "5 agents working end to end",
        "16 specification documents",
    ]):
        tf = textbox(s, Inches(8.35), Inches(4.85) + Inches(0.42 * i),
                     Inches(3.9), Inches(0.4))
        para(tf, item, size=13, color=MUTED, first=True, space_after=0)
    footer(s, n)


def s_learned(prs, n):
    s = blank(prs)
    slide_header(s, "What we ran into", "Reflection")

    items = [
        ("Isolation was harder than expected",
         "Sealing the container off from the network also blocked our own health "
         "checks. We had to add a small proxy that sits on both sides."),
        ("A convincing fix isn't always a good fix",
         "Early on we only checked that the attack stopped working. Then we "
         "realised deleting the endpoint would 'pass' that test too."),
        ("The AI had to be kept on a short leash",
         "We stopped letting it produce file paths or commands directly. It "
         "proposes; our code decides whether the proposal is allowed."),
        ("Testing broke our own app",
         "Our test suite was overwriting the running app's login token. Small "
         "bug, but it cost us a lot of confusing debugging."),
    ]
    y = BODY_TOP
    for title, desc in items:
        rect(s, MARGIN, y, CONTENT_W, Inches(1.08), fill=SURFACE,
             outline=LINE)
        rect(s, MARGIN, y, Inches(0.075), Inches(1.08), fill=WARN,
             radius=False)
        tf = textbox(s, MARGIN + Inches(0.35), y + Inches(0.15),
                     Inches(11.2), Inches(0.38))
        para(tf, title, size=16, color=INK, bold=True, first=True,
             space_after=0)
        tf = textbox(s, MARGIN + Inches(0.35), y + Inches(0.53),
                     Inches(11.3), Inches(0.5))
        para(tf, desc, size=13, color=MUTED, first=True, space_after=0,
             line=1.15)
        y += Inches(1.22)
    footer(s, n)


def s_next(prs, n):
    s = blank(prs)
    slide_header(s, "What's next", "Plan")

    items = [
        ("Live progress in the UI",
         "Watch each agent work in real time instead of waiting for the result."),
        ("Exportable reports",
         "A document a developer can act on without opening our app."),
        ("More vulnerability types",
         "We deliberately started with three we can prove. Next: server-side "
         "request forgery and rate-limit abuse."),
        ("The comparison study",
         "Measure our approach against a traditional scanner and a single-agent "
         "setup, on the same projects, with proper statistics."),
    ]
    y = BODY_TOP
    for i, (title, desc) in enumerate(items):
        rect(s, MARGIN, y, CONTENT_W, Inches(1.02), fill=WHITE, outline=LINE)
        num = s.shapes.add_shape(MSO_SHAPE.OVAL, MARGIN + Inches(0.3),
                                 y + Inches(0.28), Inches(0.46), Inches(0.46))
        num.fill.solid()
        num.fill.fore_color.rgb = ACCENT_SOFT
        num.line.fill.background()
        num.shadow.inherit = False
        tf = textbox(s, MARGIN + Inches(0.3), y + Inches(0.28), Inches(0.46),
                     Inches(0.46), align=PP_ALIGN.CENTER,
                     anchor=MSO_ANCHOR.MIDDLE)
        para(tf, str(i + 1), size=14, color=ACCENT, bold=True, first=True,
             space_after=0)
        tf = textbox(s, MARGIN + Inches(1.0), y + Inches(0.14),
                     Inches(10.2), Inches(0.38))
        para(tf, title, size=16, color=INK, bold=True, first=True,
             space_after=0)
        tf = textbox(s, MARGIN + Inches(1.0), y + Inches(0.5),
                     Inches(10.4), Inches(0.45))
        para(tf, desc, size=13, color=MUTED, first=True, space_after=0,
             line=1.15)
        y += Inches(1.16)
    footer(s, n)


def s_close(prs, n):
    s = blank(prs)
    rect(s, Emu(0), Emu(0), Inches(0.22), H, fill=ACCENT, radius=False)

    tf = textbox(s, MARGIN, Inches(2.3), Inches(11.0), Inches(0.9))
    para(tf, "Thank you", size=44, color=INK, bold=True, first=True,
         space_after=0)

    tf = textbox(s, MARGIN, Inches(3.3), Inches(10.2), Inches(0.8))
    para(tf,
         "A security tool is only useful if you can trust what it tells you. "
         "That is what we set out to build.",
         size=19, color=MUTED, first=True, space_after=0, line=1.25)

    rect(s, MARGIN, Inches(4.35), Inches(0.9), Inches(0.035), fill=ACCENT,
         radius=False)

    tf = textbox(s, MARGIN, Inches(4.8), Inches(6.0), Inches(0.9))
    para(tf, "Zaid Sayyed", size=17, color=INK, bold=True, first=True,
         space_after=4)
    para(tf, "Chirag Kadam", size=17, color=INK, bold=True, space_after=0)

    tf = textbox(s, Inches(8.6), Inches(4.85), Inches(3.9), Inches(0.6),
                 align=PP_ALIGN.RIGHT)
    para(tf, "Questions welcome", size=15, color=ACCENT, bold=True,
         first=True, space_after=0)
    footer(s, n)


def build():
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    s_title(prs)
    n = 2
    for fn in (s_problem, s_gap, s_what, s_principle, s_stack, s_testing,
               s_results, s_proof, s_screens, s_status, s_learned, s_next):
        fn(prs, n)
        n += 1
    s_close(prs, n)

    prs.save(OUT)
    return OUT, len(prs.slides._sldIdLst)


if __name__ == "__main__":
    path, count = build()
    print(f"Saved: {path}")
    print(f"Slides: {count}")
