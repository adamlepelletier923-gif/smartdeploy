from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check_is_ready():
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_orders_endpoint_returns_demo_orders():
    response = client.get("/api/orders")

    assert response.status_code == 200
    assert len(response.json()["orders"]) == 2


def test_metrics_are_exposed():
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "smartdeploy_http_requests_total" in response.text
