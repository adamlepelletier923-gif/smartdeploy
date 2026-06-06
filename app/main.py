import os
import random
import time

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


APP_VERSION = os.getenv("APP_VERSION", "dev")
ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))
EXTRA_LATENCY_MS = int(os.getenv("EXTRA_LATENCY_MS", "0"))

app = FastAPI(title="SmartDeploy API", version=APP_VERSION)

REQUEST_COUNT = Counter(
    "smartdeploy_http_requests_total",
    "Total HTTP requests handled by SmartDeploy",
    ["endpoint", "method", "status"],
)

REQUEST_LATENCY = Histogram(
    "smartdeploy_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint", "method"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 2, 5),
)


def observe(endpoint: str, method: str, status: int, started_at: float) -> None:
    REQUEST_COUNT.labels(endpoint=endpoint, method=method, status=str(status)).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint, method=method).observe(time.time() - started_at)


@app.get("/")
def root():
    started_at = time.time()
    status = 200
    try:
        return {
            "service": "smartdeploy-api",
            "version": APP_VERSION,
            "status": "ready",
            "faults": {
                "error_rate": ERROR_RATE,
                "extra_latency_ms": EXTRA_LATENCY_MS,
            },
        }
    finally:
        observe("/", "GET", status, started_at)


@app.get("/healthz")
def healthz():
    started_at = time.time()
    status = 200
    try:
        return {"ok": True, "version": APP_VERSION}
    finally:
        observe("/healthz", "GET", status, started_at)


@app.get("/api/orders")
def list_orders():
    started_at = time.time()
    status = 200

    if EXTRA_LATENCY_MS > 0:
        time.sleep(EXTRA_LATENCY_MS / 1000)

    try:
        if random.random() < ERROR_RATE:
            status = 500
            raise HTTPException(status_code=500, detail="Injected release failure")

        return {
            "orders": [
                {"id": "ord_1001", "total": 79.9, "currency": "EUR"},
                {"id": "ord_1002", "total": 129.0, "currency": "EUR"},
            ],
            "version": APP_VERSION,
        }
    finally:
        observe("/api/orders", "GET", status, started_at)


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
