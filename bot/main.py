"""Telegram bot (FR-1): python -m bot.main"""

import asyncio
import contextlib
import logging
import re
from html import escape
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app import dialog as d
from app.config import get_settings
from bot.api import ApiClient

logger = logging.getLogger(__name__)

_POLL_SECONDS = 2
_TELEGRAM_TEXT_LIMIT = 4096
_CAPTION_LIMIT = 1024
_TOPIC_LABEL_LIMIT = 60
WELCOME_PHOTO = Path(__file__).parent / "rasmlar" / "talababot_profil.png"

# --- Boʻlimlar va menyu -------------------------------------------------------

CATEGORY_EMOJI = {
    "Oʻquv jarayoni": "📚",
    "Stipendiya": "💰",
    "Yotoqxona": "🏠",
    "Hujjatlar va arizalar": "📄",
    "Akademik taʼtil va koʻchirish": "🎓",
    "Boshqa": "💡",
}
_MENU_SHORT = {
    "Hujjatlar va arizalar": "Hujjatlar",
    "Akademik taʼtil va koʻchirish": "Akademik taʼtil",
}
MENU = {
    f"{emoji} {_MENU_SHORT.get(category, category)}": category
    for category, emoji in CATEGORY_EMOJI.items()
}
MENU_OPERATOR = "👤 Operator"
MENU_HELP = "ℹ️ Yordam"


def main_menu() -> ReplyKeyboardMarkup:
    labels = list(MENU)
    rows = [labels[i : i + 2] for i in range(0, len(labels), 2)] + [[MENU_OPERATOR, MENU_HELP]]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label) for label in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Savolingizni yozing…",
    )


# --- Matnlar ------------------------------------------------------------------

HELP_TEXT = (
    "ℹ️ <b>Qanday foydalaniladi?</b>\n\n"
    "✍️ Savolingizni oddiy matn bilan yozing — lotin yoki kirill alifbosida.\n"
    "📋 Yoki pastdagi menyudan boʻlimni tanlab, tayyor savollardan birini bosing.\n\n"
    "<b>Buyruqlar</b>\n"
    "/menu — 📋 boʻlimlar menyusi\n"
    "/operator — 👤 operator bilan bogʻlanish\n"
    "/end — 🏁 suhbatni yakunlash\n"
    "/help — ℹ️ yordam"
)
API_ERROR = "⚠️ Xatolik yuz berdi. Birozdan soʻng qayta urinib koʻring."
TEXT_ONLY = (
    "🎙 Hozircha faqat matnli xabarlarni tushunaman.\n"
    "Savolingizni yozing yoki menyudan boʻlimni tanlang 👇"
)
MENU_TEXT = "📋 <b>Boʻlimni tanlang</b> yoki savolingizni yozing 👇"
# Talaba /start bosishidan oldin Telegram'da koʻrinadi (limitlar: 512 va 120 belgi).
DESCRIPTION = (
    "Buxoro davlat universiteti talabalari uchun yordamchi bot.\n\n"
    "Oʻquv jarayoni, stipendiya, yotoqxona, hujjatlar va akademik taʼtil boʻyicha "
    "savolingizni oddiy matn bilan yozing. Javob topilmasa, murojaatingiz operatorga uzatiladi.\n\n"
    "Bot magistrlik dissertatsiyasi doirasida sinovdan oʻtkazilmoqda. "
    "Suhbatlar anonim saqlanadi."
)
SHORT_DESCRIPTION = (
    "Talabalar savollariga javob beruvchi bot: stipendiya, yotoqxona, hujjatlar va boshqa."
)

