from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli import create_admin
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import Order, ProductProductionProfile
from app.orders import seed_mock_orders
from app.rbac import seed_rbac


def setup_app(tmp_path):
    app = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'profiles.db'}"))
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as db:
        seed_rbac(db)
        db.commit()
        create_admin("admin", "Admin", "admin-password-123", db)
        seed_mock_orders(db)
    return app


def login(client, username="admin", password="admin-password-123"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


def test_profile_admin_crud_and_order_normative_match(tmp_path):
    app = setup_app(tmp_path)
    with Session(app.state.engine) as db:
        order = db.scalar(select(Order).where(Order.internal_status == "QUEUED"))
        order.items[0].offer_id = "chair-offer"
        order.items[0].sku = "chair-sku"
        db.commit()
    with TestClient(app) as client:
        headers = login(client)
        payload = {"offer_id": "chair-offer", "sku": "chair-sku", "product_name": "Стул",
                   "production_minutes": 45, "packing_minutes": 8, "complexity": "HIGH",
                   "production_group": "Столярка"}
        created = client.post("/api/product-profiles", headers=headers, json=payload)
        assert created.status_code == 201
        profile_id = created.json()["id"]
        order_items = [item for order in client.get("/api/orders?limit=100").json()["items"] for item in order["items"]]
        matched = next(item for item in order_items if item["offer_id"] == "chair-offer")
        assert matched["production_profile"]["production_minutes"] == 45
        assert matched["production_profile"]["production_group"] == "Столярка"
        updated = {**payload, "production_minutes": 50}
        assert client.put(f"/api/product-profiles/{profile_id}", headers=headers, json=updated).json()["production_minutes"] == 50
        assert client.post("/api/product-profiles", headers=headers, json=payload).status_code == 409
        assert client.delete(f"/api/product-profiles/{profile_id}", headers=headers).status_code == 204
        order_items = [item for order in client.get("/api/orders?limit=100").json()["items"] for item in order["items"]]
        assert next(item for item in order_items if item["offer_id"] == "chair-offer")["production_profile"] is None
        assert client.post("/api/product-profiles", headers=headers, json={**payload, "offer_id": None, "sku": None}).status_code == 422


def test_profile_access_requires_admin_permission_and_sku_fallback(tmp_path):
    app = setup_app(tmp_path)
    with TestClient(app) as admin:
        admin_headers = login(admin)
        admin.post("/api/users", headers=admin_headers, json={"username": "viewer", "display_name": "Viewer",
                    "password": "viewer-password-123", "roles": ["VIEWER"]})
        viewer = TestClient(app)
        viewer_headers = login(viewer, "viewer", "viewer-password-123")
        assert viewer.get("/api/product-profiles").status_code == 403
        assert viewer.post("/api/product-profiles", headers=viewer_headers, json={}).status_code == 403
        with Session(app.state.engine) as db:
            order = db.scalar(select(Order).where(Order.internal_status == "QUEUED"))
            order.items[0].sku = "sku-only"
            db.add(ProductProductionProfile(sku="sku-only", product_name="Стол", production_minutes=30,
                                            packing_minutes=5, complexity="MEDIUM"))
            db.commit()
        order_items = [item for order in admin.get("/api/orders?limit=100").json()["items"] for item in order["items"]]
        data = next(item for item in order_items if item["sku"] == "sku-only")
        assert data["production_profile"]["packing_minutes"] == 5


def test_order_without_profile_remains_available(tmp_path):
    app = setup_app(tmp_path)
    with TestClient(app) as client:
        login(client)
        result = client.get("/api/orders?limit=100")
        assert result.status_code == 200
        assert all(item["production_profile"] is None for order in result.json()["items"] for item in order["items"])
