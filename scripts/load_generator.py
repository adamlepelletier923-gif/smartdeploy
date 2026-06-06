import argparse
import random
import time
from dataclasses import dataclass

import requests


@dataclass
class LoadResult:
    total_requests: int
    successful_requests: int
    failed_requests: int
    p95_latency_ms: float

    @property
    def error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = min(round((percent / 100) * (len(ordered) - 1)), len(ordered) - 1)
    return ordered[index]


def run_load(base_url: str, duration_seconds: int, rate_per_second: float, jitter: float) -> LoadResult:
    endpoint = f"{base_url.rstrip('/')}/api/orders"
    deadline = time.time() + duration_seconds
    interval = 1 / rate_per_second
    latencies_ms: list[float] = []
    total = 0
    failures = 0

    while time.time() < deadline:
        started_at = time.time()
        total += 1

        try:
            response = requests.get(endpoint, timeout=5)
            if response.status_code >= 500:
                failures += 1
        except requests.RequestException:
            failures += 1

        latencies_ms.append((time.time() - started_at) * 1000)
        sleep_for = max(interval + random.uniform(-jitter, jitter), 0)
        time.sleep(sleep_for)

    return LoadResult(
        total_requests=total,
        successful_requests=total - failures,
        failed_requests=failures,
        p95_latency_ms=percentile(latencies_ms, 95),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate demo traffic against the SmartDeploy API.")
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--rate-per-second", type=float, default=3)
    parser.add_argument("--jitter", type=float, default=0.05)
    parser.add_argument("--fail-on-errors", action="store_true")
    args = parser.parse_args()

    result = run_load(args.base_url, args.duration_seconds, args.rate_per_second, args.jitter)

    print("load test complete")
    print(f"requests_total={result.total_requests}")
    print(f"requests_success={result.successful_requests}")
    print(f"requests_failed={result.failed_requests}")
    print(f"error_rate={result.error_rate:.2%}")
    print(f"p95_latency_ms={result.p95_latency_ms:.0f}")

    return 1 if args.fail_on_errors and result.failed_requests > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