_CATEGORY_LINES = "\n".join(f"{emoji} {name}" for name, emoji in CATEGORY_EMOJI.items())
# Dialog qatlami bazaga oddiy matn yozadi; Telegram'da ularning bezatilgan koʻrinishi chiqadi.
PRETTY = {
    d.CONSENT_NOTICE: (
        "👋 <b>Assalomu alaykum!</b>\n\n"
        "Men <b>TalabaBot</b> — Buxoro davlat universiteti talabalarining yordamchisiman.\n\n"
        f"Quyidagi mavzularda javob beraman:\n{_CATEGORY_LINES}\n\n"
        "🔒 Suhbatlar ilmiy tadqiqot maqsadida <b>anonim</b> saqlanadi. Rozimisiz?"
    ),
    d.WELCOME: (
        "✨ <b>Savolingizni yozing</b> — masalan: <i>«Stipendiya qachon tushadi?»</i>\n\n"
        "Yoki pastdagi menyudan boʻlimni tanlang 👇"
    ),
    d.HANDED_OFF: "👤 <b>Murojaatingiz operatorga uzatildi.</b>\nJavobni shu yerda olasiz ⏳",
    d.ALREADY_HANDED_OFF: "👤 Murojaatingiz allaqachon operatorga uzatilgan ⏳",
    d.NOT_UNDERSTOOD: (
        "🤔 Kechirasiz, savolingizni tushuna olmadim.\n\n"
        "👤 Murojaatingiz <b>operatorga uzatildi</b> — javobni shu yerda olasiz ⏳"
    ),
    d.WAITING_FOR_OPERATOR: "⏳ Murojaatingiz operatorda. Javobni shu yerda olasiz.",
    d.END_PROMPT: "🏁 <b>Suhbat yakunlandi.</b>\n\nMuammoingiz hal boʻldimi?",
    d.RATE_PROMPT: "⭐ <b>Xizmatni baholang</b> — 1 dan 5 gacha:",
    d.THANKS: (
        "🙏 <b>Rahmat!</b> Fikringiz biz uchun muhim.\nYangi savolingiz boʻlsa, bemalol yozing."
    ),
    d.NO_ACTIVE_DIALOG: (
        "💬 Faol suhbat yoʻq. Savolingizni yozing yoki menyudan boʻlimni tanlang 👇"
    ),
    d.YOU_ARE_WELCOME: "😊 Arzimaydi! Yangi savolingiz boʻlsa, bemalol yozing.",
    d.TOPIC_GONE: "⚠️ Bu mavzu hozir mavjud emas. Savolingizni yozib yuboring.",
}

_PHONE = re.compile(r"^\+?\d[\d\s()-]{6,}$")
_EMAIL = re.compile(r"^\S+@\S+\.\w+$")
_TIME = re.compile(r"\d{1,2}:\d{2}")
_URL = re.compile(r"^(https?://)?[\w.-]+\.(uz|com|org|net)(/\S*)?$")


def _link(url: str) -> str:
    href = url if url.startswith(("http://", "https://")) else f"https://{url}"
    return f'<a href="{escape(href)}">{escape(url)}</a>'


def _contact_line(part: str) -> str:
    if _PHONE.match(part):
        return f"📞 {escape(part)}"
    if _EMAIL.match(part):
        return f"✉️ {escape(part)}"
    if _URL.match(part):
        return f"🌐 {_link(part)}"
    if _TIME.search(part):
        return f"🕑 {escape(part)}"
    return f"📍 {escape(part)}"


def _department_block(value: str) -> str:
    lines = ["🏢 <b>Masʼul boʻlim</b>"]
    for part in (p.strip() for p in value.split(";")):
        if not part:
            continue
        # "Boʻlim nomi: tafsilot" → nomi qalin, tafsilot alohida qatorda.
        name, sep, rest = part.partition(": ")
        if sep:
            lines.append(f"▪️ <b>{escape(name)}</b>")
            lines.append(_contact_line(rest.strip()))
        elif part.endswith(":"):
            lines.append(f"▪️ <b>{escape(part[:-1])}</b>")
        else:
            lines.append(_contact_line(part))
    return "\n".join(lines)


def _source_block(value: str) -> str:
    parts = [p.strip() for p in value.split(";") if p.strip()]
    links = (_link(p) if _URL.match(p) else escape(p) for p in parts)
    return "🔗 <b>Manba</b>\n" + "\n".join(links)


def format_answer(text: str, category: str | None, title: str | None) -> str:
    body, extras = [], []
    for line in text.split("\n"):
        if line.startswith("Masʼul boʻlim: "):
            extras.append(_department_block(line.removeprefix("Masʼul boʻlim: ")))
        elif line.startswith("Manba: "):
            extras.append(_source_block(line.removeprefix("Manba: ")))
        else:
            body.append(line)
    header = []
    if category:
        header.append(f"{CATEGORY_EMOJI.get(category, '💬')} <i>{escape(category)}</i>")
    if title:
        header.append(f"<b>{escape(title)}</b>")
    parts = ["\n".join(header), escape("\n".join(body).strip()), *extras]
    return "\n\n".join(p for p in parts if p)


def format_reply(reply: dict) -> str:
    text = reply["text"]
    if text in PRETTY:
        return PRETTY[text]
    kind = reply.get("response_type")
    if kind == "kb":
        return format_answer(text, reply.get("category"), reply.get("title"))
    if kind == "clarify":
        return "🔎 " + escape(text)
    return escape(text)


