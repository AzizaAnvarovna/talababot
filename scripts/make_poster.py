"""Bosma eʼlon: A4 varaq, QR kod bilan (dars xonalari va yotoqxonaga ilish uchun).

python scripts/make_poster.py docs/pilot/Elon_QR_A4.docx
"""

import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
QR = ROOT / "docs" / "pilot" / "qr_buxdu_talababot.png"
FONT = "Arial"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
BLUE = RGBColor(0x2A, 0x78, 0xD6)
GREY = RGBColor(0x55, 0x55, 0x55)


def line(doc, text, size, bold=False, color=None, before=0, after=0, italic=False):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    run = p.add_run(text)
    run.font.name = FONT
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    return p


def rule(doc, before=6, after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    border = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    for key, value in (("val", "single"), ("sz", "12"), ("space", "1"), ("color", "2A78D6")):
        bottom.set(qn(f"w:{key}"), value)
    border.append(bottom)
    p._p.get_or_add_pPr().append(border)


def main(out: Path) -> None:
    doc = Document()
    doc.styles["Normal"].font.name = FONT
    doc.styles["Normal"].element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.left_margin = section.right_margin = Cm(1.8)
    section.top_margin = section.bottom_margin = Cm(1.5)

    line(doc, "Savolingiz bormi?", 44, bold=True, color=NAVY, after=2)
    line(doc, "Telegram botga yozing!", 30, bold=True, color=BLUE, after=6)
    rule(doc)
    line(
        doc,
        "Stipendiya  •  Yotoqxona  •  Hujjatlar\nOʻquv jarayoni  •  Akademik taʼtil",
        17,
        color=GREY,
        before=4,
        after=10,
    )

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(QR), width=Cm(11.5))

    line(doc, "@buxdu_talababot", 34, bold=True, color=NAVY, before=2, after=10)
    line(
        doc,
        "1. Telefon kamerasini QR kodga qarating\n"
        "2. Telegram'da botni oching va “Start” ni bosing\n"
        "3. Savolingizni oddiy matn bilan yozing — lotin yoki kirillda",
        15,
        after=10,
    )
    rule(doc, before=2, after=4)
    line(
        doc,
        "Ilmiy tadqiqot loyihasi. Suhbatlar anonim saqlanadi: ism va telefon raqamingiz "
        "saqlanmaydi.\nSuhbat oxirida botni 1 dan 5 gacha baholang. Rahmat!",
        11,
        color=GREY,
        italic=True,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    print(f"Eʼlon saqlandi: {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "pilot" / "Elon_QR_A4.docx")
