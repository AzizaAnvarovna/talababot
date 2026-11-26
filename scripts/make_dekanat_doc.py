# ruff: noqa: E501
"""Dekanat uchun: ruxsat soʻrovi xati + bot haqida + 34 mavzu boʻyicha javoblar shakli."""

import sys
from pathlib import Path

import openpyxl
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

TEMPLATE = Path("data/Murojaatlar_yigish_shabloni.xlsx")
OUT = Path(sys.argv[1])
# --faqat-jadval: ariza va bot haqidagi sahifalarsiz, faqat dekanat toʻldiradigan jadval
ONLY_TABLE = "--faqat-jadval" in sys.argv[2:]

NAMES = {
    "dars_jadvali": "Dars jadvali",
    "imtihon_jadvali": "Imtihon (sessiya) jadvali",
    "qayta_topshirish": "Qarzdor fanni qayta topshirish",
    "baho_etiroz": "Bahoga eʼtiroz (apelyatsiya)",
    "kredit_reyting": "Kredit tizimi, reyting, GPA",
    "davomat": "Davomat, dars qoldirish",
    "hemis": "HEMIS tizimi",
    "stipendiya_muddati": "Stipendiya toʻlanadigan kun",
    "stipendiya_miqdori": "Stipendiya miqdori",
    "stipendiya_tushmadi": "Stipendiya tushmasa",
    "stipendiya_kartasi": "Stipendiya kartasi",
    "stipendiya_shartlari": "Stipendiya olish shartlari",
    "ijtimoiy_yordam": "Ijtimoiy stipendiya va yordam",
    "joy_olish": "Yotoqxonaga joylashish",
    "yotoqxona_tolovi": "Yotoqxona toʻlovi",
    "yotoqxona_hujjatlari": "Yotoqxona uchun hujjatlar",
    "xona_almashtirish": "Xonani almashtirish, nizolar",
    "ichki_tartib": "Yotoqxona ichki tartibi",
    "oqish_joyidan_malumotnoma": "Oʻqish joyidan maʼlumotnoma",
    "transkript": "Transkript (baholar varaqasi)",
    "talaba_guvohnomasi": "Talabalik guvohnomasi",
    "kontrakt_tolovi": "Kontrakt toʻlovi",
    "ariza_yozish": "Ariza yozish va topshirish",
    "diplom": "Diplom",
    "akademik_tatil": "Akademik taʼtil olish",
    "tatildan_qaytish": "Akademik taʼtildan qaytish",
    "boshqa_otmga_kochirish": "Boshqa OTMga / OTMdan koʻchirish",
    "talim_shaklini_ozgartirish": "Yoʻnalish yoki taʼlim shaklini oʻzgartirish",
    "qayta_tiklanish": "Oʻqishni qayta tiklash",
    "kutubxona": "Kutubxona",
    "internet": "Universitet internet (Wi-Fi)",
    "togaraklar": "Toʻgaraklar",
    "harbiy_hisob": "Harbiy hisob, xizmatdan kechiktirish",
    "tibbiy_yordam": "Tibbiy yordam",
}

FONT = "Times New Roman"
SHADE_HEAD = "D9E2F3"
SHADE_CAT = "F2F2F2"


def shade(cell, color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), color)
    tc_pr.append(shd)


def repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    tr_pr.append(el)


def no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    tr_pr.append(OxmlElement("w:cantSplit"))


def para(doc_or_cell, text="", bold=False, size=12, align=None, italic=False, after=6, color=None):
    p = doc_or_cell.add_paragraph()
    if text:
        r = p.add_run(text)
        r.bold, r.italic = bold, italic
        r.font.size = Pt(size)
        if color:
            r.font.color.rgb = RGBColor.from_string(color)
    if align:
        p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    return p


def bullet(doc, text):
    p = doc.add_paragraph(style="List Bullet")
    p.add_run(text)
    p.paragraph_format.space_after = Pt(3)
    return p


def heading(doc, text, level=1):
    h = doc.add_heading(text, level=level)
    for r in h.runs:
        r.font.name = FONT
        r.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    return h


# ---------- maʼlumot ----------
ws = openpyxl.load_workbook(TEMPLATE, read_only=True)["Bilimlar bazasi"]
rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r and r[1]]
assert len(rows) == 34, len(rows)

doc = Document()
st = doc.styles["Normal"]
st.font.name = FONT
st.font.size = Pt(12)
st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
for name, size in (("Heading 1", 15), ("Heading 2", 13)):
    s = doc.styles[name]
    s.font.name, s.font.size, s.font.bold = FONT, Pt(size), True
    s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(12), Pt(6)
    s.paragraph_format.keep_with_next = True

sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.left_margin, sec.right_margin = Cm(2.5), Cm(1.5)
sec.top_margin, sec.bottom_margin = Cm(2), Cm(2)

