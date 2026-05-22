"""새록 웹훅 등록.

사용법:
    uv run python scripts/register_webhook.py
    uv run python scripts/register_webhook.py --url https://my-public-host/webhook/saylog
"""
from __future__ import annotations

import argparse
import asyncio

from scripts._common import connect_client, load_settings


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        help="웹훅 수신 URL (기본: PUBLIC_BASE_URL/webhook/saylog)",
    )
    args = parser.parse_args()

    settings = load_settings()
    url = args.url or f"{settings.public_base_url.rstrip('/')}/webhook/saylog"

    async with connect_client(settings) as client:
        result = await client.register_webhook(url=url)

    print("✓ Webhook 등록 완료")
    print(f"  webhookId: {result.webhook_id}")
    print(f"  url:       {result.url}")
    print(f"  event:     {result.event}")
    print(f"  secret:    {result.secret}")
    print()
    print("⚠ 이 secret은 다시 조회할 수 없습니다.")
    print("  .env의 WEBHOOK_SECRET 값으로 저장하세요.")


if __name__ == "__main__":
    asyncio.run(main())
