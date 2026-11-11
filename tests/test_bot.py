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
    message.edit_reply_markup = AsyncMock()
    return message


def fake_api(reply=REPLY):
    api = MagicMock(spec=ApiClient)
    api.send = AsyncMock(return_value=reply)
    api.pending = AsyncMock(return_value=[])
    api.ack = AsyncMock()
    return api


def run(coroutine):
    return asyncio.run(coroutine)


def markup_rows(markup):
    return [[b.text for b in row] for row in markup.inline_keyboard]


def test_no_buttons_means_no_keyboard():
    assert main.build_keyboard([]) is None


def test_rating_buttons_share_one_row():
    buttons = [{"label": str(n), "action": f"rate:1:{n}"} for n in range(1, 6)]
    assert markup_rows(main.build_keyboard(buttons)) == [["1", "2", "3", "4", "5"]]


def test_long_buttons_get_own_rows():
    buttons = [{"label": "Operator", "action": "a"}, {"label": "Yakunlash", "action": "b"}]
    assert markup_rows(main.build_keyboard(buttons)) == [["Operator"], ["Yakunlash"]]


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
    assert markup_rows(kwargs["reply_markup"]) == [["Operator"]]


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
