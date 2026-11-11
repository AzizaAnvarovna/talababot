import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import admin, admin_config, analytics, chat, expert, internal, operator
from app.config import get_settings
from app.db.session import SessionLocal
from app.dialog import close_inactive_dialogs

settings = get_settings()
logger = logging.getLogger(__name__)
_SWEEP_SECONDS = 30


def _sweep() -> None:
    with SessionLocal() as db:
        close_inactive_dialogs(db)


async def _sweep_forever() -> None:
    while True:
        await asyncio.sleep(_SWEEP_SECONDS)
        try:
            await asyncio.to_thread(_sweep)
        except Exception:  # bitta xato keyingi tekshiruvlarni toʻxtatmasligi kerak
            logger.exception("Faolsiz dialoglarni yopishda xato")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_sweep_forever())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# HTTPS dagi ishchi serverda API hujjati ochiq turmaydi.
app = FastAPI(
    title="TalabaBot",
    lifespan=lifespan,
    docs_url=None if settings.cookie_secure else "/docs",
    redoc_url=None if settings.cookie_secure else "/redoc",
    openapi_url=None if settings.cookie_secure else "/openapi.json",
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.cookie_secure,
    same_site="lax",
)
app.include_router(chat.router)
app.include_router(internal.router)
app.include_router(admin.public)
app.include_router(admin.router)
app.include_router(admin_config.router)
app.include_router(operator.router)
app.include_router(analytics.router)
app.include_router(expert.router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def chat_page(request: Request):
    return admin.templates.TemplateResponse(request, "chat.html")
