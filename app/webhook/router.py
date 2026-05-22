import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.dependencies import AppState
from app.webhook.signature import verify_signature

logger = logging.getLogger(__name__)


def build_webhook_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.post("/webhook/saylog")
    async def receive(
        request: Request,
        background: BackgroundTasks,
        saylog_signature: str | None = Header(default=None, alias="Saylog-Signature"),
    ) -> dict[str, bool]:
        secret = state.settings.webhook_secret.get_secret_value()
        body = await request.body()
        if saylog_signature is None or not secret:
            raise HTTPException(401, "Missing signature or secret not configured")
        if not verify_signature(secret=secret, payload=body, header=saylog_signature):
            raise HTTPException(401, "Invalid signature")

        try:
            event = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, "Invalid JSON") from exc

        if event.get("event") == "records.summarized":
            record_id = event.get("data", {}).get("recordId")
            if record_id:
                background.add_task(_process_record, record_id)

        return {"ok": True}

    return router


async def _process_record(record_id: str) -> None:
    logger.info("[webhook] records.summarized: %s", record_id)
