from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import admin, admin_config, chat
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="TalabaBot")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    https_only=settings.cookie_secure,
    same_site="lax",
)
app.include_router(chat.router)
app.include_router(admin.public)
app.include_router(admin.router)
app.include_router(admin_config.router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def chat_page(request: Request):
    return admin.templates.TemplateResponse(request, "chat.html")
