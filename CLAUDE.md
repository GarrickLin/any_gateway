# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 技术栈约束

- 数据库：使用 **SQLModel + FastCRUD**（不用原生 SQLAlchemy ORM）
- 日志压缩：使用 **brotli** 读写 JSONL 文件（审计消息记录）
- 认证：AD 用户认证使用 **ldap3**，管理员 API 使用 JWT + x-admin-key 双认证
- 测试：使用 **pytest**，测试目录 `./tests/`

## 常用命令

```bash
# 运行后端（网关 port 8003 + 前端 port 8502）
python any_gateway/main.py

# 直接运行网关（无前端）
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
├── gateway.py         # 主应用、路由注册、lifespan 启动
├── main.py            # 进程管理器（同时启动 gateway + 前端）
├── constants.py       # 全局常量
├── log_writer.py      # 异步 JSONL 日志（brotli 压缩，asyncio 队列 + 3 个消费者）
├── admin/
│   └── router.py      # 所有管理端点：FastCRUD CRUD + 自定义业务端点
├── db/
│   ├── models.py      # SQLModel 数据模型（支持 SQLite 和 PostgreSQL）
│   └── database.py    # 异步 SQLAlchemy 引擎配置
├── middleware/
│   └── auth.py        # API Key 中间件（校验 Token 存在/冻结/额度/过期）
└── services/
    ├── auth_service.py  # JWT 签发/验证、角色查询、超级管理员初始化
    ├── ldap_auth.py     # LDAP Simple Bind + 应急 fallback key
    └── quota.py         # 额度检查与用量更新

apps/react/src/        # React 19 + TypeScript + Vite 前端
├── pages/             # Login、Dashboard、ApiKeys、Chat、Channels、Groups、Users、Logs
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
`AuthMiddleware` 对 `/v1/*`（AI 对话）要求 API Key，跳过 `/admin/*`、`/user/*`、`/auth/*`、`/health`（这些用各自的认证）。

### FastCRUD 使用模式
CRUD 路由通过 `crud_router()` 自动生成，挂载到对应前缀。某些端点（如 Token 创建）因需要返回明文 key，会禁用自动生成的端点并手动实现替代版本。

### 日志写入
日志不直接写文件，而是推入 `asyncio.Queue`，3 个消费者并发处理。文件路径：`data/sessions/{YYYY_MM_DD}/{token_id}.jsonl.br`，每文件一把异步锁防止并发写冲突。

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
```

## 测试规范

- 测试使用 SQLite 内存数据库（`:memory:`）
- 通过 `os.environ` 注入 `ADMIN_KEY`、`DATABASE_URL` 等环境变量
- 使用 `fastapi.testclient.TestClient`（同步）
- JWT 保护路由需先登录获取 token，然后在请求头中携带 `Authorization: Bearer <token>`
