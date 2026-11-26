"""TZ 10-boʻlim qabul mezonlarini tekshiradi va Word hisobot yozadi.

    python -m scripts.qabul_tekshiruvi --out docs/Qabul_mezonlari_tekshiruvi.docx

Pilot maʼlumotini buzmaslik uchun hamma tekshiruv bazaning vaqtinchalik NUSXASIDA,
test rejimida (TEST_MODE=true) oʻtkaziladi: haqiqiy bilimlar bazasi, jargon lugʻati va
model ishlatiladi, lekin asl talababot.db ga hech narsa yozilmaydi.
"""

import argparse
import dataclasses
import json
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE_DB = ROOT / "talababot.db"
TEMPLATE = ROOT / "data" / "Murojaatlar_yigish_shabloni.xlsx"

LAT_CYR = [
    ("Stipendiya qachon tushadi?", "Стипендия қачон тушади?"),
    ("Yotoqxonaga qanday joylashaman?", "Ётоқхонага қандай жойлашаман?"),
    ("Akademik taʼtil qanday olinadi?", "Академик таътил қандай олинади?"),
    ("Maʼlumotnomani qayerdan olaman?", "Маълумотномани қаердан оламан?"),
    ("Dars jadvali qayerda chiqadi?", "Дарс жадвали қаерда чиқади?"),
    ("Kontrakt toʻlovi qachongacha?", "Контракт тўлови қачонгача?"),
    ("Kutubxona soat nechagacha ishlaydi?", "Кутубхона соат нечагача ишлайди?"),
    ("Boshqa universitetga koʻchirish mumkinmi?", "Бошқа университетга кўчириш мумкинми?"),
    ("Talabalik guvohnomasini yoʻqotdim", "Талабалик гувоҳномасини йўқотдим"),
    ("Qarzdor fanni qayta topshirish", "Қарздор фанни қайта топшириш"),
]
PII_TEXT = (
    "Assalomu alaykum, men Alisher Karimov, telefonim +998 90 123 45 67, "
    "email alisher.karimov@mail.ru, stipendiyam tushmadi"
)
PII_PARTS = ("Karimov", "+998", "123 45 67", "alisher.karimov@mail.ru")
LOG_PII = re.compile(r"\+998|\b\d{2} \d{3} \d{2} \d{2}\b|[\w.]+@[\w-]+\.(?:ru|uz|com)")


def copy_database(target: Path) -> None:
    """sqlite backup API: WAL rejimidagi ochiq bazadan ham toʻliq nusxa oladi."""
    source = sqlite3.connect(LIVE_DB)
    copy = sqlite3.connect(target)
    source.backup(copy)
    copy.close()
    source.close()