if not ONLY_TABLE:
    # ---------- 1. Ariza ----------
    for line in (
        "[Fakultet nomi] fakulteti dekani",
        "[F.I.Sh.]ga",
        "[Yoʻnalish] magistranti",
        "[F.I.Sh.]dan",
    ):
        para(doc, line, align=WD_ALIGN_PARAGRAPH.RIGHT, after=0)
    para(doc, after=12)
    para(doc, "ARIZA", bold=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER, after=12)

    body = [
        "Men magistrlik dissertatsiyam doirasida (ilmiy rahbar: prof. Eshankulov H.I.) talabalarning "
        "tez-tez beriladigan savollariga avtomatik javob beradigan “TalabaBot” Telegram botini ishlab chiqdim "
        "(@buxdu_talababot). Bot talaba savolini tushunib, rasmiy tasdiqlangan javobni beradi, javobini "
        "bilmagan holatda esa savolni masʼul xodimga yoʻnaltiradi.",
        "Dissertatsiyaning tajriba qismi uchun botni 3 hafta davomida talabalar ishtirokida sinovdan "
        "oʻtkazish (pilot) rejalashtirilgan. Shu munosabat bilan Sizdan quyidagilarni soʻrayman:",
    ]
    for t in body:
        p = para(doc, t, after=6)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.first_line_indent = Cm(1.25)
    for t in (
        "bot havolasi va QR kodini fakultet talabalari guruhlariga tarqatishga ruxsat berishingizni;",
        "ilovadagi shakl boʻyicha talabalar koʻp beradigan 34 ta savolga rasmiy javoblarni "
        "tegishli xodimlar orqali tayyorlab berishda yordam koʻrsatishingizni.",
    ):
        p = doc.add_paragraph(style="List Number")
        p.add_run(t)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p = para(
        doc,
        "Bot talabalarning ismi va telefon raqamini saqlamaydi, foydalanuvchilar anonim identifikator "
        "bilan qayd etiladi, maʼlumotlar faqat ilmiy tadqiqot maqsadida ishlatiladi.",
    )
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.first_line_indent = Cm(1.25)
    para(doc, after=6)
    para(doc, "Ilova: bot haqida qisqacha maʼlumot va javoblar shakli.", italic=True, after=24)
    t = doc.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "“___” __________ 2026-yil"
    t.cell(0, 1).text = "_____________ [F.I.Sh.]"
    t.cell(0, 1).paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # ---------- 2. Bot haqida ----------
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    heading(doc, "Ilova. “TalabaBot” haqida qisqacha maʼlumot")
    heading(doc, "Bot nima qiladi", 2)
    for t in (
        "Talaba Telegram orqali savolini oʻz soʻzlari bilan yozadi (lotin yoki kirill harflarida).",
        "Bot savolning mavzusini aniqlaydi (stipendiya, yotoqxona, hujjatlar va h.k.) va bilimlar bazasidagi "
        "rasmiy javobni beradi.",
        "Javob topilmasa yoki talaba javobdan qoniqmasa, savol masʼul xodimga yoʻnaltiriladi.",
        "Bot faqat dekanat tasdiqlagan javoblarni beradi, oʻzidan javob toʻqimaydi.",
    ):
        bullet(doc, t)
    heading(doc, "Pilot qanday oʻtadi", 2)
    for t in (
        "Muddati: 3 hafta.",
        "Bot havolasi va QR kod guruh sardorlari orqali guruhlarga tarqatiladi.",
        "Talabalardan qatnashishga rozilik soʻraladi; ism va telefon raqami saqlanmaydi.",
        "Natijalar (savollar soni, toʻgʻri javoblar ulushi, talabalar fikri) dissertatsiyada umumlashtirilgan "
        "holda keltiriladi.",
    ):
        bullet(doc, t)
    heading(doc, "Dekanatdan nima soʻraladi", 2)
    for t in (
        "Keyingi sahifalardagi jadvalda talabalar koʻp beradigan 34 ta savol mavzusi va savol namunalari berilgan.",
        "Har bir mavzu uchun “Rasmiy javob” ustuniga qisqa (1–5 gap) toʻgʻri javob yozilsa kifoya: "
        "nima qilish kerak, qayerga borish kerak, qanday hujjat kerak, muddati qachon.",
        "“Masʼul boʻlim” ustuniga savol boʻyicha murojaat qilinadigan boʻlim (xona raqami, ish vaqti, "
        "telefon yoki havola) yoziladi.",
        "Javobi aniq boʻlmagan mavzuni boʻsh qoldirish mumkin: bot bunday savolni masʼul xodimga yoʻnaltiradi.",
        "Shaklni qoʻlda yoki kompyuterda toʻldirish mumkin.",
    ):
        bullet(doc, t)

