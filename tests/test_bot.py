import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramServerError
from aiogram.methods import SendMessage
from aiogram.types import Message

from app.dialog import _rate_buttons, _resolved_buttons
from app.kb_import import CATEGORIES
from bot import main
from bot.api import ApiClient

TELEGRAM_CALLBACK_LIMIT = 64
REPLY = {"text": "Javob", "buttons": [{"label": "Operator", "action": "operator"}]}
METHOD = SendMessage(chat_id=1, text="x")


def fake_message(text="salom"):
    message = MagicMock(spec=Message)
    message.text = text
    message.chat = SimpleNamespace(id=42)
    message.answer = AsyncMock()
    message.answer_photo = AsyncMock()
    message.edit_reply_markup = AsyncMock()
    message.edit_text = AsyncMock()
    message.edit_caption = AsyncMock()
    message.bot = MagicMock(send_chat_action=AsyncMock())
    message.html_text = "Savol"
    message.caption = None
    message.reply_markup = None
    return message


def fake_api(reply=REPLY):
    api = MagicMock(spec=ApiClient)
    api.send = AsyncMock(return_value=reply)
    api.pending = AsyncMock(return_value=[])
    api.ack = AsyncMock()
    api.topics = AsyncMock(return_value=[])
    return api


def run(coroutine):
    return asyncio.run(coroutine)


def markup_rows(markup):
    return [[b.text for b in row] for row in markup.inline_keyboard]


def test_descriptions_fit_telegram_limits():
    assert len(main.DESCRIPTION) <= 512
    assert len(main.SHORT_DESCRIPTION) <= 120


def test_no_buttons_means_no_keyboard():
    assert main.build_keyboard([]) is None


def test_rating_buttons_share_one_row():
    buttons = [{"label": str(n), "action": f"rate:1:{n}"} for n in range(1, 6)]
    assert markup_rows(main.build_keyboard(buttons)) == [["1 ⭐", "2 ⭐", "3 ⭐", "4 ⭐", "5 ⭐"]]


def test_dialog_buttons_get_emoji_and_share_row_but_options_do_not():
    buttons = [
        {"label": "Stipendiya", "action": "category:Stipendiya"},
        {"label": "Yotoqxona", "action": "category:Yotoqxona"},
        {"label": "Operator", "action": "operator"},
        {"label": "Yakunlash", "action": "end"},
    ]
    assert markup_rows(main.build_keyboard(buttons)) == [
        ["💰 Stipendiya"],
        ["🏠 Yotoqxona"],
        ["👤 Operator", "🏁 Yakunlash"],
    ]


def test_feedback_and_consent_labels():
    labels = [
        main.button_label({"label": "Ha", "action": "resolved:3:yes"}),
        main.button_label({"label": "Yoʻq", "action": "resolved:3:no"}),
        main.button_label({"label": "Roziman", "action": "consent_yes"}),
    ]
    assert labels == ["👍 Ha", "👎 Yoʻq", "✅ Roziman"]


def test_every_category_has_menu_entry_and_emoji():
    assert set(main.MENU.values()) == set(CATEGORIES) == set(main.CATEGORY_EMOJI)


def test_kb_answer_is_formatted_with_header_contacts_and_links():
    text = (
        "Javob <matni>\n\n"
        "Masʼul boʻlim: Buxgalteriya: 2-qavat, 6-xona; Du–Ju, 14:00–17:00; "
        "+998 65 221-30-46; u@buxdu.uz; Fakultet dekanati:\n"
        "Manba: buxdu.uz/abc; lex.uz/acts/1"
    )
    html = main.format_reply(
        {"text": text, "response_type": "kb", "category": "Stipendiya", "title": "Qancha?"}
    )
    assert html.startswith("💰 <i>Stipendiya</i>\n<b>Qancha?</b>\n\nJavob &lt;matni&gt;")
    for part in (
        "▪️ <b>Buxgalteriya</b>\n📍 2-qavat, 6-xona",
        "🕑 Du–Ju, 14:00–17:00",
        "📞 +998 65 221-30-46",
        "✉️ u@buxdu.uz",
        "▪️ <b>Fakultet dekanati</b>",
        '<a href="https://buxdu.uz/abc">buxdu.uz/abc</a>',
    ):
        assert part in html


