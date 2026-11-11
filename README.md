# TalabaBot

Talabalar murojaatlarini qayta ishlovchi chatbot. Talablar: `docs/TZ (2).md`.

Hozirgi holat: 5-bosqich (modellarni taqqoslash eksperimenti).

## Shu kompyuterda doimiy ishlatish (Windows)

Administrator PowerShell'da bir marta:

```powershell
.\deploy\windows\install.ps1
```

Dastur va bot kompyuter yoqilganda Windows'ga kirmasdan ham ishga tushadi, yiqilsa qayta yonadi. Zaxira har kuni 02:30 da `backups/` ga olinadi. Loglar `logs/` papkasida.

- Kod yangilangandan keyin qayta ishga tushirish: `.\deploy\windows\restart.ps1`
- Holatni ko'rish: `Get-ScheduledTask -TaskPath \TalabaBot\`
- O'chirish (administrator): `.\deploy\windows\uninstall.ps1`

Universitet serveriga ko'chirishda `talababot.db`, `.env` va `models/` ham olib o'tiladi (`.env` dagi kalitlar o'zgarmasligi shart).

## Eksperiment

Excel faylni `data/Murojaatlar_yigish_shabloni.xlsx` ga qo'ying. Varaqda "Murojaat" va "Toifa" ustunlari, imlo xatolari uchun "Imlo xatosi" ustuni bo'lishi kerak.

```powershell
.\.venv\Scripts\python.exe -m experiments.train_baselines
```

Natijalar `experiments/results/` da saqlanadi. Transformer uchun `experiments/colab_transformer.ipynb` ni Google Colab'da oching va ichidagi ko'rsatmaga amal qiling. Natijalarni ilovaga o'tkazish (k1 va SVM modeli, faqat haqiqiy ma'lumotda):

```powershell
.\.venv\Scripts\python.exe -m experiments.train_baselines --register
```

Xodim yaratish (parol so'raladi, rollar: `admin`, `operator`, `ekspert`):

```powershell
.\.venv\Scripts\python.exe -m app.manage create-staff admin admin
```

Telegram botni alohida oynada ishga tushirish (`.env` da `TELEGRAM_BOT_TOKEN` bo'lishi kerak):

```powershell
.\.venv\Scripts\python.exe -m bot.main
```

SVM modelini bilimlar bazasidagi savol namunalarida o'qitish:

```powershell
.\.venv\Scripts\python.exe -m app.nlp.train_svm
```

Keyin admin paneldagi "Sozlamalar" sahifasida modelni tanlang.

## Ishga tushirish (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env   # keyin .env dagi maxfiy qiymatlarni to'ldiring
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload
```

- Veb-chat: http://127.0.0.1:8000/
- Admin panel: http://127.0.0.1:8000/admin
- Operator paneli: http://127.0.0.1:8000/operator
- API hujjati: http://127.0.0.1:8000/docs

## Tekshirish

```powershell
.\.venv\Scripts\pytest.exe --cov=app
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\black.exe --check .
```
