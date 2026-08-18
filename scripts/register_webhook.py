"""새록 웹훅 등록.

사용법:
    uv run python scripts/register_webhook.py
    uv run python scripts/register_webhook.py --url https://my-public-host/webhook/saylog
    uv run python scripts/register_webhook.py --event records.updated

등록은 이벤트 단위이며 등록 건마다 별도 secret이 발급됩니다 — 여러 이벤트를
구독하려면 이벤트별로 실행하고, 발급된 secret들을 .env의 WEBHOOK_SECRETS에
콤마로 이어 붙여 저장하세요.
"""
from __future__ import annotations

import argparse
import asyncio

from scripts._common import connect_client, load_settings

WEBHOOK_EVENTS = [
    "records.summarized",
    "records.transcribed",
    "records.updated",
    "records.deleted",
]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        help="웹훅 수신 URL (기본: PUBLIC_BASE_URL/webhook/saylog)",
    )
    parser.add_argument(
        "--event",
        choices=WEBHOOK_EVENTS,
        default="records.summarized",
        help="구독할 이벤트 (기본: records.summarized)",
    )
    args = parser.parse_args()

    settings = load_settings()
    url = args.url or f"{settings.public_base_url.rstrip('/')}/webhook/saylog"

    async with connect_client(settings) as client:
        result = await client.register_webhook(url=url, event=args.event)

    print("✓ Webhook 등록 완료")
    print(f"  webhookId: {result.webhook_id}")
    print(f"  url:       {result.url}")
    print(f"  event:     {result.event}")
    print(f"  secret:    {result.secret}")
    print()
    print("⚠ 이 secret은 다시 조회할 수 없습니다.")
    print("  .env의 WEBHOOK_SECRETS에 콤마로 이어 붙여 저장하세요")
    print("  (등록 건마다 secret이 다릅니다. 단일 값이면 WEBHOOK_SECRET도 동작).")


if __name__ == "__main__":
    asyncio.run(main())
