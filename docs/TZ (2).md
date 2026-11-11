**“TASDIQLAYMAN”**

Ilmiy rahbar: \_\_\_\_\_\_\_\_\_\_\_\_ prof. Eshankulov H.I.

“\_\_\_” \_\_\_\_\_\_\_\_\_\_\_\_ 2026-yil

**TEXNIK TOPSHIRIQ**

**TALABA MUROJAATLARINI QAYTA ISHLOVCHI INTELLEKTUAL CHATBOT TIZIMI**

Texnik topshiriq: talabalar uchun Telegram bot, operator, ekspert va
tadqiqotchi uchun veb-panel, yagona NLP yadro

| **Loyiha nomi**  | TalabaBot — sunʼiy intellekt asosidagi talabalar murojaatlarini qayta ishlovchi chatbot |
|------------------|-----------------------------------------------------------------------------------------|
| **Muallif**      | Arslonova Aziza Anvar qizi, 70610401 – Dasturiy injiniring mutaxassisligi magistranti   |
| **Ilmiy rahbar** | professor Eshankulov H.I.                                                               |
| **Tashkilot**    | Buxoro davlat universiteti                                                              |
| **Versiya**      | 1.0, 2026-yil noyabr                                                                    |

**Buxoro – 2026**

# 1. Umumiy maʼlumot

## 1.1. Loyihaning maqsadi

Oliy taʼlim muassasasida talabalarning oʻzbek tilidagi murojaatlarini
avtomatik qabul qiluvchi, tasniflovchi, bilimlar bazasi asosida maslahat
beruvchi, kerak boʻlganda operatorga uzatuvchi hamda muloqot sifatini
integral koʻrsatkich asosida oʻlchovchi chatbot tizimini yaratish.

## 1.2. Loyihaning dissertatsiyadagi oʻrni

Tizim magistrlik dissertatsiyasining amaliy qismi hisoblanadi. Uning har
bir moduli dissertatsiyaning muayyan paragrafi uchun maʼlumot va natija
beradi:

| **Modul**                              | **Natija**                            | **Dissertatsiyada** |
|----------------------------------------|---------------------------------------|---------------------|
| Normallashtirish va tasniflash         | Formal model, algoritm                | 2.1, 2.2            |
| Maslahat va operatorga uzatish         | Ishonch chegarasi strategiyasi        | 2.3                 |
| Veb-chat, Telegram, maʼlumotlar bazasi | Arxitektura, dastur                   | 3.1, 3.2            |
| Eksperiment moduli                     | Modellarni taqqoslash jadvallari      | 3.3                 |
| Tahlil paneli                          | Integral indeks Q, kS, A/B natijalari | 3.3, ilmiy yangilik |

## 1.3. Asosiy tamoyillar

- Haqiqiy natija — tizimdagi barcha koʻrsatkichlar faqat haqiqiy
  foydalanuvchilar loglaridan hisoblanadi; test maʼlumotlari alohida
  belgilanadi (dialogs.is_test) va hisobotga kirmaydi.

- Takrorlanuvchanlik — har bir tajriba belgilangan tasodifiy son (seed),
  saqlangan maʼlumotlar boʻlinmasi va model versiyasi bilan qayta
  bajarilishi mumkin.

- Bitta “miya”, bir necha kanal — talabalar asosan Telegram bot orqali,
  sinov va namoyish uchun esa veb-chat orqali murojaat qiladi. Ikkala
  kanal kanaldan mustaqil yagona Dialog API va bitta NLP yadrodan
  foydalanadi; boshqaruv, baholash va tahlil veb-panelda amalga
  oshiriladi.

- Shaxsiy maʼlumotlar himoyasi — talaba identifikatori xeshlanadi,
  telefon, email kabi maʼlumotlar logda maskalanadi.

# 2. Foydalanuvchilar va rollar

| **Rol**       | **Kim**                                         | **Imkoniyatlari**                                                                                               |
|---------------|-------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| Talaba        | Har qanday foydalanuvchi (roʻyxatdan oʻtmasdan) | Asosan Telegram bot orqali (zaxira kanal — veb-chat) savol berish, javobni baholash, operatorni chaqirish       |
| Operator      | Dekanat yoki boʻlim xodimi                      | Veb-panelda uzatilgan murojaatlar navbatini koʻrish va javob yozish; javob talabaga Telegram orqali yetkaziladi |
| Ekspert       | Oʻqituvchi, xodim, talaba vakili                | Tasodifiy dialoglarga 1–5 ball qoʻyish (k2), AHP juft taqqoslash soʻrovnomasini toʻldirish                      |
| Administrator | Tadqiqotchi (muallif)                           | Bilimlar bazasini boshqarish, modellarni almashtirish, tahlil paneli, eksport                                   |