def test_system_texts_are_prettified_and_others_escaped():
    from app import dialog

    assert main.format_reply({"text": dialog.WELCOME}) == main.PRETTY[dialog.WELCOME]
    assert main.format_reply({"text": "a<b", "response_type": "system"}) == "a&lt;b"
    operator = main.format_pending({"text": "<salom>", "sender": "operator"})
    assert operator == "👤 <b>Operator javobi</b>\n\n&lt;salom&gt;"


def test_menu_button_shows_topics_list():
    message, api = fake_message("💰 Stipendiya"), fake_api()
    api.topics.return_value = [{"id": 8, "title": "Stipendiya qancha?"}]
    run(main.on_text(message, api))
    api.topics.assert_awaited_once_with("Stipendiya")
    api.send.assert_not_awaited()
    markup = message.answer.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == "kb:8"


def test_empty_category_says_so():
    message, api = fake_message("💡 Boshqa"), fake_api()
    run(main.on_text(message, api))
    assert "tayyor javoblar yoʻq" in message.answer.await_args.args[0]


def test_menu_operator_and_help_buttons():
    message, api = fake_message(main.MENU_OPERATOR), fake_api()
    run(main.on_text(message, api))
    api.send.assert_awaited_once_with(42, action="operator")
    message = fake_message(main.MENU_HELP)
    run(main.on_text(message, fake_api()))
    assert message.answer.await_args.args[0] == main.HELP_TEXT


def test_reply_without_buttons_attaches_main_menu_and_shows_typing():
    message, api = fake_message(), fake_api({"text": "x", "buttons": []})
    run(main.on_text(message, api))
    message.bot.send_chat_action.assert_awaited_once()
    assert message.answer.await_args.kwargs["reply_markup"] == main.main_menu()


def test_start_sends_welcome_photo():
    message, api = fake_message("/start"), fake_api({"text": "x", "buttons": []})
    run(main.on_start(message, api))
    message.answer_photo.assert_awaited_once()
    assert message.answer_photo.await_args.kwargs["caption"] == "x"


def test_rating_choice_is_written_into_message():
    message, api = fake_message(), fake_api()
    query = SimpleNamespace(answer=AsyncMock(), message=message, data="rate:5:4")
    run(main.on_button(query, api))
    assert message.edit_text.await_args.args[0] == "Savol\n\n<i>Bahoingiz: ⭐⭐⭐⭐</i>"


def test_topic_button_keeps_list_open():
    message, api = fake_message(), fake_api()
    query = SimpleNamespace(answer=AsyncMock(), message=message, data="kb:8")
    run(main.on_button(query, api))
    message.edit_text.assert_not_awaited()
    message.edit_reply_markup.assert_not_awaited()
    api.send.assert_awaited_once_with(42, action="kb:8")


def test_every_action_fits_telegram_callback_limit():
    big_id = 999_999_999_999
    actions = [f"category:{category}" for category in CATEGORIES]
    actions += [b.action for b in _resolved_buttons(big_id) + _rate_buttons(big_id)]
    assert all(len(action.encode()) <= TELEGRAM_CALLBACK_LIMIT for action in actions)


def test_text_goes_to_api_and_reply_has_keyboard():
    message, api = fake_message("savol"), fake_api()
    run(main.on_text(message, api))
    api.send.assert_awaited_once_with(42, text="savol")
    args, kwargs = message.answer.await_args
    assert args == ("Javob",)
    assert markup_rows(kwargs["reply_markup"]) == [["👤 Operator"]]


@pytest.mark.parametrize(
    ("handler", "action"),
    [(main.on_start, "start"), (main.on_operator, "operator"), (main.on_end, "end")],
)
def test_commands_send_actions(handler, action):
    message, api = fake_message("/x"), fake_api()
    run(handler(message, api))
    api.send.assert_awaited_once_with(42, action=action)


