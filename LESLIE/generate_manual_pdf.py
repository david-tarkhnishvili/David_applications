from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "USER_MANUAL.md"
OUTPUT = ROOT / "USER_MANUAL.pdf"


def _build_styles():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ManualTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "ManualHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        spaceBefore=10,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ManualBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        spaceAfter=5,
    )
    bullet_style = ParagraphStyle(
        "ManualBullet",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-8,
        bulletIndent=4,
        spaceAfter=3,
    )
    code_style = ParagraphStyle(
        "ManualCode",
        parent=body_style,
        fontName="Courier",
        fontSize=9,
        leading=12,
        leftIndent=12,
        spaceAfter=3,
    )
    return title_style, heading_style, body_style, bullet_style, code_style


def markdown_to_story() -> list:
    title_style, heading_style, body_style, bullet_style, code_style = _build_styles()
    story: list = []
    in_code_block = False

    for raw_line in SOURCE.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_block = not in_code_block
            if not in_code_block:
                story.append(Spacer(1, 0.08 * inch))
            continue

        if in_code_block:
            if stripped:
                story.append(Paragraph(stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), code_style))
            else:
                story.append(Spacer(1, 0.06 * inch))
            continue

        if not stripped:
            story.append(Spacer(1, 0.08 * inch))
            continue

        safe = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        if stripped.startswith("# "):
            story.append(Paragraph(safe[2:], title_style))
        elif stripped.startswith("## "):
            story.append(Paragraph(safe[3:], heading_style))
        elif stripped.startswith("### "):
            story.append(Paragraph(safe[4:], heading_style))
        elif stripped.startswith("- "):
            story.append(Paragraph(safe[2:], bullet_style, bulletText="•"))
        elif stripped[0].isdigit() and ". " in stripped[:4]:
            number, text = stripped.split(". ", 1)
            story.append(Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), bullet_style, bulletText=f"{number}."))
        else:
            story.append(Paragraph(safe, body_style))

    return story


def main() -> None:
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Leslie Population Dynamics App Manual",
        author="OpenAI Codex",
    )
    doc.build(markdown_to_story())
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
