import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.dependencies import AppState
from app.webhook.signature import verify_signature

logger = logging.getLogger(__name__)

# 새록 공식 가이드 권장값: 수신 시각과의 차이가 300초(5분)를 넘는 이벤트는 폐기
FRESHNESS_TOLERANCE_SECONDS = 300


def build_webhook_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.post("/webhook/saylog")
    async def receive(
        request: Request,
        background: BackgroundTasks,
        saylog_signature: str | None = Header(default=None, alias="Saylog-Signature"),
        saylog_timestamp: str | None = Header(default=None, alias="X-Saylog-Timestamp"),
    ) -> dict[str, bool]:
        secret = state.settings.webhook_secret.get_secret_value()
        if not secret:
            # 서버 설정 누락은 호출자의 인증 실패(401)가 아니라 서버 오류다
            logger.error("[webhook] WEBHOOK_SECRET not configured")
            raise HTTPException(500, "Webhook secret not configured")

        body = await request.body()
        if saylog_signature is None or saylog_timestamp is None:
            logger.warning("[webhook] rejected: missing signature or timestamp header")
            raise HTTPException(401, "Missing signature or timestamp header")
        if not verify_signature(
            secret=secret,
            timestamp=saylog_timestamp,
            payload=body,
            header=saylog_signature,
        ):
            logger.warning("[webhook] rejected: signature mismatch")
            raise HTTPException(401, "Invalid signature")

        # replay 방어: 서명 검증을 통과한 timestamp만 신뢰하고 신선도를 확인한다
        try:
            ts = int(saylog_timestamp)
        except ValueError:
            logger.warning("[webhook] rejected: non-numeric timestamp")
            raise HTTPException(401, "Invalid timestamp") from None
        if abs(time.time() - ts) > FRESHNESS_TOLERANCE_SECONDS:
            logger.warning("[webhook] rejected: stale timestamp")
            raise HTTPException(401, "Stale timestamp")

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
