"""测试分组-渠道管理和用户-分组管理 API。"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

_AG = Path(__file__).parent.parent / "any_gateway"
if str(_AG) not in sys.path:
    sys.path.insert(0, str(_AG))

os.environ["ADMIN_KEY"] = "test-admin-secret"
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import asyncio
TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


async def override_session():
    async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    async def _create():
        import db.models  # noqa: F401
        async with TEST_ENGINE.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
    asyncio.run(_create())


@pytest.fixture
def client():
    from db.database import async_session_generator
    from gateway import app
    app.dependency_overrides[async_session_generator] = override_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


HEADERS = {"x-admin-key": "test-admin-secret"}


def create_group(client, name: str) -> dict:
    """创建分组并返回带 id 的分组对象。"""
    client.post("/admin/groups", json={"name": name}, headers=HEADERS)
    resp = client.get("/admin/groups", headers=HEADERS)
    data = resp.json()["data"]
    # 找到名字匹配的分组（最后创建的）
    matches = [g for g in data if g["name"] == name]
    return matches[-1]


def create_channel(client, name: str, base_url: str, api_key: str) -> dict:
    """创建渠道并返回带 id 的渠道对象。"""
    client.post("/admin/channels", json={
        "name": name, "provider": "openai",
        "base_url": base_url, "api_key": api_key,
    }, headers=HEADERS)
    resp = client.get("/admin/channels", headers=HEADERS)
    data = resp.json()["data"]
    matches = [c for c in data if c["name"] == name]
    return matches[-1]


def test_add_channel_to_group(client):
    """POST /admin/groups/{group_id}/channels/{channel_id} 应返回 200。"""
    grp = create_group(client, "g1")
    ch = create_channel(client, "ch1", "http://x/v1", "k")

    resp = client.post(f"/admin/groups/{grp['id']}/channels/{ch['id']}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["group_id"] == grp["id"]


def test_list_group_channels(client):
    """GET /admin/groups/{group_id}/channels 应返回渠道列表。"""
    grp = create_group(client, "g2")
    ch = create_channel(client, "ch2", "http://y/v1", "k2")
    client.post(f"/admin/groups/{grp['id']}/channels/{ch['id']}", headers=HEADERS)

    resp = client.get(f"/admin/groups/{grp['id']}/channels", headers=HEADERS)
    assert resp.status_code == 200
    assert any(c["id"] == ch["id"] for c in resp.json())


def test_remove_channel_from_group(client):
    """DELETE /admin/groups/{group_id}/channels/{channel_id} 应返回 200。"""
    grp = create_group(client, "g3")
    ch = create_channel(client, "ch3", "http://z/v1", "k3")
    client.post(f"/admin/groups/{grp['id']}/channels/{ch['id']}", headers=HEADERS)

    resp = client.delete(f"/admin/groups/{grp['id']}/channels/{ch['id']}", headers=HEADERS)
    assert resp.status_code == 200


def test_list_ad_users(client):
    """GET /admin/users-list 应返回用户列表（初始为空）。"""
    resp = client.get("/admin/users-list", headers=HEADERS)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_add_user_to_group(client):
    """POST /admin/users-list/{username}/groups/{group_id} 应返回 200。"""
    grp = create_group(client, "g4")
    resp = client.post(f"/admin/users-list/testuser/groups/{grp['id']}", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_get_user_groups(client):
    """GET /admin/users-list/{username}/groups 应返回用户的分组列表。"""
    grp = create_group(client, "g5")
    client.post(f"/admin/users-list/testuser2/groups/{grp['id']}", headers=HEADERS)

    resp = client.get("/admin/users-list/testuser2/groups", headers=HEADERS)
    assert resp.status_code == 200
    assert any(g["id"] == grp["id"] for g in resp.json())


def test_remove_user_from_group(client):
    """DELETE /admin/users-list/{username}/groups/{group_id} 应返回 200。"""
    grp = create_group(client, "g6")
    client.post(f"/admin/users-list/testuser3/groups/{grp['id']}", headers=HEADERS)

    resp = client.delete(f"/admin/users-list/testuser3/groups/{grp['id']}", headers=HEADERS)
    assert resp.status_code == 200
