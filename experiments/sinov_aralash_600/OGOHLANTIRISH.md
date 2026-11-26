# Aralash maʼlumotdagi sinov natijalari (600 ta savol, 2026-11-26)

| Manba | Soni | Toifani kim belgilagan |
|---|---|---|
| SUNʼIY (Claude) — AI yozgan savollar | 500 | Claude |
| forma — `forma_javoblari.xlsx` (vaqt ustunisiz fayl) | 100 | Claude (muallif tekshirishi kerak) |

- `metrics.json`, `comparison.csv`, `confusion_*.png`: 600 ta savol aralash, 480 train / 120 test.
  SVM 90.8%, Naive Bayes 87.5%, qoidaga asoslangan 65%.
- `forma_tekshiruv.json`: faqat 500 sunʼiy savolda oʻqitib, 100 forma savolida tekshirish.
  SVM 69%, Naive Bayes 70%, qoidaga asoslangan 63%.

Dissertatsiyada ishlatilsa, maʼlumot tarkibi (sunʼiy + forma) va toifalarni kim belgilagani ochiq koʻrsatilishi kerak.
Shu SVM modeli 2026-11-26 dan botda faol (models/svm.joblib).
