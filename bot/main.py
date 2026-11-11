"""Telegram bot (FR-1): python -m bot.main"""

import asyncio
import contextlib
import logging

import httpx
from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.config import get_settings
from bot.api import ApiClient

logger = logging.getLogger(__name__)

_POLL_SECONDS = 2
_TELEGRAM_TEXT_LIMIT = 4096
_SHORT_LABEL = 2

HELP_TEXT = (
    "Savolingizni oddiy matn koʻrinishida yozing.\n\n"
    "/operator — operator bilan bogʻlanish\n"
    "/end — suhbatni yakunlash\n"
    "/help — yordam"
)
API_ERROR = "Xatolik yuz berdi. Birozdan soʻng qayta urinib koʻring."
TEXT_ONLY = "Hozircha faqat matnli xabarlarni tushunaman."

router = Router()
router.message.filter(F.chat.type == "private")


def build_keyboard(buttons: list[dict]) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    builder = InlineKeyboardBuilder()
    for button in buttons:
        builder.button(text=button["label"], callback_data=button["action"])
    # 1–5 baholash tugmalari bitta qatorga sigʻadi, qolganlari alohida qatorda.
    builder.adjust(len(buttons) if all(len(b["label"]) < _SHORT_LABEL for b in buttons) else 1)
    return builder.as_markup()


async def _reply(message: Message, api: ApiClient, **body) -> None:
    try:
        reply = await api.send(message.chat.id, **body)
    except httpx.HTTPError:
        logger.exception("Dialog API xatosi")
        await message.answer(API_ERROR)
        return
    await message.answer(
        reply["text"][:_TELEGRAM_TEXT_LIMIT], reply_markup=build_keyboard(reply["buttons"])
    )


@router.message(CommandStart())
async def on_start(message: Message, api: ApiClient) -> None:
    await _reply(message, api, action="start")


@router.message(Command("help"))
async def on_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("operator"))
async def on_operator(message: Message, api: ApiClient) -> None:
    await _reply(message, api, action="operator")


@router.message(Command("end"))
async def on_end(message: Message, api: ApiClient) -> None:
    await _reply(message, api, action="end")


@router.message(F.text)
async def on_text(message: Message, api: ApiClient) -> None:
    await _reply(message, api, text=message.text)


@router.message()
async def on_other(message: Message) -> None:
    await message.answer(TEXT_ONLY)


@router.callback_query(F.data)
async def on_button(query: CallbackQuery, api: ApiClient) -> None:
    await query.answer()
    if not isinstance(query.message, Message):
        return
    # Eski tugma qayta bosilmasligi uchun klaviatura olib tashlanadi.
    with contextlib.suppress(TelegramBadRequest):
        await query.message.edit_reply_markup(reply_markup=None)
    await _reply(query.message, api, action=query.data)


async def deliver_once(bot: Bot, api: ApiClient) -> None:
    for item in await api.pending():
        try:
            await bot.send_message(
                int(item["chat_id"]),
                item["text"][:_TELEGRAM_TEXT_LIMIT],
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

    bot = Bot(settings.telegram_bot_token)
    api = ApiClient(settings.api_base_url, settings.bot_api_token)
    dispatcher = Dispatcher()
    dispatcher["api"] = api
    dispatcher.include_router(router)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Boshlash"),
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
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
