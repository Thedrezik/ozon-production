import re
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, BlockerType, Photo, User
from app.orders import seed_mock_orders
from app.storage import LocalStorage, Storage
from tests.test_orders import login, setup_app


def image_bytes():
    output = BytesIO()
    Image.new("RGB", (2000, 1000), "red").save(output, format="PNG")
    return output.getvalue()


@pytest.fixture
def context(tmp_path):
    app = setup_app(tmp_path)
    app.state.storage = LocalStorage(str(tmp_path / "uploads"))
    with Session(app.state.engine) as db:
        seed_mock_orders(db)
        db.add(BlockerType(code="OTHER", display_name="Other"))
        db.commit()
    with TestClient(app) as client:
        headers = login(client)
        order = client.get("/api/orders?status=QUEUED").json()["items"][0]
        yield app, client, headers, order


def test_upload_compression_metadata_and_filename(context):
    app, client, headers, order = context
    response = client.post(f"/api/files/orders/{order['id']}/photos", content=image_bytes(),
                           headers={**headers, "Content-Type": "image/png", "X-Filename": "../../evil.png"})
    assert response.status_code == 201
    photo = response.json()
    assert (photo["width"], photo["height"]) == (1600, 800)
    saved = client.get(photo["url"])
    assert saved.status_code == 200
    assert saved.headers["cache-control"] == "private, no-store"
    with Image.open(BytesIO(saved.content)) as image:
        assert image.format == "JPEG"
        assert not image.getexif()
    with Session(app.state.engine) as db:
        row = db.get(Photo, photo["id"])
        assert re.fullmatch(r"[0-9a-f]{32}\.jpg", row.storage_key)
        assert row.size_bytes == len(saved.content)
        assert db.scalar(select(AuditLog.id).where(AuditLog.action == "photo.uploaded"))
    assert client.delete(photo["url"], headers=headers).status_code == 405


@pytest.mark.parametrize("mime,content", [("image/svg+xml", b"<svg/>"), ("image/png", b"invalid"), ("image/jpeg", image_bytes())])
def test_unsupported_or_forged_type(context, mime, content):
    app, client, headers, order = context
    assert client.post(f"/api/files/orders/{order['id']}/photos", content=content,
                       headers={**headers, "Content-Type": mime}).status_code == 415
    assert not app.state.storage.root.exists()


def test_stream_size_limit(context):
    app, client, headers, order = context
    app.state.settings.upload_max_bytes = 1024
    assert client.post(f"/api/files/orders/{order['id']}/photos", content=b"a" * 1025,
                       headers={**headers, "Content-Type": "image/png"}).status_code == 413
    assert not app.state.storage.root.exists()


def test_blocker_and_comment_targets(context):
    _app, client, headers, order = context
    blocker = client.post("/api/blockers", headers=headers, json={"order_id": order["id"],
                        "type_code": "OTHER", "description": "Problem"}).json()
    comment = client.post(f"/api/orders/{order['id']}/comments", headers=headers, json={"body": "Comment"}).json()
    for query in (f"blocker_id={blocker['id']}", f"comment_id={comment['id']}"):
        response = client.post(f"/api/files/orders/{order['id']}/photos?{query}", content=image_bytes(),
                               headers={**headers, "Content-Type": "image/png"})
        assert response.status_code == 201
    photos = client.get(f"/api/blockers?order_id={order['id']}").json()["items"][0]["photos"]
    assert len(photos) == 1
    scoped = client.get(f"/api/files/orders/{order['id']}/photos?target_only=true&blocker_id={blocker['id']}").json()
    assert len(scoped["items"]) == 1
    assert scoped["items"][0]["blocker_id"] == blocker["id"]
    other = next(row["id"] for row in client.get("/api/orders").json()["items"] if row["id"] != order["id"])
    assert client.post(f"/api/files/orders/{other}/photos?blocker_id={blocker['id']}", content=image_bytes(),
                       headers={**headers, "Content-Type": "image/png"}).status_code == 404


