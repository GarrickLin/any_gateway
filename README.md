# Any Gateway

A self-hosted AI API gateway that proxies requests to multiple backend providers (OpenAI, Anthropic, Gemini) with user management, quota control, and audit logging.

![](docs/imgs/snapshot1.png)
![](docs/imgs/snapshot2.png)
![](docs/imgs/snapshot3.png)

## Features

- **Multi-provider routing** — Supports OpenAI-compatible, Anthropic, and Gemini APIs with automatic protocol detection
- **Weighted load balancing** — Distribute traffic across channels using configurable weights
- **User group access control** — Assign users to groups with priority-based channel access
- **API key management** — Issue `sk-*` keys with per-key quota limits and expiration
- **Quota enforcement** — Per-token USD spend limits enforced before forwarding requests
- **LDAP/AD authentication** — Enterprise login via Active Directory Simple Bind
- **JWT admin auth** — Role-based admin access (`user`, `admin`, `superadmin`)
- **Audit logging** — Brotli-compressed JSONL logs per token, per day
- **React admin dashboard** — Full-featured SPA for managing channels, groups, users, and tokens
- **Streaming support** — SSE pass-through for streaming AI responses

## Architecture

```
any_gateway/
├── gateway.py          # FastAPI app, routing logic, request forwarding
├── main.py             # Process manager (gateway + frontend)
├── constants.py        # Global constants (ports, limits)
├── log_writer.py       # Async JSONL logger (brotli, asyncio queue, 3 consumers)
├── admin/
│   └── router.py       # Admin endpoints: FastCRUD CRUD + custom business logic
├── db/
│   ├── models.py       # SQLModel data models
│   └── database.py     # Async SQLAlchemy engine
├── middleware/
│   └── auth.py         # API key middleware (validates token existence, quota, expiry)
└── services/
    ├── auth_service.py # JWT issuance/validation, role management, superadmin init
    ├── ldap_auth.py    # LDAP Simple Bind + emergency fallback key
    └── quota.py        # Quota check and usage update

apps/react/src/
├── pages/              # Login, Dashboard, ApiKeys, Chat, Channels, Groups, Users, Logs
├── api/                # Axios HTTP client modules
├── components/         # Layout (nav), AuthGuard (route protection)
├── router/             # React Router configuration
└── store/              # Zustand global state (user, JWT token)
```

## Authentication Layers

| Layer | Method | Scope |
|---|---|---|
| User login | LDAP Simple Bind / fallback key | Issues 24h JWT |
| Admin API | JWT Bearer or `x-admin-key` header | `/admin/*` endpoints |
| AI API calls | `x-api-key: sk-*` or `Authorization: Bearer sk-*` | `/v1/*` endpoints |

### Roles

- `user` — access own tokens (`/user/tokens/*`)
- `admin` — all management functions (`/admin/*`)
- `superadmin` — admin superset + user role management + unrestricted channel access

## Routing Strategy

1. Resolve user's group memberships, ordered by `priority` descending
2. Within the highest-priority group that supports the requested model, select a channel by weighted random
3. Superadmin and `_admin_fallback` bypass group routing and access all enabled channels

Model aliases are resolved via per-channel `model_mapping` (e.g., `{"gpt-4o": "claude-opus-4-5"}`).

## Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend development)
- LDAP/AD server (or use the mock server for local development)

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env  # or set variables manually
```

Required environment variables:

```bash
ADMIN_KEY=<admin API key>
JWT_SECRET=<random secret for JWT signing>
ADMIN_FALLBACK_KEY=<emergency login password>
SUPERADMIN_USERNAME=<initial superadmin username>
```

Optional:

```bash
LDAP_SERVER_URL=ldap://dc.company.internal
LDAP_BASE_DN=DC=company,DC=internal
LDAP_DOMAIN=COMPANY
JWT_EXPIRE_HOURS=24
DATABASE_URL=sqlite+aiosqlite:///./data/gateway.db  # default
```

### 3. Run

```bash
# Gateway + frontend (port 8003)
python any_gateway/main.py

# Gateway only
uvicorn any_gateway.gateway:app --host 0.0.0.0 --port 8003 --reload
```

The admin dashboard is served at `http://localhost:8003`.

## Docker

```bash
# With mock LDAP server
docker-compose up

# Gateway only
docker build -t any_gateway .
docker run -p 8003:8003 \
  -e ADMIN_KEY=your-key \
  -e JWT_SECRET=your-secret \
  -e ADMIN_FALLBACK_KEY=your-fallback \
  -v $(pwd)/data:/app/data \
  any_gateway
```

## Frontend Development

```bash
cd apps/react
npm install
npm run dev   # dev server with proxy to :8003
npm run build # production build (output served by gateway)
npm run lint
```

## API Reference

### Health

```
GET /health
```

### AI (OpenAI-compatible)

```
POST /v1/chat/completions
POST /v1/messages          # Anthropic protocol
GET  /v1/models
```

Authenticate with `x-api-key: sk-*` or `Authorization: Bearer sk-*`.

### Auth

```
POST /auth/login           # LDAP login → JWT
GET  /auth/me              # current user info
```

### User (JWT required)

```
GET    /user/tokens        # list own tokens
POST   /user/tokens        # create token
DELETE /user/tokens/{id}   # delete token
```

### Admin (JWT or x-admin-key required)

```
/admin/channels            # CRUD
/admin/groups              # CRUD
/admin/tokens              # CRUD
/admin/users               # CRUD
/admin/users/{username}/role  # role management (superadmin only)
```

## Audit Logs

Request/response pairs are logged asynchronously to:

```
data/sessions/{YYYY_MM_DD}/{token_id}.jsonl.br
```

Each file is Brotli-compressed JSONL. One file per token per day. A 3-consumer asyncio queue handles concurrent writes without file locking contention.

## Testing

```bash
# All tests
pytest tests/

# Single file
pytest tests/test_admin_router.py -v

# Single test
pytest tests/test_admin_router.py::test_create_token -v
```

Tests use SQLite in-memory databases and FastAPI's `TestClient`.

## Tech Stack

| Component | Technology |
|---|---|
| Backend framework | FastAPI |
| Database ORM | SQLModel + FastCRUD |
| Database | SQLite (default) / PostgreSQL |
| Authentication | ldap3, python-jose |
| Audit logging | brotli + asyncio queue |
| HTTP client | httpx |
| Frontend | React 19 + TypeScript + Vite |
| State management | Zustand |
| HTTP requests | axios |