# ---------- 3. Jadval (albom) ----------
land = doc.sections[0] if ONLY_TABLE else doc.add_section()
land.orientation = WD_ORIENT.LANDSCAPE
land.page_width, land.page_height = Cm(29.7), Cm(21)
land.left_margin = land.right_margin = Cm(1.5)
land.top_margin = land.bottom_margin = Cm(1.5)

heading(doc, "Talabalar savollariga rasmiy javoblar shakli")
para(
    doc,
    "Toʻldirgan xodim: ______________________   Lavozimi: ______________________   "
    "Sana: ___________",
    size=11,
    after=8,
)
if ONLY_TABLE:
    for t in (
        "“Rasmiy javob” ustuniga qisqa (1–5 gap) javob yozing: nima qilish kerak, qayerga borish kerak, "
        "qanday hujjat kerak, muddati qachon.",
        "“Masʼul boʻlim” ustuniga murojaat qilinadigan boʻlim, xona raqami, ish vaqti, telefon yoki havolani yozing.",
        "Javobi aniq boʻlmagan mavzuni boʻsh qoldirish mumkin: bot bunday savolni masʼul xodimga yoʻnaltiradi.",
    ):
        b = bullet(doc, t)
        for r in b.runs:
            r.font.size = Pt(11)
    para(doc, after=4)

widths = [Cm(1.0), Cm(4.3), Cm(7.0), Cm(9.7), Cm(4.7)]
heads = [
    "№",
    "Mavzu",
    "Talabalar savollaridan namunalar",
    "Rasmiy javob",
    "Masʼul boʻlim (xona, telefon, havola)",
]
tbl = doc.add_table(rows=1, cols=5)
tbl.style = "Table Grid"
tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
tbl.autofit = False
hdr = tbl.rows[0]
repeat_header(hdr)
for i, h in enumerate(heads):
    c = hdr.cells[i]
    c.width = widths[i]
    c.text = ""
    r = c.paragraphs[0].add_run(h)
    r.bold = True
    r.font.size = Pt(10.5)
    c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    shade(c, SHADE_HEAD)

n, current = 0, None
for cat, slug, samples, *_ in rows:
    if cat != current:
        current = cat
        row = tbl.add_row()
        no_split(row)
        merged = row.cells[0].merge(row.cells[4])
        merged.text = ""
        rr = merged.paragraphs[0].add_run(cat)
        rr.bold = True
        rr.font.size = Pt(11)
        shade(merged, SHADE_CAT)
    n += 1
    row = tbl.add_row()
    no_split(row)
    row.height = Cm(2.4)
    row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
    vals = [str(n), NAMES[slug], None, "", ""]
    for i, v in enumerate(vals):
        c = row.cells[i]
        c.width = widths[i]
        c.text = ""
        if i == 2:
            parts = [s.strip() for s in samples.split(";") if s.strip()]
            for j, s in enumerate(parts):
                p = c.paragraphs[0] if j == 0 else c.add_paragraph()
                rs = p.add_run(f"– {s}")
                rs.font.size = Pt(10)
                p.paragraph_format.space_after = Pt(1)
        else:
            rs = c.paragraphs[0].add_run(v)
            rs.font.size = Pt(10.5)
            if i == 1:
                rs.bold = True
            if i == 0:
                c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

# ustun kengliklari: grid + har bir katak + fixed layout
tbl_pr = tbl._tbl.tblPr
layout = OxmlElement("w:tblLayout")
layout.set(qn("w:type"), "fixed")
tbl_pr.append(layout)
for i, gc in enumerate(tbl._tbl.tblGrid.findall(qn("w:gridCol"))):
    gc.set(qn("w:w"), str(int(widths[i].twips)))
for row in tbl.rows:
    tcs = row._tr.findall(qn("w:tc"))
    if len(tcs) == 5:
        for i, tc in enumerate(tcs):
            tc.get_or_add_tcPr().get_or_add_tcW().set(qn("w:w"), str(int(widths[i].twips)))
            tc.get_or_add_tcPr().get_or_add_tcW().set(qn("w:type"), "dxa")


def line(doc):
    """Toʻldirish uchun chiziq: oʻng tab + tagiga chizilgan tab belgisi."""
    from docx.enum.text import WD_TAB_ALIGNMENT

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(26.7), WD_TAB_ALIGNMENT.RIGHT)
    r = p.add_run("	")
    r.font.underline = True


para(doc, after=6)
extra = para(
    doc,
    "Qoʻshimcha: talabalar tez-tez beradigan, lekin jadvalda yoʻq savollar boʻlsa, shu yerga yozing:",
    size=11,
    after=4,
)
extra.paragraph_format.keep_with_next = True  # sarlavha chiziqlardan ajralmasin
for i in range(3):
    line(doc)
    if i < 2:
        doc.paragraphs[-1].paragraph_format.keep_with_next = True

OUT.parent.mkdir(parents=True, exist_ok=True)
doc.save(OUT)
print("ok", n)
