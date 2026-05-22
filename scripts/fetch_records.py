"""새록 기록 조회.

사용법:
    uv run python scripts/fetch_records.py
    uv run python scripts/fetch_records.py --record-id rec_xyz789
"""
from __future__ import annotations

import argparse
import asyncio
import json

from scripts._common import connect_client, load_settings


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-id", help="단건 조회할 기록 ID")
    parser.add_argument("--since", help="ISO 8601 시작 시각 필터")
    parser.add_argument("--employee-id", help="녹음 의료진 사번 필터")
    parser.add_argument("--patient-uid", help="환자 식별자 필터")
    parser.add_argument(
        "--limit", type=int,
        help="반환할 최대 기록 수 (1~100, 기본 50)",
    )
    args = parser.parse_args()

    settings = load_settings()
    async with connect_client(settings) as client:
        if args.record_id:
            detail = await client.get_record(args.record_id)
            print(json.dumps(detail.model_dump(by_alias=True), indent=2, ensure_ascii=False))
            return

        records = await client.list_records(
            since=args.since,
            employee_id=args.employee_id,
            patient_uid=args.patient_uid,
            limit=args.limit,
        )
        for r in records:
            tldr = f" — {r.tldr}" if r.tldr else ""
            print(f"[{r.created_at}] {r.record_id} ({r.patient_name}){tldr}")


if __name__ == "__main__":
    asyncio.run(main())
