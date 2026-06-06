import argparse
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
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


@dataclass
class MetricSample:
    collected_at: str
    error_rate: float
    p95_latency_ms: float
    degraded: bool


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

    value = float(results[0]["value"][1])
    return 0.0 if math.isnan(value) else value


def build_report(
    samples: list[MetricSample],
    verdict: str,
    reason: str,
    error_rate_threshold: float,
    p95_latency_threshold_ms: float,
) -> str:
    lines = [
        "# SmartDeploy Release Report",
        "",
        f"- Verdict: `{verdict}`",
        f"- Reason: {reason}",
        f"- Error rate threshold: `{error_rate_threshold:.2%}`",
        f"- p95 latency threshold: `{p95_latency_threshold_ms:.0f}ms`",
        "",
        "## Samples",
        "",
        "| Time UTC | Error Rate | p95 Latency | State |",
        "| --- | ---: | ---: | --- |",
    ]

    for sample in samples:
        state = "degraded" if sample.degraded else "healthy"
        lines.append(
            f"| {sample.collected_at} | {sample.error_rate:.2%} | "
            f"{sample.p95_latency_ms:.0f}ms | {state} |"
        )

    return "\n".join(lines) + "\n"


def write_report(path: str | None, report: str) -> None:
    if not path:
        return

    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


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
    parser.add_argument("--consecutive-failures", type=int, default=2)
    parser.add_argument("--report-file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    deadline = time.time() + args.watch_seconds
    samples: list[MetricSample] = []
    degraded_streak = 0

    while time.time() < deadline:
        error_rate = prometheus_query(args.prometheus_url, ERROR_RATE_QUERY)
        p95_latency_ms = prometheus_query(args.prometheus_url, P95_LATENCY_QUERY) * 1000
        degraded = (
            error_rate > args.error_rate_threshold
            or p95_latency_ms > args.p95_latency_threshold_ms
        )

        samples.append(
            MetricSample(
                collected_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                error_rate=error_rate,
                p95_latency_ms=p95_latency_ms,
                degraded=degraded,
            )
        )
        degraded_streak = degraded_streak + 1 if degraded else 0

        print(
            f"release health: error_rate={error_rate:.2%}, "
            f"p95_latency_ms={p95_latency_ms:.0f}, "
            f"degraded_streak={degraded_streak}/{args.consecutive_failures}"
        )

        if degraded_streak >= args.consecutive_failures:
            reason = "release exceeded thresholds for consecutive samples"
            report = build_report(
                samples=samples,
                verdict="rollback",
                reason=reason,
                error_rate_threshold=args.error_rate_threshold,
                p95_latency_threshold_ms=args.p95_latency_threshold_ms,
            )
            write_report(args.report_file, report)
            print("release degraded: rollback required")
            if not args.dry_run:
                rollback(args.namespace, args.deployment)
            return 2

        time.sleep(args.interval_seconds)

    report = build_report(
        samples=samples,
        verdict="healthy",
        reason="release stayed within thresholds during the watch window",
        error_rate_threshold=args.error_rate_threshold,
        p95_latency_threshold_ms=args.p95_latency_threshold_ms,
    )
    write_report(args.report_file, report)
    print("release healthy: no rollback required")
    return 0


if __name__ == "__main__":
    sys.exit(main())
