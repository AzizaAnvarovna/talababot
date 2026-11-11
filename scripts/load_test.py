"""NFR-1, NFR-2 yuklama testi. Faqat sinov serverida ishlating, haqiqiy loglarga yozmang.

python scripts/load_test.py --base http://127.0.0.1:8000 --users 50
"""

import argparse
import asyncio
import random
import time
from statistics import median
from uuid import uuid4

import httpx

QUESTIONS = (
    "stipendiya haqida 3 savol",
    "yotoqxona boyicha 7 malumot kerak",
    "dars jadvali qayerda",
    "ariza qanday yoziladi",
    "akademik tatil olish",
    "kutubxona ishlaydimi",
)


async def _post(client: httpx.AsyncClient, body: dict, log: list, errors: list) -> None:
    started = time.perf_counter()
    try:
        response = await client.post("/api/chat/message", json=body)
        response.raise_for_status()
    except httpx.HTTPError as error:
        errors.append(type(error).__name__)
        return
    log.append((time.perf_counter() - started) * 1000)


async def _user(client, messages: int, think: float, log: list, errors: list) -> None:
    user_id = uuid4().hex
    base = {"channel": "web", "user_id": user_id}
    await _post(client, base | {"action": "consent_yes"}, [], errors)
    for _ in range(messages):
        await asyncio.sleep(random.uniform(0, think * 2))
        await _post(client, base | {"text": random.choice(QUESTIONS)}, log, errors)


async def _run(base: str, users: int, messages: int, think: float) -> tuple[list, list, float]:
    log: list[float] = []
    errors: list[str] = []
    limits = httpx.Limits(max_connections=users + 10)
    async with httpx.AsyncClient(base_url=base, timeout=60, limits=limits) as client:
        started = time.perf_counter()
        await asyncio.gather(*(_user(client, messages, think, log, errors) for _ in range(users)))
    return log, errors, time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--messages", type=int, default=10)
    parser.add_argument(
        "--think", type=float, default=3.0, help="xabarlar orasidagi oʻrtacha pauza"
    )
    args = parser.parse_args()

    log, errors, elapsed = asyncio.run(_run(args.base, args.users, args.messages, args.think))
    log.sort()
    print(
        f"foydalanuvchilar={args.users} pauza={args.think}s soʻrovlar={len(log)} xato={len(errors)}"
    )
    if log:
        p95 = log[min(len(log) - 1, int(len(log) * 0.95))]
        timing = f"mediana={median(log):.0f} ms p95={p95:.0f} ms maks={log[-1]:.0f} ms"
        print(f"{timing} vaqt={elapsed:.0f}s")


if __name__ == "__main__":
    main()