# 3. Tizim arxitekturasi

Tizim “kanaldan mustaqil yadro” tamoyili asosida qurilgan: foydalanuvchi
kanallari, NLP yadro, maʼlumotlar qatlami va veb-panel bir-biridan
ajratilgan. Bu yondashuv yangi kanal (masalan, universitet sayti yoki
mobil ilova) qoʻshilganda yadroni oʻzgartirmaslik imkonini beradi.

```
[Kanallar: Telegram bot (asosiy), Veb-chat] → Dialog API (POST /api/chat/message)
 → NLP yadro: Normallashtirish → Tasniflash (+ishonch) → ishonch ≥ τ ? KB javobi : aniqlashtirish/operator → Hissiy tahlil va log
 → Maʼlumotlar bazasi → Veb-panel (Operator · Ekspert · Tadqiqotchi: k1–k8, Q, kS, A/B)
```

1-rasm. TalabaBot tizimining umumiy arxitekturasi

| **Qatlam**  | **Tarkibi**                                                            | **Vazifasi**                                                                  |
|-------------|------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| Kanallar    | Telegram bot (asosiy), veb-chat (zaxira va namoyish)                   | Talaba xabarini qabul qilish va javobni koʻrsatish                            |
| Dialog API  | POST /api/chat/message                                                 | Barcha kanallar uchun yagona kirish nuqtasi, sessiya va kontekstni boshqarish |
| NLP yadro   | Normallashtirish, tasniflash, strategiya, javob tanlash, hissiy tahlil | Murojaatni tushunish va maslahat shakllantirish                               |
| Maʼlumotlar | SQLite (pilot), SQLAlchemy                                             | Dialoglar, xabarlar, baholar, bilimlar bazasi, model versiyalari              |
| Veb-panel   | Operator, ekspert va administrator sahifalari                          | Uzatilgan murojaatlarga javob, baholash, tahlil va eksport                    |

Telegram bot alohida jarayon sifatida ishlaydi va har bir xabarni Dialog
API ga yuboradi. Shu sababli Telegram va veb-chat bir xil mantiq, bir
xil log va bir xil koʻrsatkichlardan foydalanadi, ular boʻyicha
natijalarni esa alohida-alohida solishtirish mumkin.

# 4. Funksional talablar

## 4.1. Kanallar

| **FR-1** | Telegram bot (asosiy kanal): /start (salomlashish va rozilik), /help, /operator, /end buyruqlari; javob ostida tez tugmalar (inline keyboard): aniqlashtirish variantlari, “Operator”, “Yakunlash”, baholash tugmalari. |
|----------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **FR-2** | Veb-chat sahifasi (zaxira va namoyish kanali): savol yozish maydoni, xabarlar tarixi, “Operator bilan bogʻlanish” va “Suhbatni yakunlash” tugmalari; mobil telefonda toʻgʻri koʻrinadi.                                 |
| **FR-3** | Dialog API kanaldan mustaqil: soʻrovda kanal nomi (telegram/web) va foydalanuvchi identifikatori keladi, javobda matn va tugmalar roʻyxati qaytadi. Har bir kanal bu javobni oʻz interfeysida koʻrsatadi.               |
| **FR-4** | Birinchi muloqotda talabaga xabar beriladi: “Suhbatlar ilmiy tadqiqot maqsadida anonim saqlanadi”. Rozilik bermagan talaba uchun loglar tahlilga kiritilmaydi.                                                          |

## 4.2. Matnni normallashtirish

