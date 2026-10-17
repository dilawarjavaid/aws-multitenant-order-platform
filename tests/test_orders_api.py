from fastapi.testclient import TestClient

from app.main import app


TENANT_ID = "11111111-1111-4111-8111-111111111111"
VALID_ORDER = {
    "items": [
        {
            "product_id": "b8f00bc2-b494-4c02-8cad-7ad0f3336290",
            "quantity": 2,
        }
    ]
}


def test_order_endpoint_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_DEV_ORDER_API", raising=False)

    with TestClient(app) as client:
        response = client.post(
            "/orders",
            headers={"X-Tenant-ID": TENANT_ID},
            json=VALID_ORDER,
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


def test_order_endpoint_rejects_empty_items(monkeypatch):
    monkeypatch.setenv("ENABLE_DEV_ORDER_API", "true")

    with TestClient(app) as client:
        response = client.post(
            "/orders",
            headers={"X-Tenant-ID": TENANT_ID},
            json={"items": []},
        )

    assert response.status_code == 422


def test_order_endpoint_requires_tenant_header(monkeypatch):
    monkeypatch.setenv("ENABLE_DEV_ORDER_API", "true")

    with TestClient(app) as client:
        response = client.post("/orders", json=VALID_ORDER)

    assert response.status_code == 422

def test_get_order_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_DEV_ORDER_API", raising=False)

    with TestClient(app) as client:
        response = client.get(
            "/orders/b1d4e478-4bac-4ea4-949e-c095eb32ade8",
            headers={"X-Tenant-ID": TENANT_ID},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}


def test_get_order_requires_tenant_header(monkeypatch):
    monkeypatch.setenv("ENABLE_DEV_ORDER_API", "true")

    with TestClient(app) as client:
        response = client.get(
            "/orders/b1d4e478-4bac-4ea4-949e-c095eb32ade8"
        )

    assert response.status_code == 422


def test_get_order_rejects_invalid_order_id(monkeypatch):
    monkeypatch.setenv("ENABLE_DEV_ORDER_API", "true")

    with TestClient(app) as client:
        response = client.get(
            "/orders/not-a-uuid",
            headers={"X-Tenant-ID": TENANT_ID},
        )

    assert response.status_code == 422