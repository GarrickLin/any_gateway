import secrets
from datetime import datetime, timezone
from uuid import uuid4

from sqlmodel import SQLModel, Field


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# =======================
# UserGroup（用户分组）
# =======================


class UserGroupBase(SQLModel):
    name: str = Field(unique=True)
    rpm_limit: int = Field(default=60)
    tpm_limit: int = Field(default=1_000_000)
    priority: int = Field(default=1)
    multiplier: float = Field(default=1.0)


class UserGroup(UserGroupBase, table=True):
    __tablename__ = "user_groups"
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    created_at: str = Field(default_factory=utcnow)


class UserGroupCreate(UserGroupBase):
    pass


class UserGroupUpdate(SQLModel):
    rpm_limit: int | None = None
    tpm_limit: int | None = None
    priority: int | None = None
    multiplier: float | None = None


# =======================
# Token（内部 API Key）
# =======================


class TokenBase(SQLModel):
    name: str
    group_id: str | None = Field(default=None, foreign_key="user_groups.id")
    username: str | None = Field(default=None, foreign_key="users.username")
    quota_usd: float = Field(default=0)
    expires_at: str | None = None


class Token(TokenBase, table=True):
    __tablename__ = "tokens"
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    key: str = Field(
        default_factory=lambda: f"sk-{secrets.token_hex(16)}",
        unique=True,
    )
    used_usd: float = Field(default=0)
    frozen: bool = Field(default=False)
    created_at: str = Field(default_factory=utcnow)
    last_used: str | None = None


class TokenCreate(TokenBase):
    pass


class TokenUpdate(SQLModel):
    name: str | None = None
    group_id: str | None = None
    quota_usd: float | None = None
    expires_at: str | None = None
    frozen: bool | None = None


# =======================
# Channel（后端渠道）
# =======================


class ChannelBase(SQLModel):
    name: str
    provider: str
    base_url: str
    # 当前明文存储（设计决策：YAGNI，待后期添加 Fernet 加密）
    api_key: str
    weight: int = Field(default=1)
    enabled: bool = Field(default=True)
    models: str | None = None
    model_mapping: str | None = (
        None  # JSON string, e.g. '{"gpt-4o": "claude-opus-4-5"}'
    )


class Channel(ChannelBase, table=True):
    __tablename__ = "channels"
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    created_at: str = Field(default_factory=utcnow)


class ChannelCreate(ChannelBase):
    pass


class ChannelUpdate(SQLModel):
    name: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    weight: int | None = None
    enabled: bool | None = None
    models: str | None = None
    model_mapping: str | None = None


# =======================
# UsageLog（用量记录，只写不改）
# =======================


class UsageLog(SQLModel, table=True):
    __tablename__ = "usage_logs"
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    token_id: str | None = Field(default=None, foreign_key="tokens.id")
    username: str | None = Field(default=None)  # 冗余存储，Token 删除后仍可追溯
    channel_id: str | None = Field(default=None, foreign_key="channels.id")
    model: str | None = None
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    cost_usd: float = Field(default=0)
    duration_ms: float = Field(default=0)
    status: int | None = None
    is_stream: bool = Field(default=False)
    created_at: str = Field(default_factory=utcnow)


# =======================
# Voucher（兑换码）
# =======================


class VoucherBase(SQLModel):
    amount_usd: float
    expires_at: str | None = None


class Voucher(VoucherBase, table=True):
    __tablename__ = "vouchers"
    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    code: str = Field(unique=True)
    used: bool = Field(default=False)
    used_by: str | None = Field(default=None, foreign_key="tokens.id")
    used_at: str | None = None
    created_at: str = Field(default_factory=utcnow)


class VoucherCreate(VoucherBase):
    pass


# =======================
# AdminUser（管理员账户）
# =======================


class AdminUser(SQLModel, table=True):
    __tablename__ = "admin_users"
    username: str = Field(primary_key=True)  # LDAP 用户名
    role: str = Field(default="admin")  # "admin" | "superadmin"
    created_by: str | None = None
    created_at: str = Field(default_factory=utcnow)


# =======================
# User（AD 用户，懒加载）
# =======================


class User(SQLModel, table=True):
    __tablename__ = "users"
    username: str = Field(primary_key=True)
    created_at: str = Field(default_factory=utcnow)


# =======================
# UserGroupMembership（用户-分组 多对多）
# =======================


class UserGroupMembership(SQLModel, table=True):
    __tablename__ = "user_group_memberships"
    username: str = Field(foreign_key="users.username", primary_key=True)
    group_id: str = Field(foreign_key="user_groups.id", primary_key=True)


# =======================
# GroupChannel（分组-渠道 多对多）
# =======================


class GroupChannel(SQLModel, table=True):
    __tablename__ = "group_channels"
    group_id: str = Field(foreign_key="user_groups.id", primary_key=True)
    channel_id: str = Field(foreign_key="channels.id", primary_key=True)
