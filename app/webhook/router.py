import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.dependencies import AppState
from app.webhook.signature import verify_signature

logger = logging.getLogger(__name__)

# 새록 공식 가이드 권장값: 수신 시각과의 차이가 300초(5분)를 넘는 이벤트는 폐기
FRESHNESS_TOLERANCE_SECONDS = 300

# 새록이 발송하는 웹훅 이벤트 4종.
# 이 목록에 없는 이벤트가 와도 2xx로 응답하고 무시한다(forward-compat) —
# 새록이 이벤트를 추가해도 파트너 수신부가 깨지지 않게 하기 위한 계약이다.
KNOWN_EVENTS = frozenset(
    {
        "records.summarized",
        "records.transcribed",
        "records.updated",
        "records.deleted",
    }
)


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

        event_name = event.get("event")
        # data 안의 미지 필드는 검증하지 않고 통과시킨다(forward-compat) —
        # 필요한 필드만 꺼내 쓰고 나머지는 무시한다.
        data = event.get("data") or {}
        record_id = data.get("recordId") if isinstance(data, dict) else None
        source = data.get("source", "unknown") if isinstance(data, dict) else "unknown"

        if event_name in KNOWN_EVENTS:
            if record_id:
                background.add_task(_process_event, event_name, record_id, source)
        else:
            # 미지 이벤트: 재시도를 유발하지 않도록 2xx로 응답하고 무시한다
            logger.info("[webhook] ignored unknown event: %s", event_name)

        return {"ok": True}

    return router


async def _process_event(event_name: str, record_id: str, source: str) -> None:
    """이벤트별 후속 동작 예시 — 실제 파트너 구현에서는 자사 시스템을 갱신한다.

    source는 기록 유입 경로(connect-api | saylog-mobile | saylog-watch | unknown)로,
    파트너가 자기 API로 올린 기록(connect-api)을 걸러내는 용도 등에 쓸 수 있다.
    """
    if event_name == "records.summarized":
        # AI 요약 완료 — 기록 단건 조회 API로 상세를 가져와 저장한다
        logger.info("[webhook] records.summarized: %s (source=%s)", record_id, source)
    elif event_name == "records.transcribed":
        # 서버 전사 완료 — transcripts:read scope가 있으면 전사 조회 API로 원문 조회 가능
        logger.info("[webhook] records.transcribed: %s (source=%s)", record_id, source)
    elif event_name == "records.updated":
        # 요약 편집·재생성 — recordId 멱등 캐시만으로 스킵하면 갱신이 유실되므로
        # 이 이벤트는 반드시 다시 조회해 로컬 사본을 갱신한다
        logger.info("[webhook] records.updated: %s (source=%s)", record_id, source)
    elif event_name == "records.deleted":
        # 기록 삭제·연결 해제 — 로컬 사본을 삭제한다.
        # 이 이벤트 수신 후 단건 조회가 404를 반환하는 것은 정상이다.
        logger.info("[webhook] records.deleted: %s (source=%s)", record_id, source)
