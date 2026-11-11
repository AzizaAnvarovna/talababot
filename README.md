# TalabaBot

Talabalar murojaatlarini qayta ishlovchi chatbot. Talablar: `docs/TZ (2).md`.

Hozirgi holat: 2-bosqich (NLP yadro). Telegram bot keyingi bosqichda qo'shiladi.

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
- Admin panel: http://127.0.0.1:8000/admin (parol `.env` dagi `ADMIN_PASSWORD`)
- API hujjati: http://127.0.0.1:8000/docs

## Tekshirish

```powershell
.\.venv\Scripts\pytest.exe --cov=app
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\black.exe --check .
```
