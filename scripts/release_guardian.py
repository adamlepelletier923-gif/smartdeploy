import argparse
import subprocess
import sys
import time
from urllib.parse import urlencode

import requests


ERROR_RATE_QUERY = """
sum(rate(smartdeploy_http_requests_total{endpoint="/api/orders",status=~"5.."}[2m]))
/
sum(rate(smartdeploy_http_requests_total{endpoint="/api/orders"}[2m]))
"""

P95_LATENCY_QUERY = """
histogram_quantile(
  0.95,
  sum(rate(smartdeploy_http_request_duration_seconds_bucket{endpoint="/api/orders"}[2m])) by (le)
)
"""


def prometheus_query(base_url: str, query: str) -> float:
    url = f"{base_url.rstrip('/')}/api/v1/query?{urlencode({'query': query})}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus query failed: {payload}")

    results = payload["data"]["result"]
    if not results:
        return 0.0

    return float(results[0]["value"][1])


def rollback(namespace: str, deployment: str) -> None:
    command = ["kubectl", "rollout", "undo", "-n", namespace, f"deployment/{deployment}"]
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch release metrics and roll back degraded deployments.")
    parser.add_argument("--namespace", default="smartdeploy")
    parser.add_argument("--deployment", default="smartdeploy-api")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--error-rate-threshold", type=float, default=0.05)
    parser.add_argument("--p95-latency-threshold-ms", type=float, default=500)
    parser.add_argument("--watch-seconds", type=int, default=180)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    deadline = time.time() + args.watch_seconds
    while time.time() < deadline:
        error_rate = prometheus_query(args.prometheus_url, ERROR_RATE_QUERY)
        p95_latency_ms = prometheus_query(args.prometheus_url, P95_LATENCY_QUERY) * 1000

        print(
            f"release health: error_rate={error_rate:.2%}, "
            f"p95_latency_ms={p95_latency_ms:.0f}"
        )

        if error_rate > args.error_rate_threshold or p95_latency_ms > args.p95_latency_threshold_ms:
            print("release degraded: rollback required")
            if not args.dry_run:
                rollback(args.namespace, args.deployment)
            return 2

        time.sleep(args.interval_seconds)

    print("release healthy: no rollback required")
    return 0


if __name__ == "__main__":
    sys.exit(main())
