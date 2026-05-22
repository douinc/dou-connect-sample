from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.config import Settings, get_settings
from app.connect.client import ConnectClient


def load_settings() -> Settings:
    settings = get_settings()
    if not settings.dou_connect_client_id or not settings.dou_connect_client_secret.get_secret_value():
        raise SystemExit(
            "DOU_CONNECT_CLIENT_ID / DOU_CONNECT_CLIENT_SECRET가 .env에 설정되어야 합니다.",
        )
    return settings


@asynccontextmanager
async def connect_client(settings: Settings) -> AsyncIterator[ConnectClient]:
    async with ConnectClient(
        base_url=settings.dou_connect_base_url,
        client_id=settings.dou_connect_client_id,
        client_secret=settings.dou_connect_client_secret.get_secret_value(),
        audience=settings.dou_connect_audience,
        scope=settings.dou_connect_scope or None,
        provider_code=settings.dou_connect_provider_code or None,
    ) as c:
        yield c
