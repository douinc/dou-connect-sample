from fastapi import FastAPI

from app.api.router import build_api_router
from app.config import get_settings
from app.dependencies import AppState, build_app_state
from app.oauth.router import build_oauth_router
from app.webhook.router import build_webhook_router


def create_app(state: AppState) -> FastAPI:
    app = FastAPI(title="DOU Connect Sample (Saylog)")
    app.include_router(build_oauth_router(state))
    app.include_router(build_api_router(state))
    app.include_router(build_webhook_router(state))
    return app


def get_app() -> FastAPI:
    return create_app(build_app_state(get_settings()))
