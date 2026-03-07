"""
JWT 认证服务。

职责：
- JWT 签发与验证（HS256，python-jose）
- 查询用户角色（admin_users 表，不在表中则视为 "user"）
- 超级管理员初始化（SUPERADMIN_USERNAME 环境变量）
"""

import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from loguru import logger
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AdminUser

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

_JWT_SECRET_DEFAULT = "change-me-in-production"
_JWT_SECRET = os.getenv("JWT_SECRET", _JWT_SECRET_DEFAULT)
_ALGORITHM = "HS256"

if not os.getenv("JWT_SECRET") or _JWT_SECRET == _JWT_SECRET_DEFAULT:
    logger.critical(
        "JWT_SECRET 使用了默认不安全值，生产环境请务必设置 JWT_SECRET 环境变量！"
    )
_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))


# ---------------------------------------------------------------------------
# JWT 签发 / 验证
# ---------------------------------------------------------------------------


def create_access_token(username: str, role: str) -> str:
    """签发 JWT。

    Args:
        username: 用户名（将存入 ``sub`` 字段）。
        role:     用户角色，例如 ``"admin"``、``"superadmin"``。

    Returns:
        已签名的 JWT 字符串。
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=_EXPIRE_HOURS)
    payload = {
        "sub": username,
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_ALGORITHM)


def verify_token(token: str) -> dict:
    """验证 JWT 并返回 payload。

    Args:
        token: Bearer token 字符串（不含 "Bearer " 前缀）。

    Returns:
        解码后的 payload 字典，包含 ``sub``、``role``、``exp``。

    Raises:
        JWTError: token 无效或已过期时抛出。
    """
    return jwt.decode(token, _JWT_SECRET, algorithms=[_ALGORITHM])


# ---------------------------------------------------------------------------
# 用户角色查询
# ---------------------------------------------------------------------------


async def get_user_role(username: str, session: AsyncSession) -> str:
    """从 admin_users 表查询用户角色。

    Args:
        username: 登录用户名。
        session:  异步数据库 session。

    Returns:
        用户在 admin_users 表中的 role 字段；若不在表中则返回 ``"user"``。
    """
    stmt = select(AdminUser).where(AdminUser.username == username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        return "user"
    return user.role


# ---------------------------------------------------------------------------
# JWT 权限校验 FastAPI 依赖函数
# ---------------------------------------------------------------------------


async def require_auth(
    authorization: str = Header(...),
) -> dict:
    """验证 Authorization: Bearer <token>，返回 {"username": ..., "role": ...}。

    Raises:
        HTTPException 401: 缺少 Bearer token 或 token 无效/过期。
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Bearer token")
    token = authorization[len("Bearer "):]
    try:
        payload = verify_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    username = payload.get("sub")
    role = payload.get("role", "user")
    if not username:
        raise HTTPException(status_code=401, detail="Token payload 无效")
    return {"username": username, "role": role}


def require_role(*roles: str):
    """工厂函数，返回一个 Depends checker，验证 JWT 且 role 在 roles 中。

    用法::

        Depends(require_role("admin", "superadmin"))

    Raises:
        HTTPException 403: 当前用户角色不在允许列表中。
    """
    async def checker(user: dict = Depends(require_auth)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Permission denied")
        return user
    return checker


# ---------------------------------------------------------------------------
# 超级管理员初始化
# ---------------------------------------------------------------------------


async def init_superadmin(session: AsyncSession) -> None:
    """在应用启动时确保超级管理员账户存在。

    读取环境变量 ``SUPERADMIN_USERNAME``；若该用户名尚未在 admin_users 表中，
    则以 ``role="superadmin"`` 插入一条记录。

    Args:
        session: 异步数据库 session。
    """
    username = os.getenv("SUPERADMIN_USERNAME")
    if not username:
        logger.warning("SUPERADMIN_USERNAME 未配置，跳过超级管理员初始化")
        return

    stmt = select(AdminUser).where(AdminUser.username == username)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        superadmin = AdminUser(
            username=username,
            role="superadmin",
            created_by="system",
        )
        session.add(superadmin)
        await session.commit()
        logger.info(f"超级管理员 [{username}] 已初始化")
    else:
        logger.info(f"超级管理员 [{username}] 已存在（role={existing.role}），跳过")


# ---------------------------------------------------------------------------
# 懒加载用户创建（首次 AD 登录时调用）
# ---------------------------------------------------------------------------


async def lazy_create_user(username: str, session: AsyncSession) -> None:
    """首次登录时懒加载创建 User 记录并加入 default 分组。

    幂等：若 User 已存在则跳过；若已在 default 分组则不重复加入。

    Args:
        username: AD 用户名（大小写敏感，与 LDAP 保持一致）。
        session:  已打开的异步数据库 session。
    """
    from db.models import User, UserGroup, UserGroupMembership

    # 1. 确保 User 记录存在
    existing_user = await session.get(User, username)
    if existing_user is None:
        session.add(User(username=username))
        await session.flush()  # 确保 User 已写入，避免 PG 外键约束失败

    # 2. 查找 default 分组
    result = await session.execute(
        select(UserGroup).where(UserGroup.name == "default")
    )
    default_group = result.scalar_one_or_none()
    if default_group is None:
        logger.warning("default 分组不存在，跳过用户分组加入")
        return

    # 3. 确保用户在 default 分组中（幂等）
    result = await session.execute(
        select(UserGroupMembership).where(
            UserGroupMembership.username == username,
            UserGroupMembership.group_id == default_group.id,
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(UserGroupMembership(username=username, group_id=default_group.id))