def format_pending(item: dict) -> str:
    if item.get("sender") == "operator":
        return "👤 <b>Operator javobi</b>\n\n" + escape(item["text"])
    return PRETTY.get(item["text"]) or escape(item["text"])


# --- Tugmalar -----------------------------------------------------------------

_FIXED_LABELS = {
    "consent_yes": "✅ Roziman",
    "consent_no": "❌ Rozi emasman",
    "operator": "👤 Operator",
    "end": "🏁 Yakunlash",
}


def button_label(button: dict) -> str:
    action = button["action"]
    if action in _FIXED_LABELS:
        return _FIXED_LABELS[action]
    if action.startswith("resolved:"):
        return "👍 Ha" if action.endswith(":yes") else "👎 Yoʻq"
    if action.startswith("rate:"):
        return f"{action.rsplit(':', 1)[1]} ⭐"
    if action.startswith(d.CATEGORY_ACTION_PREFIX):
        category = action.removeprefix(d.CATEGORY_ACTION_PREFIX)
        return f"{CATEGORY_EMOJI.get(category, '💬')} {button['label']}"
    return button["label"]


def _row_kind(action: str) -> str:
    """Bir turdagi qisqa tugmalar bitta qatorga joylanadi, qolganlari alohida qatorda."""
    for prefix in ("rate:", "resolved:", "consent_"):
        if action.startswith(prefix):
            return prefix
    if action in ("operator", "end"):
        return "dialog"
    return action


def build_keyboard(buttons: list[dict]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    last_kind = None
    for button in buttons:
        kind = _row_kind(button["action"])
        item = InlineKeyboardButton(text=button_label(button), callback_data=button["action"])
        if rows and kind == last_kind:
            rows[-1].append(item)
        else:
            rows.append([item])
        last_kind = kind
    return InlineKeyboardMarkup(inline_keyboard=rows)


def topics_keyboard(topics: list[dict]) -> InlineKeyboardMarkup:
    def label(title: str) -> str:
        if len(title) <= _TOPIC_LABEL_LIMIT:
            return title
        return title[: _TOPIC_LABEL_LIMIT - 1].rstrip() + "…"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label(t["title"]), callback_data=f"{d.KB_ACTION_PREFIX}{t['id']}"
                )
            ]
            for t in topics
        ]
    )


# --- Handlerlar ---------------------------------------------------------------

router = Router()
router.message.filter(F.chat.type == "private")
_photo_cache: dict[str, str] = {}


async def _typing(message: Message) -> None:
    """Javob tayyorlanayotganda "yozmoqda…" holati koʻrinadi."""
    with contextlib.suppress(TelegramAPIError, AttributeError, TypeError):
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)


async def _send_with_photo(message: Message, text: str, markup) -> None:
    if not WELCOME_PHOTO.exists() or len(text) > _CAPTION_LIMIT:
        await message.answer(text, reply_markup=markup)
        return
    photo = _photo_cache.get("welcome") or FSInputFile(WELCOME_PHOTO)
    sent = await message.answer_photo(photo, caption=text, reply_markup=markup)
    # Keyingi safar faylni qayta yuklamaslik uchun Telegram file_id si saqlanadi.
    with contextlib.suppress(AttributeError, IndexError, TypeError):
        _photo_cache["welcome"] = sent.photo[-1].file_id


async def _reply(message: Message, api: ApiClient, *, with_photo: bool = False, **body) -> None:
    await _typing(message)
    try:
        reply = await api.send(message.chat.id, **body)
    except httpx.HTTPError:
        logger.exception("Dialog API xatosi")
        await message.answer(API_ERROR)
        return
    text = format_reply(reply)[:_TELEGRAM_TEXT_LIMIT]
    # Inline tugmalar boʻlmasa, pastki menyu yuboriladi (eski talabalarda ham paydo boʻladi).
    markup = build_keyboard(reply["buttons"]) or main_menu()
    if with_photo:
        await _send_with_photo(message, text, markup)
    else:
        await message.answer(text, reply_markup=markup)


async def show_topics(message: Message, api: ApiClient, category: str) -> None:
    await _typing(message)
    try:
        topics = await api.topics(category)
    except httpx.HTTPError:
        logger.exception("Mavzular roʻyxatini olishda xato")
        await message.answer(API_ERROR)
        return
    header = f"{CATEGORY_EMOJI.get(category, '💬')} <b>{escape(category)}</b>\n\n"
    if not topics:
        await message.answer(
            header + "Bu boʻlimda hozircha tayyor javoblar yoʻq.\n"
            "Savolingizni yozing — kerak boʻlsa operatorga uzataman ✍️"
        )
        return
    await message.answer(
        header + "Savollardan birini tanlang yoki oʻzingiz yozing 👇",
        reply_markup=topics_keyboard(topics),
    )


