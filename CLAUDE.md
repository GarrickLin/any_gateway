# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 技术栈约束

- 数据库：使用 **SQLModel + FastCRUD**（不用原生 SQLAlchemy ORM）
- 日志压缩：使用 **brotli** 读写 JSONL 文件（审计消息记录）
- 认证：AD 用户认证使用 **ldap3**，管理员 API 使用 JWT + x-admin-key 双认证
- 限流：使用 **Redis + Lua 脚本**实现滑动窗口原子限流
- 测试：使用 **pytest**，测试目录 `./tests/`

## 常用命令

```bash
# 运行网关
uvicorn any_gateway.gateway:app --host 0.0.0.0 --port 8003 --reload

# 运行所有测试
pytest tests/

# 运行单个测试文件
pytest tests/test_admin_router.py -v

# 运行单个测试函数
pytest tests/test_admin_router.py::test_create_token -v

# 前端开发服务器（代理 /admin、/user、/auth 到 8003）
cd apps/react && npm run dev

# 前端构建
cd apps/react && npm run build

# 前端 lint
cd apps/react && npm run lint

# Docker Compose（mock-ad + gateway）
docker-compose up
```

## 架构概览

```
any_gateway/           # 后端 FastAPI 应用
├── gateway.py         # 应用入口、路由注册、lifespan 启动、AI 请求代理
├── constants.py       # 全局常量
├── log_writer.py      # 异步 JSONL 日志（brotli 压缩，asyncio 队列 + 3 个消费者）
├── admin/
│   └── router.py      # 所有管理端点：FastCRUD CRUD + 自定义业务端点
├── db/
│   ├── models.py      # SQLModel 数据模型（支持 SQLite 和 PostgreSQL）
│   └── database.py    # 异步 SQLAlchemy 引擎配置
├── middleware/
│   └── auth.py        # API Key 中间件（校验 Token 存在/冻结/额度/过期 + 限流）
└── services/
    ├── auth_service.py      # JWT 签发/验证、角色查询、超级管理员初始化
    ├── ldap_auth.py         # LDAP Simple Bind + 应急 fallback key
    ├── quota.py             # 额度检查与用量更新
    ├── pricing.py           # 价格查询与费用计算（Group 自定义 → 全局兜底）
    ├── rate_limit_redis.py  # Redis 滑动窗口限流（Lua 脚本原子操作）
    └── rate_limit_service.py # 限流决策入口（检查所有 RateLimit 规则）

apps/react/src/        # React 19 + TypeScript + Vite + Arco Design 前端
├── pages/             # Login、Dashboard、ApiKeys、Chat、Channels、Groups、Users、Prices、Vouchers、Logs
├── api/               # axios HTTP 客户端（client.ts + 各资源模块）
├── components/        # Layout（导航栏）、AuthGuard（路由保护）
├── router/            # React Router 配置
└── store/             # Zustand 全局状态（当前用户、JWT token）

tests/                 # pytest 测试（SQLite 内存 DB + FastAPI TestClient）
mock/                  # mock-ad server（测试用 LDAP 服务）
```

## 关键架构决策

### 认证三层体系
1. **LDAP/AD 认证**：用户登录，Simple Bind 验证，支持 `_admin_fallback` 应急账户
2. **JWT Token**：登录后签发 24h HS256 JWT，payload 含 `sub`（username）和 `role`
3. **API Key**：对外 AI 调用接口，`x-api-key` 或 `Authorization: Bearer sk-xxx`

### 权限分层
- `user`：访问自己的 Token（`/user/tokens/*`）
- `admin`：所有管理功能（`/admin/*`）
- `superadmin`：admin 超集 + 用户角色管理

### Admin 端点双重认证
管理端点（`/admin/channels`、`/admin/groups` 等）同时支持 `x-admin-key`（环境变量）或 Admin JWT，通过 `require_admin_access()` 依赖实现。

### 路由保护策略
`AuthMiddleware` 对 `/v1/*`（AI 对话）要求 API Key，跳过 `/admin/*`、`/user/*`、`/auth/*`、`/health`（这些用各自的认证）。`/v1/models` 特殊：支持可选 API Key（不强制）。

