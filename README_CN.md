# Any Gateway

**[中文](#any-gateway) · [English](README.md)**

自托管 AI API 网关，将请求代理到多个后端 AI 提供商（OpenAI、Anthropic、Gemini），并提供用户管理、配额控制、限流和审计日志功能。

![](docs/imgs/snapshot1.png)
![](docs/imgs/snapshot2.png)
![](docs/imgs/snapshot3.png)

## 功能特性

- **多提供商路由** — 支持 OpenAI 兼容、Anthropic、Gemini 协议，透明代理认证头
- **加权负载均衡** — 通过可配置权重在多个渠道间分配流量
- **用户分组访问控制** — 将用户分配到分组，按优先级控制渠道访问权限
- **API Key 管理** — 签发 `sk-*` 格式的密钥，支持单 Key 配额限制、过期时间和冻结/解冻
- **配额强制执行** — 转发请求前检查 Token USD 用量，超额直接拦截
- **限流系统** — 基于 Redis 滑动窗口，支持按分组限制请求数、Token 数或消费金额
- **价格与计费** — 支持全局模型定价、分组价格倍数和自定义覆盖价格
- **消费券** — 兑换码充值用户余额
- **LDAP/AD 认证** — 通过 Active Directory Simple Bind 实现企业级登录
- **JWT 管理员认证** — 基于角色的管理端访问控制（`user`、`admin`、`superadmin`）
- **审计日志** — 按请求和日期存储的 Brotli 压缩 JSON 日志
- **React 管理后台** — 用于管理渠道、分组、用户、Token、价格和消费券的完整 SPA
- **流式响应支持** — SSE 透传，支持 AI 流式输出并追踪 Token 用量

## 技术亮点

### 1. 现代化的开发效率工具 (SQLModel + FastCRUD)
后端采用 **SQLModel**，结合了 SQLAlchemy 的数据库能力与 Pydantic 的数据验证能力，使代码具备强类型检查且简洁清晰。配合 **FastCRUD** 使用，大幅减少了基础 CRUD 代码工作量。

### 2. 针对 AI 场景的并发优化 (Asyncio + HTTPX)
- **异步代理：** 使用 **httpx** 配合 FastAPI 原生异步支持，高效处理大量并发 AI 接口请求，不阻塞主线程。
- **非阻塞审计日志：** 使用 **asyncio queue（3 消费者模式）** 防止日志写入成为并发瓶颈。请求响应立即返回，**Brotli 压缩** 和文件写入在后台异步完成。
- **Fire-and-forget 后处理：** 用量更新、余额扣减、限流计数器更新和日志写入均在响应返回后作为后台 Task 异步执行。

### 3. 企业级安全与身份管理 (LDAP + RBAC)
- **身份验证：** 通过 **ldap3** 实现 LDAP/AD 集成，直接接入企业现有活动目录，无需用户重新注册。
- **权限模型：** 利用 **python-jose** 实现 JWT 认证体系，构建清晰的 RBAC 模型，区分普通用户、管理员和超级管理员。

### 4. 双模式限流 (Redis + 余额)
- **分组 Token：** Redis 滑动窗口限制，支持按可配置时间窗口限制请求数、Token 数或消费金额。
- **个人 Token：** 简单余额检查（`User.quota_usd`）。Redis 不可用时 Fail Open。

### 5. 前端状态与性能平衡 (React 19 + Zustand + Arco Design)
采用 **React 19**、**Vite** 构建工具、**Arco Design** UI 组件库和 **Zustand** 轻量级状态管理。

### 6. 数据存储与归档设计
- **存储灵活性：** 支持从 **SQLite** 平滑迁移到生产级 **PostgreSQL**。
- **压缩归档：** 日志按天和请求分片，使用 **Brotli** 压缩，比 Gzip 提供更高压缩比。

## 架构

```
any_gateway/
├── gateway.py               # FastAPI 应用入口，路由逻辑，请求转发
├── constants.py             # 全局常量（端口、限制等）
├── log_writer.py            # 异步 JSONL 日志（brotli 压缩，asyncio 队列，3 个消费者）
├── admin/
│   └── router.py            # 管理端点：FastCRUD 自动 CRUD + 自定义业务逻辑
├── db/
│   ├── models.py            # SQLModel 数据模型
│   └── database.py          # 异步 SQLAlchemy 引擎配置
├── middleware/
│   └── auth.py              # API Key 中间件（校验 Token 存在/冻结/额度/过期 + 限流）
└── services/
    ├── auth_service.py      # JWT 签发/验证、角色管理、超级管理员初始化
    ├── ldap_auth.py         # LDAP Simple Bind + 应急 fallback key
    ├── quota.py             # 额度检查与用量更新
    ├── pricing.py           # 费用计算（分组自定义 → 全局兜底 × multiplier）
    ├── rate_limit_redis.py  # Redis 滑动窗口限流（Lua 脚本原子操作）
    └── rate_limit_service.py # 限流决策入口

apps/react/src/
├── pages/                   # Login、Dashboard、ApiKeys、Chat、Channels、Groups、
│                            # Users、Prices、Vouchers、Logs
├── api/                     # axios HTTP 客户端模块
├── components/
│   ├── AuthGuard/           # 路由保护
│   └── Layout/              # 导航栏与主布局
├── router/                  # React Router 配置
└── store/                   # Zustand 全局状态（当前用户、JWT token）
```

## 认证三层体系

| 层级 | 方式 | 作用范围 |
|---|---|---|
| 用户登录 | LDAP Simple Bind / fallback key | 签发 24h JWT |
| 管理 API | JWT Bearer 或 `x-admin-key` 请求头 | `/admin/*` 端点 |
| AI API 调用 | `x-api-key: sk-*` 或 `Authorization: Bearer sk-*` | `/v1/*` 端点 |

### 权限角色

- `user` — 访问自己的 Token（`/user/tokens/*`）
- `admin` — 全部管理功能（`/admin/*`）
- `superadmin` — admin 超集 + 用户角色管理 + 不受分组限制的渠道访问

## 路由策略

1. 获取用户所属分组，按 `priority` 降序排列
2. 在支持所请求模型的最高优先级分组内，按 `weight` 加权随机选取一个渠道
3. `superadmin` 和 `_admin_fallback` 跳过分组路由，直接访问所有已启用渠道

模型别名通过渠道级 `model_mapping` 解析（例如 `{"gpt-4o": "claude-opus-4-5"}`）。

## 限流策略

根据 Token 类型采用不同限流方式：

| Token 类型 | 方式 | 维度 |
|---|---|---|
| 分组 Token（有 `group_id`） | Redis 滑动窗口 | 请求数 / Token 数 / 消费金额 |
| 个人 Token（无 `group_id`） | 余额检查 | `User.quota_usd` 剩余额度 |

限流规则通过 `/admin/rate-limits` 按分组配置。Redis 为可选组件，不可用时 Fail Open。

## 典型工作流

部署完成后，按以下顺序完成初始配置：

**1. 添加后端渠道**（管理员）

通过管理后台或 API 添加一个 AI 提供商渠道：

```bash
curl -X POST http://localhost:8003/admin/channels \
  -H "x-admin-key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OpenAI 主渠道",
    "provider": "openai",
    "base_url": "https://api.openai.com",
    "api_key": "sk-xxx",
    "models": ["gpt-4o", "gpt-4o-mini"],
    "weight": 1,
    "enabled": true
  }'
```

**2. 创建用户分组并关联渠道**（管理员）

```bash
# 创建分组
curl -X POST http://localhost:8003/admin/groups \
  -H "x-admin-key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"name": "默认分组", "priority": 10, "multiplier": 1.0}'

# 关联渠道（将渠道 id 加入分组）
curl -X POST http://localhost:8003/admin/groups/{group_id}/channels \
  -H "x-admin-key: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"channel_ids": ["{channel_id}"]}'
```

**3. 创建 API Key**（用户登录后自助操作）

```bash
# 先登录获取 JWT
TOKEN=$(curl -s -X POST http://localhost:8003/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your-username", "password": "your-password"}' \
  | jq -r '.access_token')

# 创建 API Key（明文 key 仅返回一次）
curl -X POST http://localhost:8003/user/tokens \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "我的 Key", "group_id": "{group_id}"}'
```

**4. 调用 AI 接口**

```bash
curl -X POST http://localhost:8003/v1/chat/completions \
  -H "Authorization: Bearer sk-your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

## 本地开发（无 LDAP）

无需 LDAP 服务器即可完整运行网关，使用内置应急账户登录：

```bash
# 1. 配置应急账户
ADMIN_FALLBACK_KEY=my-fallback-password
SUPERADMIN_USERNAME=admin

# 2. 启动网关
python any_gateway/main.py

# 3. 使用应急账户登录（用户名固定为 _admin_fallback）
curl -X POST http://localhost:8003/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "_admin_fallback", "password": "my-fallback-password"}'
```

也可以使用内置 mock LDAP 服务器（Docker Compose）：

```bash
docker-compose up  # 启动 mock-ad + gateway
```

## 环境要求

- Python 3.11+
- Node.js 18+（前端开发时需要）
- Redis（可选，用于限流）
- LDAP/AD 服务器（本地开发可使用内置 mock 服务器）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env  # 或手动设置环境变量
```

必填变量：

```bash
ADMIN_KEY=<管理接口密钥>
JWT_SECRET=<JWT 签名随机密钥>
ADMIN_FALLBACK_KEY=<应急登录密钥>
SUPERADMIN_USERNAME=<超级管理员用户名>
```

可选变量：

```bash
LDAP_SERVER_URL=ldap://dc.company.internal
LDAP_BASE_DN=DC=company,DC=internal
LDAP_DOMAIN=COMPANY
JWT_EXPIRE_HOURS=24
DATABASE_URL=sqlite+aiosqlite:///./data/gateway.db  # 默认值
REDIS_URL=redis://localhost:6379                     # 限流用
GATEWAY_PORT=8003
NUM_LOG_CONSUMERS=3
```

### 3. 启动

```bash
uvicorn any_gateway.gateway:app --host 0.0.0.0 --port 8003 --reload
```

管理后台地址：`http://localhost:8003`

## Docker

```bash
# 包含 mock LDAP 服务器
docker-compose up

# 仅网关
docker build -t any_gateway .
docker run -p 8003:8003 \
  -e ADMIN_KEY=your-key \
  -e JWT_SECRET=your-secret \
  -e ADMIN_FALLBACK_KEY=your-fallback \
  -v $(pwd)/data:/app/data \
  any_gateway
```

## 前端开发

```bash
cd apps/react
npm install
npm run dev   # 开发服务器，自动代理 /admin、/user、/auth 到 :8003
npm run build # 生产构建（输出由网关直接服务）
npm run lint
```

## API 说明

### 健康检查

```
GET /health
```

### AI 接口（OpenAI 兼容）

```
POST /v1/chat/completions
POST /v1/messages          # Anthropic 协议
GET  /v1/models            # 支持可选 API Key 或 JWT
```

认证：`x-api-key: sk-*`、`Authorization: Bearer sk-*` 或 `x-goog-api-key`（Gemini）。

### 认证

```
POST /auth/login           # LDAP 登录 → JWT
GET  /auth/me              # 当前用户信息（含配额、用量）
```

### 用户接口（需要 JWT）

```
GET    /user/tokens              # 查看自己的 Token 列表
POST   /user/tokens              # 创建 Token（仅返回一次明文 key）
DELETE /user/tokens/{id}         # 删除 Token
POST   /user/tokens/{id}/freeze  # 冻结 Token
PATCH  /user/tokens/{id}/freeze  # 解冻 Token
GET    /user/logs                # 用量日志（分页、可过滤）
GET    /user/logs/{id}/messages  # 查看某次请求的完整内容
POST   /user/vouchers/redeem     # 兑换消费券
GET    /user/groups              # 可用分组列表（创建 Token 时使用）
GET    /user/stats/overview      # 今日消费与请求数统计
GET    /user/stats/tokens        # Top 10 Token 用量
GET    /user/stats/models        # Top 10 模型请求量
```

### 管理接口（需要 JWT 或 x-admin-key）

```
/admin/channels                  # 渠道 CRUD
/admin/groups                    # 分组 CRUD
/admin/users                     # 用户 CRUD
/admin/users/{username}/role     # 角色管理（仅 superadmin）
/admin/rate-limits               # 限流规则 CRUD（按分组配置）
/admin/prices                    # 全局模型价格 CRUD
/admin/group-prices              # 分组自定义价格 CRUD
/admin/vouchers                  # 消费券 CRUD（批量创建/管理）
GET /admin/stats/overview        # 全局今日消费统计
GET /admin/stats/tokens          # 全局 Top 10 Token 用量
GET /admin/stats/models          # 全局 Top 10 模型请求量
```

## 审计日志

请求/响应对异步写入：

```
data/sessions/{YYYY_MM_DD}/{request_id}.json.br
```

每个文件为 Brotli 压缩的 JSON 格式，按请求和日期各存一个文件。3 个 asyncio 消费者并发处理写入队列，每文件一把异步锁防止并发写冲突。

## 测试

```bash
# 运行所有测试
pytest tests/

# 运行单个测试文件
pytest tests/test_admin_router.py -v

# 运行单个测试函数
pytest tests/test_admin_router.py::test_create_token -v
```

测试使用 SQLite 内存数据库和 FastAPI 的 `TestClient`。

## 技术栈

| 组件 | 技术 |
|---|---|
| 后端框架 | FastAPI |
| 数据库 ORM | SQLModel + FastCRUD |
| 数据库 | SQLite（默认）/ PostgreSQL |
| 认证 | ldap3、python-jose |
| 限流 | Redis + Lua 脚本 |
| 审计日志 | brotli + asyncio 队列 |
| HTTP 客户端 | httpx |
| 前端 | React 19 + TypeScript + Vite |
| UI 组件库 | Arco Design |
| 状态管理 | Zustand |
| HTTP 请求 | axios |