@router.message(CommandStart())
async def on_start(message: Message, api: ApiClient) -> None:
    await _reply(message, api, with_photo=True, action="start")


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("menu"))
async def on_menu(message: Message) -> None:
    await message.answer(MENU_TEXT, reply_markup=main_menu())


@router.message(Command("operator"))
async def on_operator(message: Message, api: ApiClient) -> None:
    await _reply(message, api, action="operator")


@router.message(Command("end"))
async def on_end(message: Message, api: ApiClient) -> None:
    await _reply(message, api, action="end")


@router.message(F.text)
async def on_text(message: Message, api: ApiClient) -> None:
    if message.text in MENU:
        await show_topics(message, api, MENU[message.text])
    elif message.text == MENU_OPERATOR:
        await _reply(message, api, action="operator")
    elif message.text == MENU_HELP:
        await on_help(message)
    else:
        await _reply(message, api, text=message.text)


@router.message()
async def on_other(message: Message) -> None:
    await message.answer(TEXT_ONLY, reply_markup=main_menu())


def _choice_note(message: Message, data: str) -> str | None:
    if data.startswith("rate:"):
        return "Bahoingiz: " + "⭐" * int(data.rsplit(":", 1)[1])
    markup = message.reply_markup
    for row in markup.inline_keyboard if markup else []:
        for button in row:
            if button.callback_data == data:
                return f"Tanlovingiz: {button.text}"
    return None


async def _mark_choice(message: Message, data: str) -> None:
    """Bosilgan tugma xabarda qayd etiladi, eski tugmalar qayta bosilmasligi uchun olinadi."""
    note = _choice_note(message, data)
    with contextlib.suppress(TelegramBadRequest):
        if note is None:
            await message.edit_reply_markup(reply_markup=None)
            return
        new_text = f"{message.html_text}\n\n<i>{escape(note)}</i>"
        if message.caption is not None:
            await message.edit_caption(caption=new_text, reply_markup=None)
        else:
            await message.edit_text(new_text, reply_markup=None)


@router.callback_query(F.data)
async def on_button(query: CallbackQuery, api: ApiClient) -> None:
    await query.answer()
    if not isinstance(query.message, Message):
        return
    # Mavzular roʻyxati ochiq qoladi — talaba boshqa savolni ham tanlashi mumkin.
    if not query.data.startswith(d.KB_ACTION_PREFIX):
        await _mark_choice(query.message, query.data)
    await _reply(query.message, api, action=query.data)


async def deliver_once(bot: Bot, api: ApiClient) -> None:
    for item in await api.pending():
        try:
            await bot.send_message(
                int(item["chat_id"]),
                format_pending(item)[:_TELEGRAM_TEXT_LIMIT],
                reply_markup=build_keyboard(item["buttons"]),
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            # Talaba botni bloklagan: qayta urinish foydasiz.
            logger.warning("Xabar %s yetkazilmadi", item["id"])
        except TelegramAPIError:
            logger.exception("Telegram xatosi, keyingi urinishda qayta yuboriladi")
            return
        await api.ack(item["id"])


async def deliver_forever(bot: Bot, api: ApiClient) -> None:
    while True:
        try:
            await deliver_once(bot, api)
        except httpx.HTTPError:
            logger.exception("Yetkazish navbatini olishda xato")
        await asyncio.sleep(_POLL_SECONDS)


async def run() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit(".env faylida TELEGRAM_BOT_TOKEN toʻldirilmagan.")

    bot = Bot(
        settings.telegram_bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )
    api = ApiClient(settings.api_base_url, settings.bot_api_token)
    dispatcher = Dispatcher()
    dispatcher["api"] = api
    dispatcher.include_router(router)
    await bot.set_my_description(DESCRIPTION)
    await bot.set_my_short_description(SHORT_DESCRIPTION)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Boshlash"),
            BotCommand(command="menu", description="Boʻlimlar menyusi"),
            BotCommand(command="help", description="Yordam"),
            BotCommand(command="operator", description="Operator bilan bogʻlanish"),
            BotCommand(command="end", description="Suhbatni yakunlash"),
        ]
    )
    delivery = asyncio.create_task(deliver_forever(bot, api))
    try:
        await dispatcher.start_polling(bot)
    finally:
        delivery.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await delivery
        await api.close()
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # Har bir xabar uchun yozuv logni tez toʻldiradi.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run())