### 透明代理认证头
`forward_request()` 保留客户端原始认证头的 key，仅替换 value 为渠道 `api_key`：
- `Authorization` → `Bearer {api_key}`
- `x-api-key` → `{api_key}`（Anthropic）
- `x-goog-api-key` → `{api_key}`（Gemini）

### FastCRUD 使用模式
CRUD 路由通过 `crud_router()` 自动生成，挂载到对应前缀。某些端点（如 Token 创建）因需要返回明文 key，会禁用自动生成的端点并手动实现替代版本。

### 网关路由选择算法（加权随机）
`find_backend_for_model()` 按优先级选渠道：
1. Token 绑定 `group_id` → 在该组渠道中按 `weight` 加权随机
2. Token 有 `username` → 按用户所属分组的 `priority` 降序，在第一个支持该模型的分组内选取
3. 降级（仅 `_admin_fallback` / superadmin）→ 遍历所有 enabled 渠道

每条 Channel 支持 `models`（JSON 列表）和 `model_mapping`（JSON 别名映射），上游模型名通过映射替换后转发。

### 双层限流（两种 Token 类型）
- **Type 1（套餐 Token，有 group_id）**：查 `RateLimit` 规则，使用 Redis 滑动窗口检查 request/token/quota 三种维度。
- **Type 2（个人 Token，无 group_id）**：检查 `User.quota_usd` 账户余额。
- Fail Open：Redis 不可用时放行请求。

### 价格计算
`calculate_cost()` 优先检查分组自定义价格（`GroupModelPrice`），否则使用全局价格（`ModelPrice`），最终乘以分组 `multiplier`。支持 `request`（固定费）和按 token 计费两种模式。

### Fire-and-forget 后处理
AI 请求响应后，以下操作作为后台 task 异步执行（不阻塞响应）：
- `update_usage()` → 更新 `Token.used_usd`、插入 `UsageLog`
- `update_user_balance()` → 扣减 `User.quota_usd`
- `_update_rate_limit_counters()` → 更新 Redis 限流计数
- `log_writer.enqueue_log()` → 入队 brotli 日志

Task 引用保存到 `app.state.log_tasks` 防止 GC，lifespan 关闭时等待处理完成（timeout=5s）。

### 流式响应多协议解析
支持三种 SSE 协议的 token 计数解析（在 `gateway.py` 的 `parse_stream_usage()`）：
- **OpenAI**：`usage.prompt_tokens/completion_tokens`
- **Anthropic**：`message.usage.input_tokens/message_delta.usage.output_tokens` + cache 字段
- **Gemini**：`usageMetadata.promptTokenCount/candidatesTokenCount`

### 日志写入
日志不直接写文件，而是推入 `asyncio.Queue`（maxsize=1000），3 个消费者并发处理。文件路径：`data/sessions/{YYYY_MM_DD}/{request_id}.json.br`，每文件一把异步锁防止并发写冲突。

## 关键环境变量

```bash
LDAP_SERVER_URL=ldap://dc.company.internal
LDAP_BASE_DN=DC=company,DC=internal
LDAP_DOMAIN=COMPANY
ADMIN_KEY=<管理接口密钥>
ADMIN_FALLBACK_KEY=<应急登录密钥>
JWT_SECRET=<JWT 签名密钥>
JWT_EXPIRE_HOURS=24
SUPERADMIN_USERNAME=<超级管理员用户名>
DATABASE_URL=sqlite+aiosqlite:///./data/gateway.db  # 默认 SQLite
REDIS_URL=redis://localhost:6379                     # 限流用（可选）
GATEWAY_PORT=8003                                    # 默认 8003
NUM_LOG_CONSUMERS=3                                  # 日志消费者数量（2-5）
```

## 测试规范

- 测试使用 SQLite 内存数据库（`:memory:`）
- 通过 `os.environ` 注入 `ADMIN_KEY`、`DATABASE_URL` 等环境变量
- 使用 `fastapi.testclient.TestClient`（同步）
- JWT 保护路由需先登录获取 token，然后在请求头中携带 `Authorization: Bearer <token>`
- `pytest.ini` 配置了 `asyncio_mode = auto`
