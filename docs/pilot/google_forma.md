# Savollarni yigʻish uchun Google Forms

Maqsad: talabalar universitetga qanday savollar bilan murojaat qilishini **ularning oʻz soʻzlari bilan** yigʻish. Siz savollarga javob bermaysiz, faqat yigʻasiz.

## Formani yaratish (taxminan 5 daqiqa)

1. https://forms.google.com ga Google akkauntingiz bilan kiring va **Boʻsh forma** ni bosing.
2. Quyidagi sarlavha va tavsifni nusxalab qoʻying.
3. Bitta savol qoʻshing, turi **Paragraf** boʻlsin. Savol matni aynan shunday boshlansin: **Savolingiz**, aks holda dastur javoblarni topa olmaydi.
4. **Sozlamalar → Javoblar** boʻlimida **Email yigʻilmasin** deb qoʻying va **1 ta javob bilan cheklash** belgisini olib tashlang. Formaga kirish uchun akkaunt talab qilinmaydi, javoblar anonim boʻladi.
5. **Yuborish** tugmasi orqali havolani oling va eʼlon matni bilan tarqating.

---

**Sarlavha:**

Talabalar savollari soʻrovnomasi

**Tavsif:**

Assalomu alaykum! Talabalar savollariga avtomatik javob beradigan Telegram bot ishlab chiqilmoqda (magistrlik dissertatsiyasi, Buxoro davlat universiteti).

Oʻqish davomida dekanatga, buxgalteriyaga, yotoqxonaga yoki boshqa boʻlimlarga qanday savollar bilan murojaat qilgansiz yoki qilmoqchi boʻlgansiz? Savollaringizni **oʻzingiz odatda qanday yozsangiz, shunday** yozing: lotin yoki kirill harflarida, qisqartmalar bilan ham boʻlaveradi.

Soʻrovnoma anonim: ismingiz va emailingiz yigʻilmaydi. Iltimos, savol ichida ism, telefon raqam va boshqa shaxsiy maʼlumotlarni yozmang. Javoblar faqat ilmiy tadqiqot uchun ishlatiladi.

**Savol (Paragraf):**

Savolingiz (har bir savolni yangi qatordan yozing; 3–5 ta savol yozsangiz juda yaxshi)

---

## Guruhlarga yuboriladigan xabar

Assalomu alaykum! Universitet talabalari uchun Telegram bot tayyorlanmoqda. Unga talabalar odatda qanday savollar berishini bilishimiz kerak. 2 daqiqa vaqt ajratib, oʻzingizni qiziqtirgan yoki ilgari soʻragan savollaringizni yozib bersangiz: [forma havolasi]

Soʻrovnoma anonim. Rahmat!

---

## Javoblar yigʻilgach

1. Formadagi **Javoblar** yorligʻida **Sheets'da koʻrish** tugmasini bosing.
2. Google Sheets'da **Fayl → Yuklab olish → Microsoft Excel (.xlsx)** ni tanlang.
3. Faylni `C:\magistr\talababot\data\forma_javoblari.xlsx` nomi bilan saqlang.
4. `Murojaatlar_yigish_shabloni.xlsx` Excel'da ochiq boʻlsa, uni yoping va PowerShell'da yozing:

```powershell
cd C:\magistr\talababot
.\.venv\Scripts\python.exe -m experiments.collect --from-form data\forma_javoblari.xlsx
```

Savollar “Murojaatlar” varagʻiga qoʻshiladi: takrorlar tashlab ketiladi, telefon va ismlar yashiriladi. Keyin Excel'da har bir savolning **Toifa** va **Imlo xatosi** ustunlarini belgilaysiz.

Botga yozilgan savollarni ham shu tarzda qoʻshish mumkin:

```powershell
.\.venv\Scripts\python.exe -m experiments.collect --from-bot
```
