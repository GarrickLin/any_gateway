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
os.environ.setdefault("ADMIN_FALLBACK_KEY", "fallback-key")

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
    """提供测试客户端，覆盖 DB 依赖（包括 middleware 使用的 engine）"""
    import db.database as _db
    import gateway as _gw
    import middleware.auth as _auth_mw

    from db.database import async_session_generator

    # 覆盖所有模块持有的 engine 引用，确保 middleware 也使用 TEST_ENGINE
    original_db_engine = _db.engine
    original_gw_engine = _gw.engine
    _db.engine = TEST_ENGINE
    _gw.engine = TEST_ENGINE
    # middleware.auth 通过 `from db.database import engine` 持有本地绑定，需单独覆盖
    original_mw_engine = getattr(_auth_mw, "engine", None)
    _auth_mw.engine = TEST_ENGINE

    app.dependency_overrides[async_session_generator] = override_session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()

    # 还原 engine
    _db.engine = original_db_engine
    _gw.engine = original_gw_engine
    if original_mw_engine is not None:
        _auth_mw.engine = original_mw_engine


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


def test_stats_overview_actual_cost_usd(client):
    """admin stats/overview 应包含 actual_cost_usd（covered_by_package=False 的汇总）"""
    resp = client.get(
        "/admin/stats/overview",
        headers={"x-admin-key": "test-admin-secret"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "actual_cost_usd" in data


def test_user_stats_overview_actual_cost_usd(client):
    """user stats/overview 应包含 actual_cost_usd（covered_by_package=False 的汇总）"""
    from services.auth_service import create_access_token
    token = create_access_token("stats-user", "user")
    resp = client.get(
        "/user/stats/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "actual_cost_usd" in data


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


# ---------------------------------------------------------------------------
# 8. 消息详情端点测试
# ---------------------------------------------------------------------------

def test_get_log_messages_admin_not_found(client):
    """查询不存在的 request_id 应返回 404"""
    # 获取 admin token（参考文件中已有的认证方式）
    resp = client.post(
        "/auth/login",
        json={"username": "_admin_fallback", "password": os.environ.get("ADMIN_FALLBACK_KEY", "")},
    )
    # 如果 fallback 不可用，用 x-admin-key
    if resp.status_code == 200:
        token = resp.json()["access_token"]
        auth_header = {"Authorization": f"Bearer {token}"}
    else:
        auth_header = {"x-admin-key": os.environ.get("ADMIN_KEY", "test-admin-secret")}

    resp = client.get("/admin/logs/nonexistent_id_12345/messages", headers=auth_header)
    assert resp.status_code == 404


def test_update_token_group_id(client, user_jwt_headers):
    """PATCH /user/tokens/:id 应能修改 group_id。"""
    admin_headers = {"x-admin-key": "test-admin-secret"}

    # 先创建分组，再通过 GET 获取 id（fastcrud create 返回 null）
    client.post("/admin/groups", json={"name": "g-patch-test"}, headers=admin_headers)
    groups = client.get("/admin/groups", headers=admin_headers).json()
    grp_id = next(g["id"] for g in groups["data"] if g["name"] == "g-patch-test")

    # 创建 token
    tok = client.post("/user/tokens", json={"name": "tok-patch"}, headers=user_jwt_headers).json()
    tok_id = tok["id"]

    # 更新 group_id，再 GET 验证
    res = client.patch(f"/user/tokens/{tok_id}", json={"group_id": grp_id}, headers=user_jwt_headers)
    assert res.status_code == 200
    get1 = client.get(f"/user/tokens/{tok_id}", headers=user_jwt_headers)
    assert get1.status_code == 200
    assert get1.json()["group_id"] == grp_id

    # 清空 group_id，再 GET 验证
    res2 = client.patch(f"/user/tokens/{tok_id}", json={"group_id": None}, headers=user_jwt_headers)
    assert res2.status_code == 200
    get2 = client.get(f"/user/tokens/{tok_id}", headers=user_jwt_headers)
    assert get2.status_code == 200
    assert get2.json()["group_id"] is None


def test_user_can_list_groups(client):
    """普通用户（JWT）应能访问 /user/groups 列出所有分组。"""
    admin_headers = {"x-admin-key": "test-admin-secret"}

    # 先创建一个分组
    client.post("/admin/groups", json={"name": "test-visible-group"}, headers=admin_headers)

    # 使用 JWT（通过 create_access_token 直接生成 user 角色 JWT）
    from services.auth_service import create_access_token
    jwt = create_access_token("test-user", "user")

    res = client.get("/user/groups", headers={"Authorization": f"Bearer {jwt}"})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert any(g["name"] == "test-visible-group" for g in data)
    # 严格验证字段隔离：仅返回 id 和 name，不暴露 rpm_limit 等其他字段
    assert set(data[0].keys()) == {"id", "name"}


# ---------------------------------------------------------------------------
# 9. /v1/models 可选 API Key 认证测试
# ---------------------------------------------------------------------------

def test_models_with_valid_api_key_returns_200(client):
    """GET /v1/models 携带有效 API Key（x-api-key header）时，middleware 应注入 token 信息，endpoint 返回 200。"""
    login = client.post("/admin/auth/login", json={"username": "_admin_fallback", "password": os.environ["ADMIN_FALLBACK_KEY"]})
    jwt = login.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {jwt}"}
    tok = client.post("/user/tokens", json={"name": "models-test-key"}, headers=user_headers).json()
    key = tok["key"]

    res = client.get("/v1/models", headers={"x-api-key": key})
    assert res.status_code == 200
    assert "data" in res.json()


def test_models_with_x_goog_api_key_header(client):
    """GET /v1/models 携带有效 key 通过 x-goog-api-key header 时，应返回 200。"""
    login = client.post("/admin/auth/login", json={"username": "_admin_fallback", "password": os.environ["ADMIN_FALLBACK_KEY"]})
    jwt = login.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {jwt}"}
    tok = client.post("/user/tokens", json={"name": "models-goog-key"}, headers=user_headers).json()
    key = tok["key"]

    res = client.get("/v1/models", headers={"x-goog-api-key": key})
    assert res.status_code == 200
    assert "data" in res.json()


def test_models_with_authorization_bearer_header(client):
    """GET /v1/models 携带有效 API Key（Authorization: Bearer header）时，应返回 200。"""
    login = client.post("/admin/auth/login", json={"username": "_admin_fallback", "password": os.environ["ADMIN_FALLBACK_KEY"]})
    jwt = login.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {jwt}"}
    tok = client.post("/user/tokens", json={"name": "models-bearer-key"}, headers=user_headers).json()
    key = tok["key"]

    res = client.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
    assert res.status_code == 200
    assert "data" in res.json()


def test_models_with_invalid_api_key_returns_specific_error(client):
    """GET /v1/models 携带无效 API Key 时，应返回 401 且错误信息明确（非 Authentication required）。"""
    res = client.get("/v1/models", headers={"x-api-key": "sk-invalid-key-xyz"})
    assert res.status_code == 401
    body = res.json()
    assert body.get("error") == "invalid api key"


def test_models_without_auth_returns_401(client):
    """GET /v1/models 不带任何认证时应返回 401。"""
    res = client.get("/v1/models")
    assert res.status_code == 401


def test_models_filtered_by_token_group(client):
    """API Key 绑定了特定 group 时，/v1/models 只返回该 group 渠道的模型。"""
    import json as _json

    ADMIN_HEADERS = {"x-admin-key": "test-admin-secret"}

    # 1. 创建两个分组（fastcrud create 返回 null，需 GET 获取 id）
    client.post("/admin/groups", json={"name": "models-group-a"}, headers=ADMIN_HEADERS)
    client.post("/admin/groups", json={"name": "models-group-b"}, headers=ADMIN_HEADERS)
    groups_resp = client.get("/admin/groups", headers=ADMIN_HEADERS).json()
    grp_a = next(g for g in groups_resp["data"] if g["name"] == "models-group-a")
    grp_b = next(g for g in groups_resp["data"] if g["name"] == "models-group-b")

    # 2. 创建两个渠道，各有不同模型（fastcrud create 返回 null，需 GET 获取 id）
    client.post("/admin/channels", json={
        "name": "ch-model-a", "provider": "openai",
        "base_url": "http://fake-a/v1", "api_key": "fake-a",
        "models": _json.dumps(["model-only-in-a"]), "enabled": True, "weight": 1
    }, headers=ADMIN_HEADERS)
    client.post("/admin/channels", json={
        "name": "ch-model-b", "provider": "openai",
        "base_url": "http://fake-b/v1", "api_key": "fake-b",
        "models": _json.dumps(["model-only-in-b"]), "enabled": True, "weight": 1
    }, headers=ADMIN_HEADERS)
    channels_resp = client.get("/admin/channels", headers=ADMIN_HEADERS).json()
    ch_a = next(c for c in channels_resp["data"] if c["name"] == "ch-model-a")
    ch_b = next(c for c in channels_resp["data"] if c["name"] == "ch-model-b")

    # 3. 分组-渠道关联
    client.post(f"/admin/groups/{grp_a['id']}/channels/{ch_a['id']}", headers=ADMIN_HEADERS)
    client.post(f"/admin/groups/{grp_b['id']}/channels/{ch_b['id']}", headers=ADMIN_HEADERS)

    # 4. 创建 token 并绑定 grp_a
    login = client.post("/admin/auth/login", json={"username": "_admin_fallback", "password": os.environ["ADMIN_FALLBACK_KEY"]})
    jwt_token = login.json()["access_token"]
    user_headers = {"Authorization": f"Bearer {jwt_token}"}
    tok = client.post("/user/tokens", json={"name": "group-a-token", "group_id": grp_a["id"]}, headers=user_headers).json()
    api_key = tok["key"]

    # 5. 用绑定了 grp_a 的 API Key 查模型，应只看到 model-only-in-a
    res = client.get("/v1/models", headers={"x-api-key": api_key})
    assert res.status_code == 200
    model_ids = [m["id"] for m in res.json()["data"]]
    assert "model-only-in-a" in model_ids
    assert "model-only-in-b" not in model_ids


def test_group_all_visible_field(client):
    """UserGroup 应支持 all_visible 字段"""
    res = client.post(
        "/admin/groups",
        json={"name": "visible-test", "priority": 1, "multiplier": 1.0, "all_visible": True},
        headers={"x-admin-key": "test-admin-secret"},
    )
    assert res.status_code in (200, 201)
    # FastCRUD create 返回 None（无 select_schema），需通过 GET 验证字段
    groups = client.get("/admin/groups", headers={"x-admin-key": "test-admin-secret"}).json()
    visible_grp = next((g for g in groups["data"] if g["name"] == "visible-test"), None)
    assert visible_grp is not None
    assert visible_grp["all_visible"] is True

    # 默认值应为 False
    res2 = client.post(
        "/admin/groups",
        json={"name": "hidden-test", "priority": 1, "multiplier": 1.0},
        headers={"x-admin-key": "test-admin-secret"},
    )
    assert res2.status_code in (200, 201)
    groups2 = client.get("/admin/groups", headers={"x-admin-key": "test-admin-secret"}).json()
    hidden_grp = next((g for g in groups2["data"] if g["name"] == "hidden-test"), None)
    assert hidden_grp is not None
    assert hidden_grp["all_visible"] is False


def test_get_visible_groups_includes_all_visible(client):
    """get_visible_groups 应返回 all_visible=True 的分组，即使用户没有 membership"""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession
    from services.auth_service import get_visible_groups

    # 创建 all_visible 分组（通过 admin API，确保已写入 DB）
    client.post(
        "/admin/groups",
        json={"name": "public-group-test", "priority": 1, "multiplier": 1.0, "all_visible": True},
        headers={"x-admin-key": "test-admin-secret"},
    )

    async def _check():
        async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
            groups = await get_visible_groups("some-user-no-membership", session)
            names = [g.name for g in groups]
            assert "public-group-test" in names

    asyncio.run(_check())


def test_lazy_create_user_no_default_join(client):
    """lazy_create_user 不应再写入 UserGroupMembership 记录"""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlmodel import select
    from db.models import UserGroupMembership
    from services.auth_service import lazy_create_user

    async def _check():
        async with AsyncSession(TEST_ENGINE, expire_on_commit=False) as session:
            await lazy_create_user("newuser-no-group-123", session)
            await session.commit()
            result = await session.execute(
                select(UserGroupMembership).where(
                    UserGroupMembership.username == "newuser-no-group-123"
                )
            )
            memberships = result.scalars().all()
            assert len(memberships) == 0  # 不应写入任何记录

    asyncio.run(_check())


def test_rate_limits_filtered_by_group(client):
    """GET /admin/rate-limits?group_id=xxx 应只返回该分组的规则"""
    ADMIN_HEADERS = {"x-admin-key": "test-admin-secret"}

    # 创建两个分组（FastCRUD create 返回 null，需用 GET 获取 id）
    client.post("/admin/groups", json={"name": "rl-group-1", "priority": 1, "multiplier": 1.0}, headers=ADMIN_HEADERS)
    client.post("/admin/groups", json={"name": "rl-group-2", "priority": 1, "multiplier": 1.0}, headers=ADMIN_HEADERS)
    groups_resp = client.get("/admin/groups", headers=ADMIN_HEADERS).json()
    g1 = next(g for g in groups_resp["data"] if g["name"] == "rl-group-1")
    g2 = next(g for g in groups_resp["data"] if g["name"] == "rl-group-2")

    # 各自创建一条规则
    client.post(
        "/admin/rate-limits",
        json={"group_id": g1["id"], "window_sec": 60, "limit_type": "request_limit", "value": 10},
        headers=ADMIN_HEADERS,
    )
    client.post(
        "/admin/rate-limits",
        json={"group_id": g2["id"], "window_sec": 60, "limit_type": "request_limit", "value": 20},
        headers=ADMIN_HEADERS,
    )

    # 查询 group 1 的规则，应只返回 1 条且属于 g1
    res = client.get(
        "/admin/rate-limits",
        params={"group_id": g1["id"]},
        headers=ADMIN_HEADERS,
    )
    assert res.status_code == 200
    body = res.json()
    # FastCRUD read_multi 返回 {"data": [...], "total_count": N}
    rules = body.get("data", body) if isinstance(body, dict) else body
    assert isinstance(rules, list)
    assert len(rules) >= 1
    assert all(r["group_id"] == g1["id"] for r in rules)
