"""Bot havolasi uchun QR kod: python scripts/make_qr.py"""

from pathlib import Path

import segno

BOT_URL = "https://t.me/buxdu_talababot"
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "pilot"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # H darajasi: qogʻoz yirtilsa yoki xiralashsa ham oʻqiladi.
    code = segno.make(BOT_URL, error="h", micro=False)
    code.save(OUT_DIR / "qr_buxdu_talababot.png", scale=20, border=4)
    code.save(OUT_DIR / "qr_buxdu_talababot.svg", scale=10, border=4)
    print(f"QR kod saqlandi: {OUT_DIR}")


if __name__ == "__main__":
    main()