def run_checks(work: Path) -> dict:
    # app modullari muhit oʻzgaruvchilari oʻrnatilgandan keyin import qilinadi.
    from app.db.models import Dialog, Message
    from app.db.session import SessionLocal
    from app.dialog import handle_message
    from app.metrics.indicators import Filters, compute, load_stats
    from app.metrics.report import build_report
    from app.nlp.classifier import get_classifier
    from app.nlp.masking import mask_pii
    from app.nlp.normalizer import normalize
    from app.settings_store import load_settings, load_slang, save_settings

    results: dict = {}
    with SessionLocal() as db:
        settings = load_settings(db)
        save_settings(db, dataclasses.replace(settings, ab_enabled=False, active_model="svm"))
        db.commit()
        slang = load_slang(db)

        def say(channel, uid, text=None, action=None):
            return handle_message(db, channel, uid, text, action)

        # 1 va 5. Toʻliq ish sikli, baholash
        steps = []
        reply = say("telegram", "q1", "salom")
        steps.append(["Birinchi xabar", reply.response_type, "rozilik soʻraldi"])
        say("telegram", "q1", action="consent_yes")
        reply = say("telegram", "q1", "Akademik taʼtil qanday olinadi?")
        dialog_id = reply.dialog_id
        steps.append(["Savol: “Akademik taʼtil qanday olinadi?”", reply.response_type, reply.text])
        reply = say("telegram", "q1", action="end")
        steps.append(["Suhbatni yakunlash", reply.response_type, reply.text])
        reply = say("telegram", "q1", action=f"resolved:{dialog_id}:yes")
        steps.append(["“Hal boʻldi: ha”", reply.response_type, reply.text])
        say("telegram", "q1", action=f"rate:{dialog_id}:5")
        dialog = db.get(Dialog, dialog_id)
        logged = db.query(Message).filter(Message.dialog_id == dialog_id).count()
        report = build_report(db, Filters(include_test=True))
        results["cycle"] = {
            "steps": steps,
            "stored": {
                "ended": dialog.ended_at is not None,
                "resolved": dialog.resolved,
                "csat": dialog.csat,
                "messages": logged,
            },
            "panel_n": report.counts[0]["values"][0],
        }

        # 2. Telegram va veb
        pairs = []
        for index, question in enumerate(
            ("Yotoqxonaga qanday joylashaman?", "HEMIS parolim esdan chiqdi", "Kontrakt toʻlovi")
        ):
            texts = []
            for channel in ("telegram", "web"):
                uid = f"q2-{channel}-{index}"
                say(channel, uid, action="consent_yes")
                texts.append(say(channel, uid, question).text)
                say(channel, uid, action="end")
            pairs.append([question, texts[0] == texts[1]])
        report = build_report(db, Filters(include_test=True))
        results["channels"] = {
            "pairs": pairs,
            "by_channel": dict(zip(report.columns, report.counts[0]["values"], strict=True)),
        }

        # 3. Kirill va lotin
        scripts = []
        for name in ("rule-based", "svm"):
            classifier = get_classifier(name)
            for latin, cyrillic in LAT_CYR:
                a = classifier.predict(normalize(mask_pii(latin), slang))[0][0]
                b = classifier.predict(normalize(mask_pii(cyrillic), slang))[0][0]
                scripts.append([name, latin, cyrillic, a, b])
        results["scripts"] = scripts

        # 4. Aniqlashtirish va operator
        flows = {}
        for label, texts in (
            ("Ikki marta tushunarsiz xabar", ["qwerty asdf zxcv", "lorem ipsum dolor"]),
            ("Talaba “operator” deydi", ["operator kerak"]),
        ):
            uid = f"q4-{label}"
            say("web", uid, action="consent_yes")
            flows[label] = [[text, say("web", uid, text).response_type] for text in texts]
        results["handoff"] = flows

        # 6. Panel = qoʻlda hisob
        db_path = os.environ["DATABASE_URL"].removeprefix("sqlite:///")
        con = sqlite3.connect(db_path)
        base = (
            "from dialogs d join users u on u.id = d.user_id "
            "where d.ended_at is not null and u.consent = 1"
        )
        n = con.execute(f"select count(*) {base}").fetchone()[0]
        fallback = con.execute(
            f"select count(*) {base} and exists (select 1 from messages m "
            "where m.dialog_id = d.id and m.response_type = 'fallback')"
        ).fetchone()[0]
        handed = con.execute(f"select count(*) {base} and d.handed_off = 1").fetchone()[0]
        yes, no = con.execute(f"select sum(d.resolved = 1), sum(d.resolved = 0) {base}").fetchone()
        csat = [row[0] for row in con.execute(f"select d.csat {base} and d.csat is not null")]
        con.close()
        by_hand = {
            "k3": 1 - fallback / n,
            "k4": (yes or 0) / ((yes or 0) + (no or 0)),
            "k5": 1 - handed / n,
            "k8": (sum(csat) / len(csat) - 1) / 4,
        }
        panel = compute(load_stats(db, Filters(include_test=True)), None)
        results["panel"] = {
            "n": n,
            "rows": [[code, by_hand[code], panel[code]] for code in by_hand],
        }

        # 8. Shaxsiy maʼlumot
        say("web", "q8", action="consent_yes")
        reply = say("web", "q8", PII_TEXT)
        stored = (
            db.query(Message)
            .filter(Message.dialog_id == reply.dialog_id, Message.sender == "talaba")
            .first()
            .text_masked
        )
    log_hits = {
        path.name: len(LOG_PII.findall(path.read_text(encoding="utf-8", errors="ignore")))
        for path in sorted((ROOT / "logs").glob("*.log"))
    }
    results["pii"] = {
        "stored": stored,
        "leaks": [part for part in PII_PARTS if part in stored],
        "log_hits": log_hits,
    }

    # 7. Eksperimentni qayta ishga tushirish
    from experiments.train_baselines import run

    runs = []
    for index in (1, 2):
        out = work / f"run{index}"
        run(TEMPLATE, out, export_transformer=False)
        runs.append((out / "metrics.json").read_text(encoding="utf-8"))
    metrics = json.loads(runs[0])
    results["repro"] = {
        "same": runs[0] == runs[1],
        "samples": metrics["dataset"]["samples"],
        "svm_accuracy": metrics["models"]["svm"]["holdout"]["accuracy"],
    }
    return results