| **FR-5** | Kirill yozuvidagi matn lotin yozuviga oʻgiriladi (transliteratsiya jadvali: ш→sh, ч→ch, ў→oʻ, ғ→gʻ, қ→q, ҳ→h va boshqalar).                                           |
|----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **FR-6** | Apostrof variantlari (o', o\`, oʻ, o’) yagona belgiga keltiriladi; matn kichik harfga oʻtkaziladi; ortiqcha boʻshliq va takroriy harflar (“rahmaaat”) qisqartiriladi. |
| **FR-7** | Qisqartmalar va jargon lugʻati: “stipuxa” → “stipendiya”, “dekanat” variantlari va h.k. Lugʻat administrator tomonidan toʻldiriladi.                                  |
| **FR-8** | Asl va normallashgan matn ikkalasi ham logga yoziladi.                                                                                                                |

## 4.3. Tasniflash va maslahat strategiyasi

| **FR-9**  | Murojaat 6 toifadan biriga tasniflanadi: Oʻquv jarayoni, Stipendiya, Yotoqxona, Hujjatlar va arizalar, Akademik taʼtil va koʻchirish, Boshqa. Model har bir toifa uchun ehtimollik (ishonch) qaytaradi. |
|-----------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **FR-10** | Ishonch ≥ τ (sukut boʻyicha τ = 0,60, admin oʻzgartira oladi) boʻlsa — toifa ichidagi bilimlar bazasi yozuvlaridan savolga eng oʻxshash yozuv (TF-IDF kosinus oʻxshashligi) tanlanib, javob beriladi.   |
| **FR-11** | Ishonch \< τ boʻlsa — aniqlashtiruvchi savol beriladi: eng ehtimolli 2 ta toifa tugma sifatida koʻrsatiladi (“Stipendiya haqidami yoki hujjatlar haqidami?”).                                           |
| **FR-12** | Ketma-ket 2 marta tushunilmasa yoki talaba “operator” desa — murojaat operatorga uzatiladi va talabaga bu haqda xabar beriladi. “Tushunilmadi” hodisasi: ishonch \< τ yoki bilimlar bazasidagi eng yaxshi oʻxshashlik \< σ (sukut boʻyicha σ = 0,30, admin oʻzgartira oladi). Birinchi hodisada javob turi clarify, ketma-ket ikkinchisida fallback boʻladi va murojaat uzatiladi; talabaning oʻzi soʻrasa javob turi operator boʻladi.                                                                         |
| **FR-13** | Dialog konteksti: oxirgi aniqlangan toifa 10 daqiqa saqlanadi; qisqa davomiy savollar (“ijtimoiysi-chi?”) shu kontekstda talqin qilinadi.                                                               |
| **FR-14** | Faol model versiyasi sozlamada tanlanadi: rule-based, SVM yoki transformer. A/B rejimida har bir yangi dialogga versiya tasodifiy (50/50) tayinlanadi va dialog oxirigacha oʻzgarmaydi.                 |

## 4.4. Bilimlar bazasi

| **FR-15** | Yozuv tarkibi: toifa, kichik mavzu (intent), savol namunalari, rasmiy javob, havola yoki hujjat, masʼul boʻlim, “tekshirildi” belgisi.      |
|-----------|---------------------------------------------------------------------------------------------------------------------------------------------|
| **FR-16** | Admin panelda yozuvlarni qoʻshish, tahrirlash, oʻchirish; “Murojaatlar_yigish_shabloni.xlsx” faylidagi “Bilimlar bazasi” varagʻidan import. 1-bosqichda admin panel .env dagi yagona parol bilan himoyalanadi; 3-bosqichda staff jadvali va xeshlangan parollarga oʻtkaziladi. |
| **FR-17** | Faqat “tekshirildi = Ha” boʻlgan javoblar talabaga koʻrsatiladi. Javob ostida manba (boʻlim yoki havola) koʻrsatiladi.                      |

## 4.5. Dialogni yakunlash va baholash

| **FR-18** | Dialog tugaydi: talaba “Yakunlash” tugmasini bossa, “rahmat” kabi yakunlovchi xabar yozsa yoki 10 daqiqa faolsiz boʻlsa.                           |
|-----------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| **FR-19** | Yakunda ikki savol beriladi: “Muammoingiz hal boʻldimi?” (Ha / Yoʻq) va “Xizmatni 1 dan 5 gacha baholang”. Javob berish ixtiyoriy.                 |
| **FR-20** | Har bir talaba xabari uchun hissiy baho s ∈ \[–1; 1\] aniqlanadi (pilotda lugʻat va qoidalarga asoslangan, keyin model asosida) va logga yoziladi. |

## 4.6. Operator paneli

| **FR-21** | Operator login va parol bilan kiradi va uzatilgan murojaatlar navbatini (vaqt, toifa, dialog tarixi) koʻradi.                      |
|-----------|------------------------------------------------------------------------------------------------------------------------------------|
| **FR-22** | Operator javobi talabaga oʻsha kanal orqali (veb yoki Telegram) yetkaziladi; dialog “operator orqali hal qilindi” deb belgilanadi. Yetkazish uchun Telegram chat_id shifrlangan holda users.delivery_ref maydonida saqlanadi (kalit .env da; eksport va tahlilga kirmaydi). Operator javobi messages jadvaliga delivered_at = null bilan yoziladi: Telegram bot ichki API dan yetkazilmagan javoblarni har 2 s da soʻrab oladi, yuborgach tasdiqlaydi; veb-chat ham yangi javoblarni shu tarzda soʻrab turadi. |

## 4.7. Log yozuvlari

| **FR-23** | Har bir xabar uchun saqlanadi: vaqt, kanal, dialog ID, xeshlangan foydalanuvchi ID, asl matn (maskalangan), normallashgan matn, aniqlangan toifa, ishonch, javob turi (kb / clarify / fallback / operator), javob vaqti (ms), model versiyasi, hissiy baho. |
|-----------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **FR-24** | Telefon raqam, email va 6+ xonali raqamlar logga yozishdan oldin \[TEL\], \[EMAIL\], \[ID\] bilan almashtiriladi. Ismlar \[ISM\] bilan almashtiriladi: oʻzbek ismlari lugʻati, “-ov/-ova/-yev/-yeva” familiya qoʻshimchalari va “ismim …”, “men … man” qoliplari asosida.                                                                                                                                           |

## 4.8. Tahlil paneli va integral indeks

Panel tanlangan davr va model versiyasi boʻyicha quyidagi
koʻrsatkichlarni hisoblaydi (formulalar dissertatsiyaning 3.3-paragrafi
va “Integral model” maqolasiga mos):

| **Koʻrsatkich**             | **Formula**                                            | **Manba**          |
|-----------------------------|--------------------------------------------------------|--------------------|
| k1 — Intent aniqlash sifati | Test toʻplamidagi makro-F1                             | Eksperiment moduli |
| k2 — Javob mosligi          | (ekspertlar oʻrtacha bali − 1) / 4                     | Ekspert baholari   |
| k3 — Tushunish darajasi     | 1 − Nf / N (Nf — fallback boʻlgan dialoglar)           | Log                |
| k4 — Vazifa bajarilishi     | Nh / N (“hal boʻldi” javobi berilgan dialoglar ichida) | Log, talaba javobi |
| k5 — Mustaqillik            | 1 − No / N (No — operatorga uzatilganlar)              | Log                |
| k6 — Dialog tejamkorligi    | min(1, n0 / n̄), n0 = 2 navbat                          | Log                |
| k7 — Tezkorlik              | max(0, 1 − t̄ / tmax), tmax = 5 s                       | Log                |
| k8 — Qoniqish (CSAT)        | (oʻrtacha baho − 1) / 4                                | Talaba bahosi      |
| Q — Integral indeks         | Q = Σ wi·ki, Σ wi = 1                                  | AHP vaznlari       |
| kS — Hissiy koʻrsatkich     | 1 − Nneg / N                                           | Log (hissiy baho)  |

| **FR-25** | AHP moduli: ekspertlar juft taqqoslash matritsalarini (1–9 shkala) kiritadi; vaznlar geometrik oʻrtacha usulida, izchillik CR bilan hisoblanadi; CR ≥ 0,10 boʻlsa ogohlantirish chiqadi.            |
|-----------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **FR-26** | Qisman indekslar QD1, QD2, QD3 va Q qiymati shkala boʻyicha talqini (aʼlo / yaxshi / qoniqarli / past) koʻrsatiladi.                                                                                |
| **FR-27** | A/B taqqoslash: ikki versiya uchun k1–k8, Q va kS yonma-yon jadvalda; farqning statistik ahamiyati (k4 uchun χ² mezoni, CSAT uchun Mann–Whitney mezoni).                                            |
| **FR-28** | Ekspert baholash sahifasi: tizim tasodifiy 50 ta dialogni tanlaydi, ekspert har biriga 1–5 ball qoʻyadi (k2).                                                                                       |
| **FR-29** | Grafiklar: kunlik dialoglar soni, toifalar taqsimoti, Q dinamikasi; barcha koʻrsatkichlarni kanal boʻyicha (Telegram va veb) alohida koʻrsatish; jadvallarni CSV va Excel formatida eksport qilish. |

## 4.8.1. Koʻrsatkichlar taʼriflari (taklif — ilmiy rahbar bilan tasdiqlanadi)

Quyidagi taʼriflar “Integral model” maqolasi bilan solishtirilishi kerak; farq boʻlsa, maqoladagi qiymat ustun turadi.

| **Tushuncha**      | **Taʼrif**                                                                                                                                                                 |
|--------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| N                  | Tanlangan davrda tugagan, consent = rost va is_test = yolgʻon boʻlgan dialoglar soni. k4 va k8 da N — tegishli savolga javob berilgan dialoglar soni.                       |
| Nf (k3)            | Kamida bitta fallback javobi boʻlgan dialoglar soni (FR-12). Birinchi clarify va talabaning oʻzi operatorni chaqirishi fallback hisoblanmaydi.                              |
| n̄ (k6)             | Bitta dialogdagi talaba xabarlarining oʻrtacha soni (1 navbat = talaba xabari va bot javobi).                                                                              |
| t̄ (k7)             | Bot javoblari latency_ms qiymatining oʻrtachasi, sekundda.                                                                                                                 |
| QD1 — Tushunish    | k1, k2, k3.                                                                                                                                                                |
| QD2 — Samaradorlik | k4, k5, k6.                                                                                                                                                                |
| QD3 — Tajriba      | k7, k8.                                                                                                                                                                    |
| Qisman indeks      | QDj = Σ vi·ki, bunda vi — j-oʻlcham ichidagi AHP vaznlari, Σ vi = 1. Q = Σ Wj·QDj, bunda Wj — oʻlchamlar vaznlari; demak har bir koʻrsatkich uchun wi = Wj·vi.              |
| AHP darajalari     | ahp_judgments.level = 0: oʻlchamlar matritsasi (3×3); level = 1, 2, 3: QD1 (3×3), QD2 (3×3), QD3 (2×2) ichidagi matritsalar.                                               |
| Q talqini          | 0,85 ≤ Q — aʼlo; 0,70 ≤ Q \< 0,85 — yaxshi; 0,50 ≤ Q \< 0,70 — qoniqarli; Q \< 0,50 — past. Shkala QD1, QD2, QD3 uchun ham qoʻllanadi.                                      |
| Nneg (kS)          | Talaba xabarlari oʻrtacha hissiy bahosi s̄ \< −0,25 boʻlgan dialoglar soni.                                                                                                 |

## 4.9. Eksperiment moduli (oflayn)

| **FR-30** | Maʼlumotlar toʻplami shablon Excel faylidan yuklanadi; takrorlar olib tashlanadi; toifalar boʻyicha stratifikatsiyalangan 80/20 boʻlinma (seed = 42) saqlanadi; qoʻshimcha ravishda 5 karrali kross-validatsiya.                    |
|-----------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **FR-31** | Taqqoslanadigan modellar: (1) kalit soʻzlarga asoslangan rule-based, (2) TF-IDF + Naive Bayes, (3) TF-IDF + chiziqli SVM, (4) koʻp tilli transformer (XLM-RoBERTa yoki oʻzbekcha BERT) — Google Colab GPU da qoʻshimcha oʻqitiladi. |
| **FR-32** | Har bir model uchun: accuracy, makro-precision, makro-recall, makro-F1, toifalar boʻyicha hisobot, xatolar matritsasi (rasm), oʻrtacha bashorat vaqti. Natijalar JSON va PNG koʻrinishida saqlanadi.                                |
| **FR-33** | Kirill yozuvidagi va imlo xatoli murojaatlar boʻyicha alohida baholash (normallashtirishning taʼsirini koʻrsatish uchun: normallashtirish bilan va usiz). Kirill yozuvi avtomatik aniqlanadi; imlo xatoli murojaatlar shablondagi “Imlo xatosi” ustunida “Ha” deb belgilanadi.                                                                           |

# 5. Nofunksional talablar

| **NFR-1** | Javob vaqti: SVM versiyasida 1 s dan, transformer versiyasida (CPU) 3 s dan oshmasligi kerak (95-persentil).                                                   |
|-----------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **NFR-2** | Pilot davrida bir vaqtda kamida 50 ta foydalanuvchini qoʻllab-quvvatlash.                                                                                      |
| **NFR-3** | Admin va operator sahifalari parol bilan himoyalangan; 3-bosqichdan boshlab parollar xeshlangan (1–2-bosqichlarda admin paroli faqat .env da); Telegram token va maxfiy kalitlar .env faylida saqlanadi va GitHub ga yuklanmaydi. |
| **NFR-4** | Veb-sahifa HTTPS orqali ishlaydi; interfeys tili — oʻzbek (lotin).                                                                                             |
| **NFR-5** | Kod sifati: Python 3.11+, Ruff va Black; asosiy modullar (normallashtirish, strategiya, koʻrsatkichlar) uchun pytest testlari, qamrov kamida 70%.              |
| **NFR-6** | Har kuni maʼlumotlar bazasining zaxira nusxasi olinadi.                                                                                                        |

# 6. Texnologiyalar

| **Yoʻnalish**               | **Texnologiya**                                                                 |
|-----------------------------|---------------------------------------------------------------------------------|
| Dasturlash tili             | Python 3.11+                                                                    |
| Veb-ilova va API            | FastAPI, Jinja2, Bootstrap 5, Chart.js                                          |
| Telegram bot                | aiogram 3 (pilotda polling rejimi, keyin webhook)                               |
| Maʼlumotlar bazasi          | SQLite + SQLAlchemy 2, Alembic (keyinchalik PostgreSQL)                         |
| NLP va mashinaviy oʻrganish | scikit-learn, pandas, numpy; Hugging Face transformers, PyTorch                 |
| Modelni oʻqitish            | Google Colab (GPU)                                                              |
| Testlash va sifat           | pytest, Ruff, Black, GitHub Actions                                             |
| Joylashtirish               | VPS yoki universitet serveri (HTTPS bilan); bepul variant — Render yoki Railway |

# 7. Maʼlumotlar bazasi

| **Jadval**     | **Asosiy maydonlar**                                                                                                                      |
|----------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| users          | id, user_hash, channel, consent, delivery_ref (shifrlangan, faqat yetkazish uchun), created_at                                            |
| dialogs        | id, user_id, channel, model_version, started_at, ended_at, end_reason, resolved (ha/yoʻq/null), csat (1–5/null), handed_off, is_test      |
| messages       | id, dialog_id, sender (talaba/bot/operator), text_masked, text_norm, intent, confidence, response_type, latency_ms, sentiment, delivered_at, outbox_text (shifrlangan, yetkazilgach oʻchiriladi), buttons_json, created_at |
| kb_items       | id, category, intent, questions, answer, source, department, verified                                                                     |
| handoffs       | id, dialog_id, operator_id, status, created_at, answered_at                                                                               |
| staff          | id, login, password_hash, role (operator/ekspert/admin)                                                                                   |
| expert_ratings | id, dialog_id, expert_id, score (1–5)                                                                                                     |
| ahp_judgments  | id, expert_id, level, matrix_json, cr, created_at                                                                                         |
| model_versions | id, name, type, metrics_json, path, created_at, active                                                                                    |
| slang_terms    | id, term, replacement, created_at (FR-7 lugʻati)                                                                                          |
| settings       | key, value, updated_at (τ, σ, faol model, A/B rejimi)                                                                                     |

# 8. Loyiha tuzilmasi

talababot/

├── app/

│ ├── api/ \# FastAPI routerlar: chat, admin, operator, ekspert

│ ├── nlp/ \# normalizer.py, classifier.py, retriever.py, strategy.py,
sentiment.py

│ ├── metrics/ \# k1–k8, ahp.py, integral.py, ab_test.py

│ ├── db/ \# modellar, sessiya

│ ├── templates/ \# chat.html, admin/\*.html

│ └── main.py

├── bot/ \# aiogram Telegram bot

├── experiments/ \# dataset.py, train_baselines.py,
colab_transformer.ipynb, results/

├── data/ \# (gitignore) murojaatlar va KB Excel fayllari

├── models/ \# saqlangan modellar

├── tests/

├── .env.example

└── README.md

# 9. Ish bosqichlari

Dastur bosqichma-bosqich quriladi. Har bir bosqich oxirida ishlaydigan
natija boʻladi va Git da alohida commit sifatida saqlanadi. Maʼlumot
yigʻish (0-bosqich) dasturlash bilan parallel davom etadi.

| **Bosqich**                  | **Natija**                                                                                                              | **Talablar**               | **Muddat** |
|------------------------------|-------------------------------------------------------------------------------------------------------------------------|----------------------------|------------|
| 0\. Maʼlumot yigʻish         | Kamida 1500–2000 ta belgilangan murojaat, toʻldirilgan bilimlar bazasi                                                  | —                          | 1–4-hafta  |
| 1\. Skelet                   | FastAPI ilova, maʼlumotlar bazasi, Dialog API, sinov uchun veb-chat, oddiy parol bilan himoyalangan admin panel, bilimlar bazasini Excel dan import                 | FR-2, FR-3, FR-4, FR-15–17 | 1-hafta    |
| 2\. NLP yadro                | Normallashtirish, rule-based va SVM tasniflash, ishonch chegarasi strategiyasi, kontekst, log                           | FR-5–14, FR-23–24          | 2-hafta    |
| 3\. Telegram bot va operator | aiogram bot, dialogni yakunlash va baholash, hissiy baho, operator paneli (javob Telegram ga yetkaziladi), panellarni staff jadvali va xeshlangan parollarga oʻtkazish               | FR-1, FR-18–22             | 3-hafta    |
| 4\. Tahlil paneli            | k1–k8, AHP, Q, kS, kanal boʻyicha grafiklar, ekspert baholash sahifasi, eksport                                         | FR-25–29                   | 4-hafta    |
| 5\. Eksperiment              | 4 ta model taqqoslash, transformer (Colab), A/B rejim                                                                   | FR-30–33, FR-14            | 4–5-hafta  |
| 6\. Testlar va joylashtirish | pytest testlari, serverga joylash (HTTPS), botni doimiy ishga tushirish                                                 | NFR-1–6                    | 6-hafta    |
| 7\. Pilot                    | Bot havolasi va QR kodni dekanat orqali guruhlarga tarqatish, 3 hafta sinov (A/B rejimida)                              | —                          | 6–8-hafta  |
| 8\. Tahlil                   | Pilot natijalari (umumiy va kanal boʻyicha), ekspert baholari, AHP soʻrovi, dissertatsiya 3.3 uchun jadval va grafiklar | —                          | 9-hafta    |

# 10. Qabul mezonlari

- Telegram bot orqali toʻliq ish sikli ishlaydi: savol → javob yoki
  aniqlashtirish yoki operator → baholash → log → tahlil paneli.

- Telegram bot va veb-chat bir xil savolga bir xil javob beradi;
  ularning dialoglari tahlil panelida kanal boʻyicha alohida koʻrinadi.

- Kirill va lotin yozuvidagi bir xil savol bir xil toifaga tasniflanadi.

- Ishonch past boʻlganda aniqlashtiruvchi savol, ikki marta
  tushunilmaganda operatorga uzatish ishlaydi.

- Har bir dialog oxirida baholash soʻraladi va natija bazaga yoziladi.

- Tahlil paneli k1–k8, Q va kS ni loglardan hisoblaydi; qoʻlda
  tekshirilgan namunaviy hisob bilan mos keladi.

- Eksperiment skripti bitta buyruq bilan qayta ishga tushiriladi va bir
  xil natija beradi.

- Logda ism, telefon va email ochiq holda saqlanmaydi.

# 11. Xavflar va cheklovlar

| **Xavf**                                          | **Chora**                                                                                                |
|---------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| Maʼlumotlar yetarli emas yoki toifalar notekis    | Har toifada kamida 150 ta; sinf vaznlari; kross-validatsiya                                              |
| Bilimlar bazasidagi javob eskirgan yoki notoʻgʻri | Faqat tekshirilgan javoblar; har bir javobda masʼul boʻlim; operatorga uzatish                           |
| Pilotda foydalanuvchilar kam                      | Bot havolasini dekanat va guruh sardorlari orqali tarqatish, QR kod, fakultet Telegram kanallarida eʼlon |
| Talabalar baholash soʻroviga kam javob beradi     | kS koʻrsatkichi bilan toʻldirish; javob berish ulushini alohida hisobotda koʻrsatish                     |
| Transformer model serverda sekin ishlaydi         | Kichikroq model, ONNX formatiga oʻtkazish yoki SVM versiyasini asosiy qilib qoldirish                    |
