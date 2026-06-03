import React, { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import '../Home/index.css'
import './index.css'

type Section = { id: string; label: string; children?: Section[] }

const sections: Section[] = [
  { id: 'overview', label: '概览' },
  {
    id: 'quickstart', label: '快速开始',
    children: [
      { id: 'auth', label: '认证方式' },
      { id: 'chat-completions', label: 'Chat Completions' },
      { id: 'anthropic-messages', label: 'Anthropic Messages' },
      { id: 'models', label: '模型列表' },
    ],
  },
  { id: 'claude-code', label: 'Claude Code 安装' },
  { id: 'codex', label: 'CodeX 安装' },
  { id: 'gemini-cli', label: 'Gemini CLI 安装' },
  { id: 'apikey', label: 'API Key 管理' },
  { id: 'billing', label: '计费与用量' },
  { id: 'rate-limit', label: '速率限制' },
]

function flatSections(items: Section[]): Section[] {
  return items.flatMap(s => [s, ...(s.children ? flatSections(s.children) : [])])
}

function findParentId(items: Section[], childId: string): string | null {
  for (const s of items) {
    if (s.children?.some(c => c.id === childId)) return s.id
  }
  return null
}

function CodeBlock({ lang, children }: { lang: string; children: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(children)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <div className="ag-docs-code-block">
      <div className="ag-docs-code-header">
        <span className="ag-docs-code-lang">{lang}</span>
        <button className="ag-docs-code-copy" onClick={copy}>
          <span className="material-symbols-outlined">{copied ? 'check' : 'content_copy'}</span>
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="ag-docs-code-body">{children}</pre>
    </div>
  )
}

const platforms = ['macOS', 'Windows', 'Linux'] as const
type Platform = typeof platforms[number]

function PlatformTabs({ children }: { children: Record<Platform, React.ReactNode> }) {
  const [active, setActive] = useState<Platform>('macOS')
  return (
    <div>
      <div className="ag-docs-tabs">
        {platforms.map((p) => (
          <button
            key={p}
            className={`ag-docs-tab${active === p ? ' ag-docs-tab-active' : ''}`}
            onClick={() => setActive(p)}
          >
            {p}
          </button>
        ))}
      </div>
      <div className="ag-docs-tab-panel">{children[active]}</div>
    </div>
  )
}

function InstallHero({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="ag-docs-install-hero">
      <h3 className="ag-docs-install-hero-title">{title}</h3>
      <p className="ag-docs-install-hero-desc">{desc}</p>
      <div className="ag-docs-install-steps-row">
        <span className="ag-docs-install-step-badge"><span className="ag-docs-install-step-num">1</span>安装 CLI</span>
        <span className="ag-docs-install-step-badge"><span className="ag-docs-install-step-num">2</span>配置密钥</span>
        <span className="ag-docs-install-step-badge"><span className="ag-docs-install-step-num">3</span>开始编程</span>
      </div>
    </div>
  )
}

const Docs: React.FC = () => {
  const navigate = useNavigate()
  const [activeId, setActiveId] = useState('overview')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ quickstart: true })

  const toggleExpand = useCallback((id: string) => {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }))
  }, [])

  const scrollTo = useCallback((id: string) => {
    const el = document.getElementById(id)
    if (!el) return

    // Nav is sticky at top: 0 with 80px height — offset so heading lands below it.
    const top = el.getBoundingClientRect().top + window.scrollY - 100
    window.scrollTo({ top, behavior: 'smooth' })
    setActiveId(id)
  }, [])

  useEffect(() => {
    const parentId = findParentId(sections, activeId)
    if (parentId) {
      setExpanded(prev => prev[parentId] ? prev : { ...prev, [parentId]: true })
    }
  }, [activeId])

  useEffect(() => {
    const all = flatSections(sections)
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveId(entry.target.id)
            break
          }
        }
      },
      { rootMargin: '-100px 0px -60% 0px', threshold: 0 }
    )
    for (const s of all) {
      const el = document.getElementById(s.id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const hash = window.location.hash.replace('#', '')
    if (hash) {
      setTimeout(() => scrollTo(hash), 100)
    }
  }, [scrollTo])

  return (
    <div className="ag-home ag-docs-page">
      <div className="ag-home-glow ag-home-glow-1" />
      <div className="ag-home-glow ag-home-glow-2" />

      {/* Nav */}
      <nav className="ag-home-nav" aria-label="主导航">
        <div className="ag-home-nav-inner">
          <a href="/home" className="ag-home-brand" style={{ textDecoration: 'none' }}>
            <span className="material-symbols-outlined ag-home-brand-icon" style={{ fontVariationSettings: "'FILL' 1" }} aria-hidden="true">hub</span>
            <span className="ag-home-brand-title">Any Gateway</span>
          </a>
          <div className="ag-home-nav-links">
            <a className="ag-home-nav-link ag-home-nav-link-active" href="/guide">开发文档</a>
            <a className="ag-home-nav-link" href="/pricing">价格对比</a>
            <a className="ag-home-nav-link" href="mailto:admin@example.com">联系我们</a>
            <button className="ag-btn ag-btn-primary" onClick={() => navigate('/login')}>
              管理控制台
              <span className="material-symbols-outlined" style={{ fontSize: 16 }} aria-hidden="true">arrow_forward</span>
            </button>
          </div>
        </div>
      </nav>

      <div className="ag-docs-body">
        {/* Sidebar */}
        <aside className="ag-docs-sidebar">
          <p className="ag-docs-sidebar-title">文档导航</p>
          <nav className="ag-docs-sidebar-nav">
            {sections.map((s) =>
              s.children ? (
                <div key={s.id} className="ag-docs-nav-group-wrap">
                  <a
                    className={`ag-docs-nav-item ag-docs-nav-group${activeId === s.id ? ' ag-docs-nav-item-active' : ''}`}
                    onClick={(e) => { e.preventDefault(); scrollTo(s.id) }}
                    href={`#${s.id}`}
                  >
                    <span>{s.label}</span>
                    <span
                      className={`material-symbols-outlined ag-docs-nav-group-arrow${expanded[s.id] ? '' : ' ag-docs-nav-group-arrow-closed'}`}
                      onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleExpand(s.id) }}
                      aria-hidden="true"
                    >
                      expand_more
                    </span>
                  </a>
                  <div
                    className="ag-docs-nav-children"
                    style={{ maxHeight: expanded[s.id] ? `${s.children.length * 40}px` : '0' }}
                  >
                    {s.children.map((c) => (
                      <a
                        key={c.id}
                        className={`ag-docs-nav-item ag-docs-nav-child${activeId === c.id ? ' ag-docs-nav-item-active' : ''}`}
                        onClick={(e) => { e.preventDefault(); scrollTo(c.id) }}
                        href={`#${c.id}`}
                      >
                        {c.label}
                      </a>
                    ))}
                  </div>
                </div>
              ) : (
                <a
                  key={s.id}
                  className={`ag-docs-nav-item${activeId === s.id ? ' ag-docs-nav-item-active' : ''}`}
                  onClick={(e) => { e.preventDefault(); scrollTo(s.id) }}
                  href={`#${s.id}`}
                >
                  {s.label}
                </a>
              )
            )}
          </nav>
        </aside>

        {/* Content */}
        <main className="ag-docs-content">

          {/* ── 概览 ── */}
          <section id="overview" className="ag-docs-section">
            <h2 className="ag-docs-section-title">API 文档</h2>
            <p className="ag-docs-section-desc">
              Any Gateway 提供统一的 API 接口，通过单一端点访问所有主流 AI 模型，内置 Key 管理、用量追踪和速率限制功能。
            </p>

            <h3 className="ag-docs-h3">API 地址</h3>
            <p className="ag-docs-p">所有 API 统一通过一个域名访问：</p>
            <div className="ag-docs-endpoint-url">
              https://your-gateway.com
            </div>

            <h3 className="ag-docs-h3">主要端点</h3>
            <div className="ag-docs-table-wrap">
              <table className="ag-docs-table">
                <thead>
                  <tr>
                    <th>类别</th>
                    <th>端点</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>模型推理</td>
                    <td><code>/v1/chat/completions</code></td>
                    <td>OpenAI 格式对话补全</td>
                  </tr>
                  <tr>
                    <td>模型推理</td>
                    <td><code>/v1/messages</code></td>
                    <td>Anthropic 格式消息接口</td>
                  </tr>
                  <tr>
                    <td>查询</td>
                    <td><code>/v1/models</code></td>
                    <td>查询可用模型列表</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="ag-docs-h3">核心概念</h3>
            <ul className="ag-docs-ul">
              <li>两种 API 协议，一个网关：<code className="ag-docs-inline-code">/v1/chat/completions</code>（OpenAI 兼容）和 <code className="ag-docs-inline-code">/v1/messages</code>（Anthropic 兼容）</li>
              <li>多供应商路由 — DeepSeek、Anthropic、OpenAI、Gemini、火山引擎等</li>
              <li>所有协议共享 API Key、余额和计费系统</li>
              <li>实时用量追踪和余额管理</li>
            </ul>

            <h3 className="ag-docs-h3">快速导航</h3>
            <div className="ag-docs-quick-nav">
              {[
                { id: 'quickstart', title: '快速开始', desc: '2 分钟完成首次 API 调用', icon: 'rocket_launch' },
                { id: 'chat-completions', title: 'Chat Completions (OpenAI)', desc: 'OpenAI 兼容的文本生成接口', icon: 'chat' },
                { id: 'anthropic-messages', title: 'Messages (Anthropic)', desc: '原生 Anthropic 协议，支持 Claude Code', icon: 'smart_toy' },
                { id: 'models', title: '模型列表', desc: '查看可用模型和价格', icon: 'view_list' },
                { id: 'billing', title: '计费与用量', desc: '追踪成本和管理余额', icon: 'payments' },
                { id: 'apikey', title: 'Key 管理', desc: '创建、配置 API Key', icon: 'key' },
              ].map((c) => (
                <a key={c.id} className="ag-docs-quick-card" onClick={(e) => { e.preventDefault(); scrollTo(c.id) }} href={`#${c.id}`}>
                  <span className="ag-docs-quick-card-title">
                    {c.title}
                    <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
                  </span>
                  <span className="ag-docs-quick-card-desc">{c.desc}</span>
                </a>
              ))}
            </div>
          </section>

          {/* ── 快速开始 ── */}
          <section id="quickstart" className="ag-docs-section">
            <h2 className="ag-docs-section-title">快速开始</h2>
            <p className="ag-docs-section-desc">几分钟内完成首次 API 调用。支持 OpenAI SDK、curl 等多种方式。</p>

            <ol className="ag-docs-steps">
              <li>
                <strong>获取 API Key</strong>
                <p className="ag-docs-p">在 <a href="/login">管理控制台</a> 创建或获取你的 API Key。</p>
              </li>
              <li>
                <strong>安装 OpenAI SDK</strong>
                <CodeBlock lang="bash">pip install openai</CodeBlock>
              </li>
              <li>
                <strong>发起第一个请求</strong>
              </li>
            </ol>

            <h4 className="ag-docs-h4">使用 Python</h4>
            <CodeBlock lang="python">{`from openai import OpenAI

client = OpenAI(
    base_url="https://your-gateway.com/v1",
    api_key="gw-your-key-here",
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)

print(response.choices[0].message.content)`}</CodeBlock>

            <h4 className="ag-docs-h4">使用 curl</h4>
            <CodeBlock lang="bash">{`curl -X POST https://your-gateway.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer gw-your-key-here" \\
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Hello!"}],
    "max_tokens": 100
  }'`}</CodeBlock>

            <h4 className="ag-docs-h4">使用 JavaScript</h4>
            <CodeBlock lang="javascript">{`import OpenAI from 'openai'

const client = new OpenAI({
  baseURL: 'https://your-gateway.com/v1',
  apiKey: 'gw-your-key-here',
})

const response = await client.chat.completions.create({
  model: 'deepseek-chat',
  messages: [{ role: 'user', content: 'Hello!' }],
})

console.log(response.choices[0].message.content)`}</CodeBlock>

            <h3 className="ag-docs-h3">查询余额</h3>
            <CodeBlock lang="bash">{`curl https://your-gateway.com/v1/auth/key \\
  -H "Authorization: Bearer gw-your-key-here"`}</CodeBlock>

            <h3 className="ag-docs-h3">可用模型</h3>
            <p className="ag-docs-p">获取当前可用的模型列表：</p>
            <CodeBlock lang="bash">{`curl https://your-gateway.com/v1/models \\
  -H "Authorization: Bearer gw-your-key-here"`}</CodeBlock>
          </section>

          {/* ── 认证方式 ── */}
          <section id="auth" className="ag-docs-section">
            <h2 className="ag-docs-section-title">认证方式</h2>
            <p className="ag-docs-section-desc">所有 API 请求需要通过 API Key 进行身份验证。</p>

            <h3 className="ag-docs-h3">请求头格式</h3>
            <p className="ag-docs-p">
              在每个请求的 <code className="ag-docs-inline-code">Authorization</code> 头中携带你的 API Key：
            </p>
            <CodeBlock lang="http">{`Authorization: Bearer gw-your-key-here`}</CodeBlock>

            <h3 className="ag-docs-h3">Key 格式</h3>
            <p className="ag-docs-p">
              API Key 以 <code className="ag-docs-inline-code">gw-</code> 前缀开头，后跟一串随机字符。示例：
            </p>
            <CodeBlock lang="text">{`gw-a1b2c3d4e5f6g7h8i9j0...`}</CodeBlock>

            <div className="ag-docs-callout ag-docs-callout-warning">
              <span className="material-symbols-outlined" aria-hidden="true">warning</span>
              <div>
                <strong>安全提示：</strong>请勿在客户端代码或公开仓库中暴露 API Key。建议通过环境变量或密钥管理服务注入。
              </div>
            </div>

            <h3 className="ag-docs-h3">SDK 配置示例</h3>
            <h4 className="ag-docs-h4">OpenAI SDK（Python）</h4>
            <CodeBlock lang="python">{`from openai import OpenAI

client = OpenAI(
    base_url="https://your-gateway.com/v1",
    api_key="gw-your-key-here",  # 建议使用 os.environ["GATEWAY_API_KEY"]
)`}</CodeBlock>

            <h4 className="ag-docs-h4">Anthropic SDK（Python）</h4>
            <CodeBlock lang="python">{`from anthropic import Anthropic

client = Anthropic(
    base_url="https://your-gateway.com",
    api_key="gw-your-key-here",
)`}</CodeBlock>
          </section>

          {/* ── Chat Completions ── */}
          <section id="chat-completions" className="ag-docs-section">
            <h2 className="ag-docs-section-title">Chat Completions</h2>
            <p className="ag-docs-section-desc">
              完全兼容 OpenAI <code className="ag-docs-inline-code">/v1/chat/completions</code> 端点，可直接使用 OpenAI SDK 或 HTTP 客户端。
            </p>

            <h3 className="ag-docs-h3">端点</h3>
            <div className="ag-docs-endpoint-url">
              <span className="ag-docs-method ag-docs-method-post">POST</span>
              https://your-gateway.com/v1/chat/completions
            </div>

            <h3 className="ag-docs-h3">请求示例</h3>
            <CodeBlock lang="json">{`{
  "model": "deepseek-chat",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What is the capital of France?"}
  ],
  "max_tokens": 100,
  "temperature": 0.7,
  "stream": false
}`}</CodeBlock>

            <h3 className="ag-docs-h3">参数说明</h3>
            <div className="ag-docs-table-wrap">
              <table className="ag-docs-table">
                <thead>
                  <tr>
                    <th>参数</th>
                    <th>类型</th>
                    <th>必填</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><code>model</code></td>
                    <td><span className="ag-docs-param-type">string</span></td>
                    <td><span className="ag-docs-param-required">必填</span></td>
                    <td>模型名称，如 <code className="ag-docs-inline-code">deepseek-chat</code>、<code className="ag-docs-inline-code">claude-4-sonnet</code></td>
                  </tr>
                  <tr>
                    <td><code>messages</code></td>
                    <td><span className="ag-docs-param-type">array</span></td>
                    <td><span className="ag-docs-param-required">必填</span></td>
                    <td>对话消息数组</td>
                  </tr>
                  <tr>
                    <td><code>max_tokens</code></td>
                    <td><span className="ag-docs-param-type">integer</span></td>
                    <td><span className="ag-docs-param-optional">可选</span></td>
                    <td>最大生成 Token 数</td>
                  </tr>
                  <tr>
                    <td><code>temperature</code></td>
                    <td><span className="ag-docs-param-type">number</span></td>
                    <td><span className="ag-docs-param-optional">可选</span></td>
                    <td>采样温度 0-2，默认 1</td>
                  </tr>
                  <tr>
                    <td><code>stream</code></td>
                    <td><span className="ag-docs-param-type">boolean</span></td>
                    <td><span className="ag-docs-param-optional">可选</span></td>
                    <td>是否开启流式输出</td>
                  </tr>
                  <tr>
                    <td><code>top_p</code></td>
                    <td><span className="ag-docs-param-type">number</span></td>
                    <td><span className="ag-docs-param-optional">可选</span></td>
                    <td>核采样参数，默认 1</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="ag-docs-h3">响应示例</h3>
            <CodeBlock lang="json">{`{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "deepseek-chat",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "The capital of France is Paris."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 8,
    "total_tokens": 28
  }
}`}</CodeBlock>

            <h3 className="ag-docs-h3">流式响应</h3>
            <p className="ag-docs-p">设置 <code className="ag-docs-inline-code">stream: true</code> 启用 Server-Sent Events (SSE) 流式输出：</p>
            <CodeBlock lang="bash">{`curl -X POST https://your-gateway.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer gw-your-key-here" \\
  -d '{
    "model": "deepseek-chat",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'`}</CodeBlock>

            <h3 className="ag-docs-h3">模型路由</h3>
            <div className="ag-docs-callout ag-docs-callout-info">
              <span className="material-symbols-outlined" aria-hidden="true">info</span>
              <div>
                请求中的 <code className="ag-docs-inline-code">model</code> 字段决定路由：网关会自动将请求转发到提供该模型的上游供应商。同一个 Key 可以调用所有已配置的模型。
              </div>
            </div>
          </section>

          {/* ── Anthropic Messages ── */}
          <section id="anthropic-messages" className="ag-docs-section">
            <h2 className="ag-docs-section-title">Anthropic Messages</h2>
            <p className="ag-docs-section-desc">
              原生兼容 Anthropic <code className="ag-docs-inline-code">/v1/messages</code> 端点，可直接使用 Anthropic SDK 或 Claude Code。
            </p>

            <h3 className="ag-docs-h3">端点</h3>
            <div className="ag-docs-endpoint-url">
              <span className="ag-docs-method ag-docs-method-post">POST</span>
              https://your-gateway.com/v1/messages
            </div>

            <h3 className="ag-docs-h3">请求示例</h3>
            <CodeBlock lang="json">{`{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 1024,
  "messages": [
    {"role": "user", "content": "Explain quantum computing in simple terms."}
  ]
}`}</CodeBlock>

            <h3 className="ag-docs-h3">响应示例</h3>
            <CodeBlock lang="json">{`{
  "id": "msg_abc123",
  "type": "message",
  "role": "assistant",
  "content": [
    {
      "type": "text",
      "text": "Quantum computing uses quantum bits..."
    }
  ],
  "model": "claude-sonnet-4-20250514",
  "stop_reason": "end_turn",
  "usage": {
    "input_tokens": 12,
    "output_tokens": 64
  }
}`}</CodeBlock>

            <h3 className="ag-docs-h3">配置 Claude Code</h3>
            <p className="ag-docs-p">在 Claude Code 配置中设置自定义端点：</p>
            <CodeBlock lang="json">{`// ~/.claude/settings.json
{
  "apiBaseUrl": "https://your-gateway.com",
  "apiKey": "gw-your-key-here"
}`}</CodeBlock>

            <h3 className="ag-docs-h3">配置 Anthropic SDK</h3>
            <CodeBlock lang="python">{`from anthropic import Anthropic

client = Anthropic(
    base_url="https://your-gateway.com",
    api_key="gw-your-key-here",
)

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude!"}
    ],
)

print(message.content[0].text)`}</CodeBlock>

            <div className="ag-docs-callout ag-docs-callout-info">
              <span className="material-symbols-outlined" aria-hidden="true">info</span>
              <div>
                Anthropic Messages 端点同样支持流式输出，使用 <code className="ag-docs-inline-code">stream: true</code> 参数即可启用 SSE。
              </div>
            </div>
          </section>

          {/* ── Claude Code 安装 ── */}
          <section id="claude-code" className="ag-docs-section">
            <h2 className="ag-docs-section-title">Claude Code 安装</h2>
            <p className="ag-docs-section-desc">
              Anthropic 官方 CLI 工具，在终端中使用 Claude 进行 AI 辅助编程。
            </p>

            <InstallHero
              title="Claude Code"
              desc="Anthropic 官方命令行工具，Claude Sonnet / Opus 驱动"
            />

            <PlatformTabs>
              {{
                macOS: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>macOS 10.15 (Catalina) 或更高版本</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <p className="ag-docs-p">推荐使用 Homebrew：</p>
                    <CodeBlock lang="bash">{`# 安装 Homebrew（如果未安装）
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 安装 Node.js
brew install node

# 验证安装
node --version
npm --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 Claude Code CLI</h4>
                    <CodeBlock lang="bash">{`npm install -g @anthropic-ai/claude-code

# 验证安装
claude --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后编辑配置文件：
                    </p>
                    <p className="ag-docs-p">
                      配置位置：<code className="ag-docs-inline-code">~/.claude/settings.json</code>
                    </p>
                    <CodeBlock lang="json">{`{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "gw-your-key-here",
    "ANTHROPIC_BASE_URL": "https://your-gateway.com"
  }
}`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-warning">
                      <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                      <div>
                        <strong>注意：</strong>请将 <code className="ag-docs-inline-code">ANTHROPIC_AUTH_TOKEN</code> 替换为你在管理控制台生成的 API Key，修改后需重启 Claude Code 才生效。
                      </div>
                    </div>

                    <h4 className="ag-docs-h4">4. 启动 Claude Code</h4>
                    <CodeBlock lang="bash">{`cd your-project-folder
claude`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-info">
                      <span className="material-symbols-outlined" aria-hidden="true">info</span>
                      <div>
                        首次启动需完成初始化：选择主题 → 确认安全须知 → 配置 Terminal → 信任工作目录 → 开始编程。
                      </div>
                    </div>
                  </>
                ),
                Windows: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>Windows 10 或 Windows 11</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <p className="ag-docs-p">推荐使用 Winget：</p>
                    <CodeBlock lang="powershell">winget install OpenJS.NodeJS.LTS</CodeBlock>
                    <p className="ag-docs-p">也可以使用 Chocolatey 或 Scoop：</p>
                    <CodeBlock lang="powershell">{`# Chocolatey
choco install nodejs-lts

# Scoop
scoop install nodejs-lts`}</CodeBlock>
                    <p className="ag-docs-p">验证安装：</p>
                    <CodeBlock lang="powershell">{`node --version
npm --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 Claude Code CLI</h4>
                    <p className="ag-docs-p">以管理员身份运行 PowerShell：</p>
                    <CodeBlock lang="powershell">{`npm install -g @anthropic-ai/claude-code

# 验证安装
claude --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后编辑配置文件：
                    </p>
                    <p className="ag-docs-p">
                      配置位置：<code className="ag-docs-inline-code">%USERPROFILE%\.claude\settings.json</code>
                    </p>
                    <CodeBlock lang="json">{`{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "gw-your-key-here",
    "ANTHROPIC_BASE_URL": "https://your-gateway.com"
  }
}`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-warning">
                      <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                      <div>
                        <strong>注意：</strong>请将 <code className="ag-docs-inline-code">ANTHROPIC_AUTH_TOKEN</code> 替换为你在管理控制台生成的 API Key，修改后需重启 Claude Code 才生效。
                      </div>
                    </div>

                    <h4 className="ag-docs-h4">4. 启动 Claude Code</h4>
                    <CodeBlock lang="powershell">{`cd your-project-folder
claude`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-info">
                      <span className="material-symbols-outlined" aria-hidden="true">info</span>
                      <div>
                        首次启动需完成初始化：选择主题 → 确认安全须知 → 配置 Terminal → 信任工作目录 → 开始编程。
                      </div>
                    </div>
                  </>
                ),
                Linux: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>Ubuntu 18.04+ / CentOS 7+ / Debian 9+</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <p className="ag-docs-p"><strong>Ubuntu / Debian：</strong></p>
                    <CodeBlock lang="bash">{`curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs`}</CodeBlock>
                    <p className="ag-docs-p"><strong>CentOS / RHEL / Fedora：</strong></p>
                    <CodeBlock lang="bash">{`sudo dnf install nodejs npm
# 或者
sudo yum install nodejs npm`}</CodeBlock>
                    <p className="ag-docs-p"><strong>Arch Linux：</strong></p>
                    <CodeBlock lang="bash">sudo pacman -S nodejs npm</CodeBlock>
                    <p className="ag-docs-p">验证安装：</p>
                    <CodeBlock lang="bash">{`node --version
npm --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 Claude Code CLI</h4>
                    <CodeBlock lang="bash">{`npm install -g @anthropic-ai/claude-code

# 验证安装
claude --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后编辑配置文件：
                    </p>
                    <p className="ag-docs-p">
                      配置位置：<code className="ag-docs-inline-code">~/.claude/settings.json</code>
                    </p>
                    <CodeBlock lang="json">{`{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "gw-your-key-here",
    "ANTHROPIC_BASE_URL": "https://your-gateway.com"
  }
}`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-warning">
                      <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                      <div>
                        <strong>注意：</strong>请将 <code className="ag-docs-inline-code">ANTHROPIC_AUTH_TOKEN</code> 替换为你在管理控制台生成的 API Key，修改后需重启 Claude Code 才生效。
                      </div>
                    </div>

                    <h4 className="ag-docs-h4">4. 启动 Claude Code</h4>
                    <CodeBlock lang="bash">{`cd your-project-folder
claude`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-info">
                      <span className="material-symbols-outlined" aria-hidden="true">info</span>
                      <div>
                        首次启动需完成初始化：选择主题 → 确认安全须知 → 配置 Terminal → 信任工作目录 → 开始编程。
                      </div>
                    </div>
                  </>
                ),
              }}
            </PlatformTabs>
          </section>

          {/* ── CodeX 安装 ── */}
          <section id="codex" className="ag-docs-section">
            <h2 className="ag-docs-section-title">CodeX 安装</h2>
            <p className="ag-docs-section-desc">
              OpenAI 官方 CLI 工具，在终端中使用 GPT 系列模型进行 AI 辅助编程。
            </p>

            <InstallHero
              title="CodeX"
              desc="OpenAI 官方命令行工具，GPT 系列模型驱动"
            />

            <PlatformTabs>
              {{
                macOS: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>macOS 10.15 (Catalina) 或更高版本</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <CodeBlock lang="bash">{`brew install node

# 验证安装
node --version
npm --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 CodeX CLI</h4>
                    <CodeBlock lang="bash">{`npm install -g @openai/codex@latest

# 验证安装
codex --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后创建配置文件：
                    </p>
                    <CodeBlock lang="bash">{`mkdir -p ~/.codex
cd ~/.codex`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">config.toml</code>：</p>
                    <CodeBlock lang="toml">{`model_provider = "anygateway"
model = "gpt-4o"
model_reasoning_effort = "xhigh"
network_access = "enabled"
disable_response_storage = true

[model_providers.anygateway]
name = "OpenAI"
base_url = "https://your-gateway.com/v1"
wire_api = "responses"
requires_openai_auth = true`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">auth.json</code>：</p>
                    <CodeBlock lang="json">{`{
  "OPENAI_API_KEY": "gw-your-key-here"
}`}</CodeBlock>

                    <h4 className="ag-docs-h4">4. 启动 CodeX</h4>
                    <CodeBlock lang="bash">{`cd your-project-folder
codex`}</CodeBlock>
                  </>
                ),
                Windows: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>Windows 10 或 Windows 11</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <CodeBlock lang="powershell">winget install OpenJS.NodeJS.LTS</CodeBlock>
                    <p className="ag-docs-p">验证安装：</p>
                    <CodeBlock lang="powershell">{`node --version
npm --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 CodeX CLI</h4>
                    <p className="ag-docs-p">以管理员身份运行 PowerShell：</p>
                    <CodeBlock lang="powershell">{`npm install -g @openai/codex@latest

# 验证安装
codex --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后创建配置文件夹和文件：
                    </p>
                    <CodeBlock lang="powershell">{`mkdir %USERPROFILE%\\.codex
cd %USERPROFILE%\\.codex`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">config.toml</code>：</p>
                    <CodeBlock lang="toml">{`model_provider = "anygateway"
model = "gpt-4o"
model_reasoning_effort = "xhigh"
network_access = "enabled"
disable_response_storage = true

[model_providers.anygateway]
name = "OpenAI"
base_url = "https://your-gateway.com/v1"
wire_api = "responses"
requires_openai_auth = true`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">auth.json</code>：</p>
                    <CodeBlock lang="json">{`{
  "OPENAI_API_KEY": "gw-your-key-here"
}`}</CodeBlock>

                    <h4 className="ag-docs-h4">4. 启动 CodeX</h4>
                    <CodeBlock lang="powershell">{`cd your-project-folder
codex`}</CodeBlock>
                  </>
                ),
                Linux: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>Ubuntu 18.04+ / CentOS 7+ / Debian 9+</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <p className="ag-docs-p"><strong>Ubuntu / Debian：</strong></p>
                    <CodeBlock lang="bash">{`curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt-get install -y nodejs`}</CodeBlock>
                    <p className="ag-docs-p">验证安装：</p>
                    <CodeBlock lang="bash">{`node --version
npm --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 CodeX CLI</h4>
                    <CodeBlock lang="bash">{`npm install -g @openai/codex@latest

# 验证安装
codex --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后创建配置文件：
                    </p>
                    <CodeBlock lang="bash">{`mkdir -p ~/.codex
cd ~/.codex`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">config.toml</code>：</p>
                    <CodeBlock lang="toml">{`model_provider = "anygateway"
model = "gpt-4o"
model_reasoning_effort = "xhigh"
network_access = "enabled"
disable_response_storage = true

[model_providers.anygateway]
name = "OpenAI"
base_url = "https://your-gateway.com/v1"
wire_api = "responses"
requires_openai_auth = true`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">auth.json</code>：</p>
                    <CodeBlock lang="json">{`{
  "OPENAI_API_KEY": "gw-your-key-here"
}`}</CodeBlock>

                    <h4 className="ag-docs-h4">4. 启动 CodeX</h4>
                    <CodeBlock lang="bash">{`cd your-project-folder
codex`}</CodeBlock>
                  </>
                ),
              }}
            </PlatformTabs>
          </section>

          {/* ── Gemini CLI 安装 ── */}
          <section id="gemini-cli" className="ag-docs-section">
            <h2 className="ag-docs-section-title">Gemini CLI 安装</h2>
            <p className="ag-docs-section-desc">
              Google 官方 CLI 工具，在终端中使用 Gemini 系列模型进行 AI 辅助编程。
            </p>

            <InstallHero
              title="Gemini CLI"
              desc="Google AI 编程助手，Gemini 2.5 Pro 驱动"
            />

            <PlatformTabs>
              {{
                macOS: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>macOS 10.15 (Catalina) 或更高版本</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <CodeBlock lang="bash">brew install node</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 Gemini CLI</h4>
                    <CodeBlock lang="bash">npm install -g @google/gemini-cli</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后创建配置文件：
                    </p>
                    <p className="ag-docs-p">
                      配置位置：<code className="ag-docs-inline-code">~/.gemini/</code>
                    </p>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">.env</code> 文件：</p>
                    <CodeBlock lang="bash">{`GOOGLE_GEMINI_BASE_URL=https://your-gateway.com
GEMINI_API_KEY=gw-your-key-here
GEMINI_MODEL=gemini-2.5-pro`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">settings.json</code> 文件：</p>
                    <CodeBlock lang="json">{`{
  "ide": {
    "enabled": true
  },
  "security": {
    "auth": {
      "selectedType": "gemini-api-key"
    }
  }
}`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-warning">
                      <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                      <div>
                        <strong>注意：</strong>请将 <code className="ag-docs-inline-code">GEMINI_API_KEY</code> 替换为你在管理控制台生成的 API Key，修改后需重启 Gemini CLI 才生效。
                      </div>
                    </div>

                    <h4 className="ag-docs-h4">4. 启动 Gemini CLI</h4>
                    <CodeBlock lang="bash">gemini</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-info">
                      <span className="material-symbols-outlined" aria-hidden="true">info</span>
                      <div>
                        Gemini CLI 支持超大上下文窗口（1M tokens）、Agent Mode 自动规划任务、Google Search 实时联网等特性。
                      </div>
                    </div>
                  </>
                ),
                Windows: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>Windows 10 或 Windows 11</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <CodeBlock lang="powershell">winget install OpenJS.NodeJS.LTS</CodeBlock>
                    <p className="ag-docs-p">验证安装：</p>
                    <CodeBlock lang="powershell">{`node --version
npm --version`}</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 Gemini CLI</h4>
                    <CodeBlock lang="powershell">npm install -g @google/gemini-cli</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后在 <code className="ag-docs-inline-code">%USERPROFILE%\.gemini\</code> 目录下创建配置文件：
                    </p>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">.env</code> 文件：</p>
                    <CodeBlock lang="bash">{`GOOGLE_GEMINI_BASE_URL=https://your-gateway.com
GEMINI_API_KEY=gw-your-key-here
GEMINI_MODEL=gemini-2.5-pro`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">settings.json</code> 文件：</p>
                    <CodeBlock lang="json">{`{
  "ide": {
    "enabled": true
  },
  "security": {
    "auth": {
      "selectedType": "gemini-api-key"
    }
  }
}`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-warning">
                      <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                      <div>
                        <strong>注意：</strong>请将 <code className="ag-docs-inline-code">GEMINI_API_KEY</code> 替换为你在管理控制台生成的 API Key，修改后需重启 Gemini CLI 才生效。
                      </div>
                    </div>

                    <h4 className="ag-docs-h4">4. 启动 Gemini CLI</h4>
                    <CodeBlock lang="powershell">gemini</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-info">
                      <span className="material-symbols-outlined" aria-hidden="true">info</span>
                      <div>
                        Gemini CLI 支持超大上下文窗口（1M tokens）、Agent Mode 自动规划任务、Google Search 实时联网等特性。
                      </div>
                    </div>
                  </>
                ),
                Linux: (
                  <>
                    <div className="ag-docs-sysreq">
                      <p className="ag-docs-sysreq-title">系统要求</p>
                      <ul>
                        <li>Ubuntu 18.04+ / CentOS 7+ / Debian 9+</li>
                        <li>Node.js 18+</li>
                      </ul>
                    </div>

                    <h4 className="ag-docs-h4">1. 安装 Node.js</h4>
                    <p className="ag-docs-p"><strong>Ubuntu / Debian：</strong></p>
                    <CodeBlock lang="bash">sudo apt update && sudo apt install nodejs npm</CodeBlock>

                    <h4 className="ag-docs-h4">2. 安装 Gemini CLI</h4>
                    <CodeBlock lang="bash">npm install -g @google/gemini-cli</CodeBlock>

                    <h4 className="ag-docs-h4">3. 配置 Any Gateway API</h4>
                    <p className="ag-docs-p">
                      在 <a href="/login">管理控制台</a> 创建 API Key，然后在 <code className="ag-docs-inline-code">~/.gemini/</code> 目录下创建配置文件：
                    </p>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">.env</code> 文件：</p>
                    <CodeBlock lang="bash">{`GOOGLE_GEMINI_BASE_URL=https://your-gateway.com
GEMINI_API_KEY=gw-your-key-here
GEMINI_MODEL=gemini-2.5-pro`}</CodeBlock>
                    <p className="ag-docs-p">创建 <code className="ag-docs-inline-code">settings.json</code> 文件：</p>
                    <CodeBlock lang="json">{`{
  "ide": {
    "enabled": true
  },
  "security": {
    "auth": {
      "selectedType": "gemini-api-key"
    }
  }
}`}</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-warning">
                      <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                      <div>
                        <strong>注意：</strong>请将 <code className="ag-docs-inline-code">GEMINI_API_KEY</code> 替换为你在管理控制台生成的 API Key，修改后需重启 Gemini CLI 才生效。
                      </div>
                    </div>

                    <h4 className="ag-docs-h4">4. 启动 Gemini CLI</h4>
                    <CodeBlock lang="bash">gemini</CodeBlock>
                    <div className="ag-docs-callout ag-docs-callout-info">
                      <span className="material-symbols-outlined" aria-hidden="true">info</span>
                      <div>
                        Gemini CLI 支持超大上下文窗口（1M tokens）、Agent Mode 自动规划任务、Google Search 实时联网等特性。
                      </div>
                    </div>
                  </>
                ),
              }}
            </PlatformTabs>
          </section>

          {/* ── 模型列表 ── */}
          <section id="models" className="ag-docs-section">
            <h2 className="ag-docs-section-title">模型列表</h2>
            <p className="ag-docs-section-desc">查询当前可用的模型，了解网关如何进行模型路由。</p>

            <h3 className="ag-docs-h3">查询端点</h3>
            <div className="ag-docs-endpoint-url">
              <span className="ag-docs-method ag-docs-method-get">GET</span>
              https://your-gateway.com/v1/models
            </div>

            <h3 className="ag-docs-h3">响应示例</h3>
            <CodeBlock lang="json">{`{
  "object": "list",
  "data": [
    {
      "id": "deepseek-chat",
      "object": "model",
      "owned_by": "deepseek"
    },
    {
      "id": "claude-sonnet-4-20250514",
      "object": "model",
      "owned_by": "anthropic"
    },
    {
      "id": "gpt-4o",
      "object": "model",
      "owned_by": "openai"
    }
  ]
}`}</CodeBlock>

            <h3 className="ag-docs-h3">支持的模型供应商</h3>
            <div className="ag-docs-table-wrap">
              <table className="ag-docs-table">
                <thead>
                  <tr>
                    <th>供应商</th>
                    <th>代表模型</th>
                    <th>协议</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td>DeepSeek</td><td><code>deepseek-chat</code>, <code>deepseek-reasoner</code></td><td>OpenAI 兼容</td></tr>
                  <tr><td>Anthropic</td><td><code>claude-sonnet-4-20250514</code>, <code>claude-opus-4-20250514</code></td><td>OpenAI / Anthropic</td></tr>
                  <tr><td>OpenAI</td><td><code>gpt-4o</code>, <code>o3</code></td><td>OpenAI 兼容</td></tr>
                  <tr><td>Google</td><td><code>gemini-2.5-pro</code>, <code>gemini-2.5-flash</code></td><td>OpenAI 兼容</td></tr>
                  <tr><td>Alibaba</td><td><code>qwen-max</code>, <code>qwen-plus</code></td><td>OpenAI 兼容</td></tr>
                  <tr><td>Volcengine</td><td><code>doubao-pro</code></td><td>OpenAI 兼容</td></tr>
                </tbody>
              </table>
            </div>

            <h3 className="ag-docs-h3">模型路由机制</h3>
            <p className="ag-docs-p">
              网关根据请求体中的 <code className="ag-docs-inline-code">model</code> 字段自动路由到对应的上游供应商。
              管理员可以为不同分组配置可用模型和优先级。
            </p>
            <div className="ag-docs-callout ag-docs-callout-info">
              <span className="material-symbols-outlined" aria-hidden="true">info</span>
              <div>
                模型列表可能因你所在的用户分组而异。如果找不到某个模型，请联系管理员确认分组权限。
              </div>
            </div>
          </section>

          {/* ── API Key 管理 ── */}
          <section id="apikey" className="ag-docs-section">
            <h2 className="ag-docs-section-title">API Key 管理</h2>
            <p className="ag-docs-section-desc">管理你的 API Key，控制访问权限和预算。</p>

            <h3 className="ag-docs-h3">获取 Key</h3>
            <p className="ag-docs-p">
              登录 <a href="/login">管理控制台</a> 后，在「API Keys」页面创建新的 Key。每个 Key 可以独立设置：
            </p>
            <ul className="ag-docs-ul">
              <li><strong>名称</strong> — 便于识别用途（如「生产环境」「测试」）</li>
              <li><strong>额度</strong> — 设置最大消费额度，防止意外超支</li>
              <li><strong>过期时间</strong> — 设置自动过期时间</li>
            </ul>

            <h3 className="ag-docs-h3">查询 Key 信息</h3>
            <div className="ag-docs-endpoint-url">
              <span className="ag-docs-method ag-docs-method-get">GET</span>
              https://your-gateway.com/v1/auth/key
            </div>
            <CodeBlock lang="bash">{`curl https://your-gateway.com/v1/auth/key \\
  -H "Authorization: Bearer gw-your-key-here"`}</CodeBlock>

            <h3 className="ag-docs-h3">安全建议</h3>
            <div className="ag-docs-callout ag-docs-callout-warning">
              <span className="material-symbols-outlined" aria-hidden="true">shield</span>
              <div>
                <ul className="ag-docs-ul" style={{ margin: 0 }}>
                  <li>为不同环境（开发/测试/生产）使用独立的 Key</li>
                  <li>定期轮换 Key，及时删除不再使用的 Key</li>
                  <li>设置合理的额度上限，避免意外消费</li>
                  <li>不要在客户端代码中硬编码 Key</li>
                </ul>
              </div>
            </div>
          </section>

          {/* ── 计费与用量 ── */}
          <section id="billing" className="ag-docs-section">
            <h2 className="ag-docs-section-title">计费与用量</h2>
            <p className="ag-docs-section-desc">了解计费规则和如何追踪用量。</p>

            <h3 className="ag-docs-h3">计费模式</h3>
            <p className="ag-docs-p">
              按实际使用的 Token 数量计费，不同模型有不同的单价。支持 <strong>输入 Token</strong> 和 <strong>输出 Token</strong> 分开计价。
            </p>
            <ul className="ag-docs-ul">
              <li>每次 API 调用后，usage 字段会返回本次消耗的 Token 数</li>
              <li>计费精确到每次请求，实时扣减余额</li>
              <li>支持 Prompt Cache 优惠价格 — 缓存命中时按缓存价计费</li>
            </ul>

            <h3 className="ag-docs-h3">查看价格</h3>
            <p className="ag-docs-p">
              访问 <a href="/pricing">价格对比</a> 页面查看各模型的详细定价。
            </p>

            <h3 className="ag-docs-h3">用量追踪</h3>
            <p className="ag-docs-p">
              在管理控制台的「Dashboard」页面可以查看：
            </p>
            <ul className="ag-docs-ul">
              <li>总消费金额和剩余余额</li>
              <li>按模型分组的用量统计</li>
              <li>每次调用的详细日志（包含 Token 数、耗时、成本）</li>
            </ul>

            <h3 className="ag-docs-h3">充值与额度</h3>
            <p className="ag-docs-p">
              联系管理员进行充值或调整额度。支持消费券功能，管理员可以批量发放定额消费券。
            </p>
          </section>

          {/* ── 速率限制 ── */}
          <section id="rate-limit" className="ag-docs-section">
            <h2 className="ag-docs-section-title">速率限制</h2>
            <p className="ag-docs-section-desc">了解网关的多层限速机制，合理规划调用频率。</p>

            <h3 className="ag-docs-h3">限速层级</h3>
            <div className="ag-docs-table-wrap">
              <table className="ag-docs-table">
                <thead>
                  <tr>
                    <th>层级</th>
                    <th>维度</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Key 级别</td>
                    <td>每个 API Key</td>
                    <td>单个 Key 的请求频率限制</td>
                  </tr>
                  <tr>
                    <td>用户级别</td>
                    <td>每个用户</td>
                    <td>同一用户所有 Key 的总请求频率</td>
                  </tr>
                  <tr>
                    <td>分组级别</td>
                    <td>每个用户分组</td>
                    <td>同一分组内所有用户的总请求频率</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="ag-docs-h3">限速响应</h3>
            <p className="ag-docs-p">当请求触发速率限制时，API 返回 HTTP 429：</p>
            <CodeBlock lang="json">{`{
  "error": {
    "type": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Please try again later."
  }
}`}</CodeBlock>

            <h3 className="ag-docs-h3">最佳实践</h3>
            <ul className="ag-docs-ul">
              <li>实现指数退避重试策略（Exponential Backoff）</li>
              <li>使用流式输出减少并发连接数</li>
              <li>监控 API 响应头中的速率限制信息</li>
              <li>如需更高配额，联系管理员调整分组限速设置</li>
            </ul>
          </section>

        </main>
      </div>

      {/* Footer */}
      <footer className="ag-home-footer" aria-label="页脚">
        <div className="ag-home-section-inner ag-home-footer-inner">
          <div className="ag-home-footer-brand">
            <div className="ag-home-brand">
              <span className="material-symbols-outlined ag-home-brand-icon" style={{ fontVariationSettings: "'FILL' 1" }} aria-hidden="true">hub</span>
              <span className="ag-home-brand-title">Any Gateway</span>
            </div>
            <p className="ag-home-footer-tagline">企业级 AI 中转网关，聚合主流模型，统一管理用量、成本与权限。</p>
          </div>
          <div className="ag-home-footer-col">
            <h4 className="ag-home-footer-col-title">产品与服务</h4>
            <ul className="ag-home-footer-links">
              <li><a href="/guide">开发文档</a></li>
              <li><a href="/login">管理控制台</a></li>
              <li><a href="/pricing">价格对比</a></li>
            </ul>
          </div>
          <div className="ag-home-footer-col">
            <h4 className="ag-home-footer-col-title">支持</h4>
            <ul className="ag-home-footer-links">
              <li><a href="mailto:admin@example.com">联系我们</a></li>
              <li><a href="#">隐私政策</a></li>
              <li><a href="#">服务条款</a></li>
            </ul>
          </div>
        </div>
        <div className="ag-home-section-inner">
          <div className="ag-home-footer-bottom">
            <p className="ag-home-footer-copy">
              © {new Date().getFullYear()} Any Gateway AI Infrastructure. All rights reserved.
            </p>
            <div className="ag-home-footer-status">
              <span className="ag-home-footer-status-dot" aria-hidden="true" />
              系统运行正常
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default Docs
