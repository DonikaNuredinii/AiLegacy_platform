import asyncio
import time
import statistics
from dataclasses import dataclass
import httpx

BASE_URL = "http://localhost:8000"
ENDPOINT = "/api/v1/ai/analyze"  
TOTAL_REQUESTS = 100
CONCURRENCY = 5
DELAY_BETWEEN_REQUESTS_SEC = 0.2  

LOGIN_USER = "admin"
LOGIN_PASS = "admin123"

TOKEN = ""


@dataclass
class Result:
    status: int
    ms: float
    err: str | None = None


def percentile(data, p):
    if not data:
        return None
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(data_sorted) - 1)
    if f == c:
        return data_sorted[f]
    return data_sorted[f] + (data_sorted[c] - data_sorted[f]) * (k - f)


async def worker(client: httpx.AsyncClient, sem: asyncio.Semaphore, idx: int):
    async with sem:
        headers = {"Authorization": f"Bearer {TOKEN}"}
        payload = {
            "title": "VPN down",
            "description": "VPN not connecting",
            "department": "it",
        }

        if DELAY_BETWEEN_REQUESTS_SEC > 0:
            await asyncio.sleep(DELAY_BETWEEN_REQUESTS_SEC)

        start = time.perf_counter()
        try:
            r = await client.post(f"{BASE_URL}{ENDPOINT}", json=payload, headers=headers)
            ms = (time.perf_counter() - start) * 1000
            return Result(status=r.status_code, ms=ms, err=None)
        except Exception as e:
            ms = (time.perf_counter() - start) * 1000
            return Result(status=0, ms=ms, err=repr(e))


async def main():
    global TOKEN

    sem = asyncio.Semaphore(CONCURRENCY)
    timeout = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=5.0)

    test_start = time.perf_counter()

    async with httpx.AsyncClient(timeout=timeout) as client:
        login_resp = await client.post(
            f"{BASE_URL}/auth/login",
            json={"username": LOGIN_USER, "password": LOGIN_PASS},
        )
        login_resp.raise_for_status()
        TOKEN = login_resp.json()["access_token"]

        tasks = [asyncio.create_task(worker(client, sem, i)) for i in range(TOTAL_REQUESTS)]
        results = await asyncio.gather(*tasks)

    test_seconds = time.perf_counter() - test_start

    statuses = {}
    for r in results:
        statuses[r.status] = statuses.get(r.status, 0) + 1
    print("\nStatus counts:", statuses)

    error_count = sum(v for k, v in statuses.items() if k != 200)
    error_rate = (error_count / TOTAL_REQUESTS) * 100
    print("Error rate (%):", round(error_rate, 2))

    transport_errors = [r for r in results if r.status == 0]
    if transport_errors:
        print("\nSample transport errors (first 5):")
        for e in transport_errors[:5]:
            print(" -", e.err)

    times = [r.ms for r in results]
    print(
        "\nLatency (ms): avg =",
        round(statistics.mean(times), 2),
        "min =",
        round(min(times), 2),
        "max =",
        round(max(times), 2),
        "p95 =",
        round(percentile(times, 95), 2),
        "p99 =",
        round(percentile(times, 99), 2),
    )

    # Throughput (requests/sec) based on total test duration
    throughput = TOTAL_REQUESTS / test_seconds
    print("\nTotal test time (s):", round(test_seconds, 3))
    print("Throughput (req/sec):", round(throughput, 2))


if __name__ == "__main__":
    asyncio.run(main())