def test_help_and_non_text_answer_locally():
    message = fake_message()
    run(main.on_help(message))
    assert "/operator" in message.answer.await_args.args[0]
    run(main.on_other(message))
    assert message.answer.await_args.args[0] == main.TEXT_ONLY
    assert message.answer.await_args.kwargs["reply_markup"] == main.main_menu()


def test_api_failure_tells_user():
    message, api = fake_message(), fake_api()
    api.send.side_effect = httpx.ConnectError("down")
    run(main.on_text(message, api))
    assert message.answer.await_args.args[0] == main.API_ERROR


def test_button_removes_keyboard_and_sends_action():
    message, api = fake_message(), fake_api()
    query = SimpleNamespace(answer=AsyncMock(), message=message, data="end")
    run(main.on_button(query, api))
    query.answer.assert_awaited_once()
    message.edit_reply_markup.assert_awaited_once()
    api.send.assert_awaited_once_with(42, action="end")


def test_pressed_button_label_is_noted_and_keyboard_removed():
    message, api = fake_message(), fake_api()
    message.reply_markup = main.build_keyboard([{"label": "Ha", "action": "resolved:5:yes"}])
    query = SimpleNamespace(answer=AsyncMock(), message=message, data="resolved:5:yes")
    run(main.on_button(query, api))
    args, kwargs = message.edit_text.await_args
    assert args == ("Savol\n\n<i>Tanlovingiz: 👍 Ha</i>",)
    assert kwargs == {"reply_markup": None}


def item(identifier):
    return {"id": identifier, "chat_id": "42", "text": f"t{identifier}", "buttons": []}


def test_delivery_sends_then_acks():
    bot, api = MagicMock(send_message=AsyncMock()), fake_api()
    api.pending.return_value = [item(1), item(2)]
    run(main.deliver_once(bot, api))
    assert [c.args for c in bot.send_message.await_args_list] == [(42, "t1"), (42, "t2")]
    assert [c.args[0] for c in api.ack.await_args_list] == [1, 2]


def test_blocked_user_is_acked_so_queue_moves():
    bot, api = MagicMock(send_message=AsyncMock()), fake_api()
    bot.send_message.side_effect = [TelegramForbiddenError(METHOD, "blocked"), None]
    api.pending.return_value = [item(1), item(2)]
    run(main.deliver_once(bot, api))
    assert [c.args[0] for c in api.ack.await_args_list] == [1, 2]


def test_temporary_telegram_error_keeps_message_for_retry():
    bot, api = MagicMock(send_message=AsyncMock()), fake_api()
    bot.send_message.side_effect = TelegramServerError(METHOD, "boom")
    api.pending.return_value = [item(1), item(2)]
    run(main.deliver_once(bot, api))
    api.ack.assert_not_awaited()
    assert bot.send_message.await_count == 1


def test_api_client_sends_token_and_truncates():
    seen = {}

    def handler(request):
        seen["token"] = request.headers["X-Internal-Token"]
        seen["body"] = request.content
        return httpx.Response(200, json=REPLY)

    client = ApiClient("http://api", "secret", transport=httpx.MockTransport(handler))
    run(client.send(7, text="x" * 3000))
    assert seen["token"] == "secret"
    assert b'"user_id":"7"' in seen["body"]
    assert b'"text":"' + b"x" * 2000 + b'"' in seen["body"]


def test_api_client_raises_on_error_status():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    client = ApiClient("http://api", "secret", transport=transport)
    with pytest.raises(httpx.HTTPStatusError):
        run(client.pending())


def test_run_builds_bot_with_html_defaults(monkeypatch):
    # run() aiogram parametrlarini toʻgʻri nomlaganini tekshiradi (xato nom botni yiqitadi).
    captured = {}

    class Stop(Exception):
        pass

    def fake_bot(token, default):
        captured["default"] = default
        raise Stop

    monkeypatch.setattr(main, "Bot", fake_bot)
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(telegram_bot_token="t"))
    with pytest.raises(Stop):
        run(main.run())
    assert captured["default"].parse_mode == "HTML"
    assert captured["default"].link_preview_is_disabled is True
