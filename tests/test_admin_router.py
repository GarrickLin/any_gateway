"""
Admin router 单元/集成测试。

使用 FastAPI TestClient（同步）+ SQLite 内存数据库。
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel import SQLModel

# 确保 any_gateway 包路径在 sys.path 中
_REPO_ROOT = Path(__file__).parent.parent
_AG_PATH = _REPO_ROOT / "any_gateway"
if str(_AG_PATH) not in sys.path:
    sys.path.insert(0, str(_AG_PATH))

# 设置测试环境变量（在导入 app 之前）
os.environ["ADMIN_KEY"] = "test-admin-secret"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

# 使用内存数据库引擎覆盖
TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


async def override_session():
    async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
        yield session


# 导入 app 和相关模块
from db.database import init_db
from gateway import app
from admin.router import verify_admin_key, token_router, channel_router, group_router, admin_router

import asyncio


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """创建测试数据库表"""
    async def _create():
        import db.models  # noqa: F401 - 确保所有表注册到 metadata
        async with TEST_ENGINE.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(_create())


@pytest.fixture
def client():
    """提供测试客户端，覆盖 DB 依赖"""
    from db.database import async_session_generator
    app.dependency_overrides[async_session_generator] = override_session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def user_jwt_headers():
    """生成测试用 JWT 头（user 角色，用于 /user/* 端点）"""
    from services.auth_service import create_access_token
    token = create_access_token("test-user", "user")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_jwt_headers():
    """生成测试用 JWT 头（admin 角色，用于 /admin/* 端点）"""
    from services.auth_service import create_access_token
    token = create_access_token("test-admin", "admin")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. 缺少认证 → 422（Authorization Header 必填字段缺失）
# ---------------------------------------------------------------------------

def test_freeze_token_requires_admin_key(client):
    """未提供 Authorization 时，/user/tokens/{id}/freeze 应返回 422"""
    resp = client.patch("/user/tokens/nonexistent/freeze", json={"frozen": True})
    assert resp.status_code in (422, 403), f"expected 422 or 403, got {resp.status_code}"


# ---------------------------------------------------------------------------
# 2. 无效 JWT → 401
# ---------------------------------------------------------------------------

def test_admin_key_invalid(client):
    """提供无效 Bearer token 时，应返回 401"""
    resp = client.patch(
        "/user/tokens/nonexistent/freeze",
        json={"frozen": True},
        headers={"Authorization": "Bearer invalid-jwt-token"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 3. stats/overview 结构检查
# ---------------------------------------------------------------------------

def test_stats_overview_structure(client):
    """stats/overview 应包含 total_cost_usd 和 request_count 字段"""
    resp = client.get(
        "/admin/stats/overview",
        headers={"x-admin-key": "test-admin-secret"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "total_cost_usd" in data
    assert "request_count" in data


# ---------------------------------------------------------------------------
# 4. stats/tokens 结构检查
# ---------------------------------------------------------------------------

def test_stats_tokens_structure(client):
    """stats/tokens 应返回列表"""
    resp = client.get(
        "/admin/stats/tokens",
        headers={"x-admin-key": "test-admin-secret"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# 5. stats/models 结构检查
# ---------------------------------------------------------------------------

def test_stats_models_structure(client):
    """stats/models 应返回列表"""
    resp = client.get(
        "/admin/stats/models",
        headers={"x-admin-key": "test-admin-secret"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# 6. token CRUD 需要 admin key
# ---------------------------------------------------------------------------

def test_tokens_list_requires_admin_key(client):
    """GET /user/tokens 无认证应拒绝（422）"""
    resp = client.get("/user/tokens")
    assert resp.status_code in (422, 401)


def test_tokens_list_with_valid_key(client, user_jwt_headers):
    """GET /user/tokens 有效 JWT 应返回 200"""
    resp = client.get("/user/tokens", headers=user_jwt_headers)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 7. 冻结/解冻 Token 测试（先创建再冻结）
# ---------------------------------------------------------------------------

def _create_token_and_get_id(client, name: str, jwt_headers: dict, quota: float = 10.0) -> str:
    """创建 token 并返回 id。
    Token 创建端点在 /user/tokens（POST），需要 JWT 认证。
    """
    create_resp = client.post(
        "/user/tokens",
        json={"name": name, "quota_usd": quota},
        headers=jwt_headers,
    )
    assert create_resp.status_code in (200, 201), f"create failed: {create_resp.text}"
    data = create_resp.json()
    assert "id" in data, f"response has no 'id': {data}"
    return data["id"]


def test_freeze_token_flow(client, user_jwt_headers):
    """创建 token → 冻结 → 验证 frozen=True"""
    token_id = _create_token_and_get_id(client, "test-token-freeze", user_jwt_headers)

    # 冻结
    freeze_resp = client.patch(
        f"/user/tokens/{token_id}/freeze",
        json={"frozen": True},
        headers=user_jwt_headers,
    )
    assert freeze_resp.status_code == 200, f"freeze failed: {freeze_resp.text}"
    assert freeze_resp.json()["frozen"] is True


def test_unfreeze_token_flow(client, user_jwt_headers):
    """创建 token → 冻结 → 解冻 → 验证 frozen=False"""
    token_id = _create_token_and_get_id(client, "test-token-unfreeze", user_jwt_headers, quota=5.0)

    # 冻结
    client.patch(
        f"/user/tokens/{token_id}/freeze",
        json={"frozen": True},
        headers=user_jwt_headers,
    )

    # 解冻
    unfreeze_resp = client.patch(
        f"/user/tokens/{token_id}/freeze",
        json={"frozen": False},
        headers=user_jwt_headers,
    )
    assert unfreeze_resp.status_code == 200
    assert unfreeze_resp.json()["frozen"] is False


def test_freeze_nonexistent_token(client, user_jwt_headers):
    """冻结不存在的 token 应返回 404"""
    resp = client.patch(
        "/user/tokens/nonexistent-id/freeze",
        json={"frozen": True},
        headers=user_jwt_headers,
    )
    assert resp.status_code == 404