def test_permissions_and_csrf(context):
    app, client, headers, order = context
    url = f"/api/files/orders/{order['id']}/photos"
    photo = client.post(url, content=image_bytes(), headers={**headers, "Content-Type": "image/png"}).json()
    assert client.post(url, content=image_bytes(), headers={"Content-Type": "image/png"}).status_code == 403
    client.post("/api/users", headers=headers, json={"username": "viewer", "display_name": "Viewer",
                "password": "viewer-password-123", "roles": ["VIEWER"]})
    with TestClient(app) as viewer:
        vh = login(viewer, "viewer", "viewer-password-123")
        assert viewer.get(photo["url"]).status_code == 200
        assert viewer.post(url, content=image_bytes(), headers={**vh, "Content-Type": "image/png"}).status_code == 403
    client.post("/api/users", headers=headers, json={"username": "none", "display_name": "None",
                "password": "none-password-123", "roles": ["VIEWER"]})
    with Session(app.state.engine) as db:
        db.scalar(select(User).where(User.username == "none")).roles = []
        db.commit()
    with TestClient(app) as denied:
        dh = login(denied, "none", "none-password-123")
        assert denied.get(photo["url"]).status_code == 403
        assert denied.get(f"/api/files/orders/{order['id']}/qr").status_code == 403
        assert denied.get("/api/files/resolve", params={"payload": order["posting_number"]}).status_code == 403
        assert denied.post(url, content=image_bytes(), headers={**dh, "Content-Type": "image/png"}).status_code == 403
    with TestClient(app) as anonymous:
        assert anonymous.get(photo["url"]).status_code == 401


def test_qr_and_exact_payload_lookup(context):
    _app, client, _headers, order = context
    qr = client.get(f"/api/files/orders/{order['id']}/qr")
    assert qr.status_code == 200
    assert qr.content.startswith(b"\x89PNG")
    for payload in (order["posting_number"], f"ozon-production:posting:{order['posting_number']}"):
        result = client.get("/api/files/resolve", params={"payload": payload})
        assert result.json()["order_id"] == order["id"]
        assert result.json()["url"] == f"/orders/{order['id']}"
    assert client.get("/api/files/resolve", params={"payload": "https://evil.example/"}).status_code == 404


def test_storage_boundary_and_traversal(tmp_path):
    storage: Storage = LocalStorage(str(tmp_path / "uploads"))
    key = storage.put(b"test")
    assert storage.read(key) == b"test"
    assert LocalStorage(str(tmp_path / "uploads")).read(key) == b"test"
    for invalid in ("../evil.jpg", "/etc/passwd", "a.jpg", "..\\evil.jpg"):
        with pytest.raises(ValueError):
            storage.read(invalid)
    storage.delete(key)
    assert not (tmp_path / "uploads" / key).exists()


def test_alternate_storage_and_commit_cleanup(context, monkeypatch):
    app, client, headers, order = context
    class MemoryStorage:
        def __init__(self):
            self.items = {}
            self.counter = 0
        def put(self, content):
            self.counter += 1
            key = f"opaque{self.counter}"
            self.items[key] = content
            return key
        def read(self, key):
            return self.items[key]
        def delete(self, key):
            del self.items[key]
    storage = MemoryStorage()
    app.state.storage = storage
    url = f"/api/files/orders/{order['id']}/photos"
    photo = client.post(url, content=image_bytes(), headers={**headers, "Content-Type": "image/png"}).json()
    assert client.get(photo["url"]).content == storage.items["opaque1"]
    storage.items.clear()
    def fail(_self):
        raise RuntimeError("commit failed")
    monkeypatch.setattr(Session, "commit", fail)
    with pytest.raises(RuntimeError):
        client.post(url, content=image_bytes(), headers={**headers, "Content-Type": "image/png"})
    assert storage.items == {}
