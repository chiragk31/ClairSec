"""
Builds the ClairSec project report (Chapters 1-3) as a .docx file, then
converts it to PDF.

Run:  ../venv/Scripts/python.exe build_report.py
"""
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Inches

from report_content import (
    CH1, CH2, CH3, TITLE, REFERENCES,
    GAP_TABLE_HEADERS, GAP_TABLE_ROWS, COMPONENTS_TABLE,
)

OUT_DIR = Path(__file__).parent
DOCX_PATH = OUT_DIR / "ClairSec_Project_Report_Chapters_1_to_3.docx"

BODY_FONT = "Calibri"
BODY_SIZE = Pt(11)


def _shade(cell, hex_colour: str) -> None:
    """Apply a background fill to a table cell."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_colour)
    tc_pr.append(shd)


def setup_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = BODY_FONT
    normal.font.size = BODY_SIZE
    pf = normal.paragraph_format
    pf.space_after = Pt(8)
    pf.line_spacing = 1.15


def add_title(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(14)
    run.font.name = BODY_FONT
    p.paragraph_format.space_after = Pt(16)


def add_h1(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(13)
    run.font.name = BODY_FONT
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(10)


def add_h2(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(12)
    run.font.name = BODY_FONT
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(6)


def add_h3(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(11)
    run.font.name = BODY_FONT
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)


def add_para(doc: Document, text: str) -> None:
    p = doc.add_paragraph(text)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY


def add_bullet(doc: Document, text: str) -> None:
    p = doc.add_paragraph(text, style="List Bullet")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(4)


def add_numbered(doc: Document, text: str) -> None:
    p = doc.add_paragraph(text, style="List Number")
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(4)


def add_flow(doc: Document, steps: list[str]) -> None:
    """Vertical arrow flow, matching the department report's style."""
    for i, step in enumerate(steps):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        run = p.add_run(step)
        run.font.size = Pt(10.5)
        run.font.name = BODY_FONT
        run.bold = True
        if i < len(steps) - 1:
            arrow = doc.add_paragraph()
            arrow.alignment = WD_ALIGN_PARAGRAPH.CENTER
            arrow.paragraph_format.space_after = Pt(0)
            arrow.paragraph_format.space_before = Pt(0)
            a = arrow.add_run("↓")
            a.font.size = Pt(10.5)
    doc.add_paragraph()


def add_table(doc: Document, headers: list[str], rows: list[list[str]],
              widths: list[float] | None = None) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        para = hdr[i].paragraphs[0]
        run = para.add_run(h)
        run.bold = True
        run.font.size = Pt(9.5)
        run.font.name = BODY_FONT
        _shade(hdr[i], "D9E2F3")

    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            para = cells[i].paragraphs[0]
            run = para.add_run(val)
            run.font.size = Pt(9)
            run.font.name = BODY_FONT
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT

    if widths:
        for row in table.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)

    doc.add_paragraph()


def render_blocks(doc: Document, blocks) -> None:
    for kind, value in blocks:
        if kind == "h1":
            add_h1(doc, value)
        elif kind == "h2":
            add_h2(doc, value)
        elif kind == "h3":
            add_h3(doc, value)
        elif kind == "p":
            add_para(doc, value)
        elif kind == "bullet":
            add_bullet(doc, value)
        elif kind == "num":
            add_numbered(doc, value)
        elif kind == "flow":
            add_flow(doc, value)
        elif kind == "gap_table":
            add_table(
                doc, GAP_TABLE_HEADERS, GAP_TABLE_ROWS,
                widths=[0.45, 0.6, 1.5, 0.5, 1.7, 1.5, 1.7],
            )
        elif kind == "components_table":
            add_table(
                doc, COMPONENTS_TABLE[0], COMPONENTS_TABLE[1:],
                widths=[1.9, 4.6],
            )


def add_page_number_footer(doc: Document) -> None:
    section = doc.sections[0]
    footer_para = section.footer.paragraphs[0]
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    run = footer_para.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)


def build() -> Path:
    doc = Document()
    setup_styles(doc)

    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    add_page_number_footer(doc)

    add_title(doc, TITLE)
    render_blocks(doc, CH1)

    doc.add_page_break()
    render_blocks(doc, CH2)

    doc.add_page_break()
    render_blocks(doc, CH3)

    doc.add_page_break()
    add_h1(doc, "REFERENCES")
    for i, ref in enumerate(REFERENCES, start=1):
        p = doc.add_paragraph(f"[{i}]  {ref}")
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.space_after = Pt(6)

    doc.save(DOCX_PATH)
    return DOCX_PATH


if __name__ == "__main__":
    path = build()
    print(f"DOCX written: {path}")