def verdicts(r: dict) -> list[tuple[str, bool, str, str]]:
    cycle = r["cycle"]
    stored = cycle["stored"]
    types = [step[1] for step in cycle["steps"]]
    same_script = [row for row in r["scripts"] if row[3] == row[4]]
    flows = list(r["handoff"].values())
    rows = r["panel"]["rows"]
    pii = r["pii"]
    resolved = "ha" if stored["resolved"] else "yoʻq"
    return [
        (
            "Telegram bot orqali toʻliq ish sikli: savol → javob / aniqlashtirish / operator → "
            "baholash → log → tahlil paneli",
            types[1] == "kb" and stored["ended"] and stored["csat"] == 5 and cycle["panel_n"] > 0,
            "Telegram kanalida yangi foydalanuvchi: rozilik → savol → “Yakunlash” → "
            "“Hal boʻldimi?” → 1–5 baho. Soʻng dialog bazada va tahlil panelida tekshirildi.",
            f"Javob turi: {types[1]}; bazada: yakunlangan, hal boʻldi = {resolved}, "
            f"baho = {stored['csat']}, {stored['messages']} ta xabar logda; "
            f"tahlil panelida N = {cycle['panel_n']}.",
        ),
        (
            "Telegram va veb-chat bir xil savolga bir xil javob beradi; "
            "dialoglar panelda kanal boʻyicha alohida",
            all(same for _, same in r["channels"]["pairs"])
            and min(r["channels"]["by_channel"].values()) > 0,
            "3 ta savol ikki kanaldan alohida foydalanuvchilar nomidan yuborildi, "
            "javob matnlari solishtirildi.",
            f"{sum(s for _, s in r['channels']['pairs'])}/3 savolda javob soʻzma-soʻz bir xil; "
            + ", ".join(f"{k}: {v}" for k, v in r["channels"]["by_channel"].items())
            + ".",
        ),
        (
            "Kirill va lotin yozuvidagi bir xil savol bir xil toifaga tasniflanadi",
            len(same_script) == len(r["scripts"]),
            f"{len(LAT_CYR)} juft savol (lotin va kirill) ikkala model (rule-based, SVM) "
            "bilan tasniflandi.",
            f"{len(same_script)}/{len(r['scripts'])} holatda toifa bir xil.",
        ),
        (
            "Ishonch past boʻlganda aniqlashtiruvchi savol, ikki marta tushunilmaganda "
            "operatorga uzatish",
            [t for _, t in flows[0]] == ["clarify", "fallback"] and flows[1][0][1] == "operator",
            "Ketma-ket ikkita tushunarsiz xabar; alohida dialogda “operator kerak” xabari.",
            "Javob turlari: "
            + " → ".join(t for _, t in flows[0])
            + " (fallback — “tushuna olmadim, operatorga uzatildi”, FR-12); "
            + f"“operator kerak” → {flows[1][0][1]}.",
        ),
        (
            "Har bir dialog oxirida baholash soʻraladi va natija bazaga yoziladi",
            stored["resolved"] is True and stored["csat"] == 5,
            "1-banddagi dialog yakunida “Hal boʻldimi?” va 1–5 baho tugmalari bosildi.",
            f"Bazada: hal boʻldi = {resolved}, baho = {stored['csat']}.",
        ),
        (
            "Tahlil paneli k1–k8, Q va kS ni loglardan hisoblaydi; qoʻlda tekshirilgan hisob "
            "bilan mos",
            all(abs(a - b) < 1e-9 for _, a, b in rows),
            f"Bazadagi {r['panel']['n']} ta dialog boʻyicha k3, k4, k5, k8 toʻgʻridan-toʻgʻri "
            "SQL soʻrovlar bilan qoʻlda hisoblandi va panel funksiyasi bilan solishtirildi.",
            "; ".join(f"{c}: {a:.4f} = {b:.4f}" for c, a, b in rows) + ".",
        ),
        (
            "Eksperiment skripti bitta buyruq bilan qayta ishga tushiriladi "
            "va bir xil natija beradi",
            r["repro"]["same"],
            "experiments.train_baselines ikki marta ishga tushirildi, metrics.json fayllari "
            "solishtirildi.",
            f"Natija fayllari {'bir xil' if r['repro']['same'] else 'FARQ QILADI'} "
            f"({r['repro']['samples']} ta murojaat, SVM aniqligi "
            f"{r['repro']['svm_accuracy']:.3f}).",
        ),
        (
            "Logda ism, telefon va email ochiq holda saqlanmaydi",
            not pii["leaks"] and not any(pii["log_hits"].values()),
            "Ism, telefon va email bor xabar yuborildi; bazadagi yozuv va logs/ papkasidagi "
            "fayllar tekshirildi.",
            f"Bazada: “{pii['stored']}”. Log fayllarida topilgan telefon/email: "
            + ", ".join(f"{k} — {v}" for k, v in pii["log_hits"].items())
            + ".",
        ),
    ]


