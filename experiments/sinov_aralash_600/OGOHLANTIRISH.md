# Aralash maʼlumotdagi sinov natijalari (600 ta savol, 2026-11-26)

| Manba | Soni | Toifani kim belgilagan |
|---|---|---|
| SUNʼIY (Claude) — AI yozgan savollar | 500 | Claude |
| forma — `forma_javoblari.xlsx` (vaqt ustunisiz fayl) | 100 | Claude (muallif tekshirishi kerak) |

- `metrics.json`, `comparison.csv`, `confusion_*.png`: 600 ta savol aralash, 480 train / 120 test.
  SVM 91.7%, Naive Bayes 88.3%, qoidaga asoslangan 65%.
- `forma_tekshiruv.json`: faqat 500 sunʼiy savolda oʻqitib, 100 forma savolida tekshirish.
  SVM 73%, Naive Bayes 73%, qoidaga asoslangan 67%.

Natijalar kengaytirilgan jargon lugʻati (experiments/slang.json, 32 ta soʻz) bilan olingan.
Lugʻat kengaytirilishidan oldingi natijalar: SVM 90.8% (A), 69% (B) — commit 4b10820.

Dissertatsiyada ishlatilsa, maʼlumot tarkibi (sunʼiy + forma) va toifalarni kim belgilagani ochiq koʻrsatilishi kerak.
Shu SVM modeli 2026-11-26 dan botda faol (models/svm.joblib).