def write_docx(rows: list[tuple[str, bool, str, str]], out: Path, created: datetime) -> None:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(11)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    for name in ("Title", "Heading 1"):
        doc.styles[name].font.name = "Times New Roman"
        doc.styles[name].font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Cm(29.7), Cm(21)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Cm(1.5))

    doc.add_heading("TalabaBot: qabul mezonlarini tekshirish natijalari", 0)
    passed = sum(ok for _, ok, _, _ in rows)
    doc.add_paragraph(
        f"Sana: {created:%Y-%m-%d %H:%M}. Asos: texnik topshiriq, 10-boʻlim. "
        f"Natija: {passed}/{len(rows)} mezon bajarildi."
    )
    doc.add_paragraph(
        "Usul: tekshiruv ishlab turgan tizim bazasining nusxasida, test rejimida oʻtkazildi "
        "(haqiqiy bilimlar bazasi, jargon lugʻati va SVM modeli bilan). Pilot maʼlumotiga "
        "hech narsa yozilmagan. Tekshiruvni qayta oʻtkazish: "
        "python -m scripts.qabul_tekshiruvi --out <fayl>.docx"
    )

    widths = [Cm(0.8), Cm(6.5), Cm(2.2), Cm(8.2), Cm(9.0)]
    table = doc.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    table._tbl.tblPr.append(layout)
    for i, grid_col in enumerate(table._tbl.tblGrid.findall(qn("w:gridCol"))):
        grid_col.set(qn("w:w"), str(int(widths[i].twips)))
    for i, title in enumerate(("№", "Mezon", "Natija", "Qanday tekshirildi", "Olingan natija")):
        cell = table.rows[0].cells[i]
        cell.text = ""
        cell.paragraphs[0].add_run(title).bold = True
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), "D9E2F3")
        cell._tc.get_or_add_tcPr().append(shd)
    for number, (criterion, ok, method, outcome) in enumerate(rows, start=1):
        cells = table.add_row().cells
        values = (str(number), criterion, "Bajarildi" if ok else "BAJARILMADI", method, outcome)
        for i, value in enumerate(values):
            cells[i].text = ""
            run = cells[i].paragraphs[0].add_run(value)
            if i == 2:
                run.bold = True
                run.font.color.rgb = RGBColor.from_string("1E7B34" if ok else "C00000")
    for row in table.rows:
        for i, width in enumerate(widths):
            row.cells[i].width = width
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        copy_database(work / "nusxa.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{(work / 'nusxa.db').as_posix()}"
        os.environ["TEST_MODE"] = "true"
        results = run_checks(work)
        from app.db.session import engine

        engine.dispose()  # Windows'da vaqtinchalik papka oʻchirilishi uchun

    rows = verdicts(results)
    write_docx(rows, args.out, datetime.now())
    for number, (criterion, ok, _, outcome) in enumerate(rows, start=1):
        print(f"{number}. {'OK ' if ok else 'XATO'} {criterion[:60]}… — {outcome}")
    print(f"Hisobot: {args.out}")


if __name__ == "__main__":
    main()
