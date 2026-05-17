import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import './index.css'

interface PriceRow {
  model_name: string
  unit: string
  price_per_unit: number
  context_length?: number
  vendor?: string
  stability?: string
}

interface ModelEntry {
  model_name: string
  vendor: string
  context_length?: number
  stability?: string
  input_token?: number
  output_token?: number
  cache_read_token?: number
}

interface GroupedModels {
  [vendor: string]: ModelEntry[]
}

function classifyVendor(row: PriceRow): string {
  if (row.vendor) return row.vendor
  const lower = row.model_name.toLowerCase()
  if (lower.includes('deepseek')) return 'DeepSeek'
  if (lower.includes('claude')) return 'Anthropic'
  if (lower.includes('gpt') || lower.includes('o1') || lower.includes('o3') || lower.includes('o4')) return 'OpenAI'
  if (lower.includes('gemini')) return 'Google'
  if (lower.includes('qwen')) return 'Alibaba'
  if (lower.includes('glm') || lower.includes('chatglm')) return 'Zhipu AI'
  if (lower.includes('doubao') || lower.includes('skylark')) return 'Volcengine'
  return 'Other'
}

function buildModels(rows: PriceRow[]): GroupedModels {
  const modelMap = new Map<string, ModelEntry>()
  for (const row of rows) {
    const vendor = classifyVendor(row)
    let entry = modelMap.get(row.model_name)
    if (!entry) {
      entry = { model_name: row.model_name, vendor }
      modelMap.set(row.model_name, entry)
    }
    if (row.context_length) entry.context_length = row.context_length
    if (row.stability) entry.stability = row.stability
    if (row.unit === 'input_token') entry.input_token = row.price_per_unit
    else if (row.unit === 'output_token') entry.output_token = row.price_per_unit
    else if (row.unit === 'cache_read_token') entry.cache_read_token = row.price_per_unit
  }
  const grouped: GroupedModels = {}
  for (const entry of modelMap.values()) {
    if (!grouped[entry.vendor]) grouped[entry.vendor] = []
    grouped[entry.vendor].push(entry)
  }
  for (const key of Object.keys(grouped)) {
    grouped[key].sort((a, b) => a.model_name.localeCompare(b.model_name))
  }
  return grouped
}

function formatCtx(n?: number) {
  if (!n) return '-'
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${Math.round(n / 1000)}K`
  return String(n)
}

function formatPrice(v?: number) {
  if (v == null) return '-'
  return `¥${v.toFixed(2)}`
}

const vendorOrder = ['DeepSeek', 'Anthropic', 'OpenAI', 'Google', 'Alibaba', 'Volcengine', 'Zhipu AI', 'Other']

const features = [
  {
    icon: 'hub',
    color: 'emerald',
    title: '模型聚合',
    desc: '一个 API Key 接入 OpenAI、Anthropic、Gemini 等主流模型，兼容 OpenAI 接口格式，零改造迁移。',
  },
  {
    icon: 'bolt',
    color: 'amber',
    title: '多协议支持',
    desc: '完整兼容 OpenAI Chat Completions 与 Anthropic Messages 接口，改 2 行配置即可切换，无需重写代码。',
  },
  {
    icon: 'payments',
    color: 'blue',
    title: '成本控制',
    desc: '分组限流、消费券、余额管理，精细化控制每个用户和团队的 AI 支出，按实际用量计费。',
  },
  {
    icon: 'bar_chart',
    color: 'purple',
    title: '用量审计',
    desc: '每次调用精确记录，实时查看用量与成本。支持按项目、按用户分组统计，月底对账清晰明了。',
  },
  {
    icon: 'admin_panel_settings',
    color: 'rose',
    title: '权限管理',
    desc: '给每个团队分配独立 Key，限制可用模型和预算。用户分组、权限分层，满足企业合规需求。',
  },
  {
    icon: 'shield',
    color: 'indigo',
    title: '私有部署',
    desc: 'Docker 一键部署到自有基础设施，数据完全在自己手里，满足安全合规与数据主权要求。',
  },
]

const modelLogos = ['DeepSeek', 'Anthropic', 'OpenAI', 'Gemini', 'Volcengine', 'Qwen']

const Home: React.FC = () => {
  const navigate = useNavigate()
  const [groups, setGroups] = useState<GroupedModels>({})
  const [modelsLoading, setModelsLoading] = useState(true)
  const [activeVendor, setActiveVendor] = useState('')

  useEffect(() => {
    axios
      .get('/public/model-prices')
      .then((res) => {
        const rows: PriceRow[] = res.data?.data ?? res.data ?? []
        const g = buildModels(rows)
        setGroups(g)
        const first = vendorOrder.find((v) => g[v]?.length)
        if (first) setActiveVendor(first)
      })
      .catch(() => {})
      .finally(() => setModelsLoading(false))
  }, [])

  const sortedVendors = vendorOrder.filter((v) => groups[v]?.length)
  const activeModels = activeVendor ? groups[activeVendor] ?? [] : []

  return (
    <div className="ag-home">
      {/* Ambient glow orbs */}
      <div className="ag-home-glow ag-home-glow-1" />
      <div className="ag-home-glow ag-home-glow-2" />

      {/* Nav */}
      <nav className="ag-home-nav" aria-label="主导航">
        <div className="ag-home-nav-inner">
          <div className="ag-home-brand">
            <span
              className="material-symbols-outlined ag-home-brand-icon"
              style={{ fontVariationSettings: "'FILL' 1" }}
              aria-hidden="true"
            >
              hub
            </span>
            <span className="ag-home-brand-title">Any Gateway</span>
          </div>
          <div className="ag-home-nav-links">
            <a className="ag-home-nav-link" href="/docs">开发文档</a>
            <a className="ag-home-nav-link" href="#features">核心能力</a>
            <a className="ag-home-nav-link" href="/pricing">价格对比</a>
            <a className="ag-home-nav-link" href="mailto:admin@example.com">联系我们</a>
            <button
              className="ag-btn ag-btn-primary"
              onClick={() => navigate('/login')}
            >
              管理控制台
              <span className="material-symbols-outlined" style={{ fontSize: 16 }} aria-hidden="true">
                arrow_forward
              </span>
            </button>
          </div>
        </div>
      </nav>

      <main>
        {/* Hero */}
        <section className="ag-home-hero" aria-labelledby="hero-heading">
          <div className="ag-home-section-inner ag-home-hero-inner">
            <div className="ag-home-hero-text">
              <div className="ag-home-status-badge">
                <span className="ag-home-status-dot" />
                兼容 OpenAI / Anthropic 接口格式
              </div>
              <h1 id="hero-heading" className="ag-home-hero-title">
                一个 API。<br />
                <span className="ag-home-gradient-text">连接所有 AI 模型。</span>
              </h1>
              <p className="ag-home-hero-subtitle">
                不用再为每个模型单独对接 API。一个接口，调用 DeepSeek、Claude、GPT 等所有主流模型。
                <strong>统一管理用量、成本与权限。</strong>
              </p>
              <div className="ag-home-hero-actions">
                <a
                  className="ag-btn ag-btn-primary"
                  href="#contact"
                  onClick={(e) => {
                    e.preventDefault()
                    document.getElementById('contact')?.scrollIntoView({ behavior: 'smooth' })
                  }}
                >
                  立即开始接入
                  <span className="material-symbols-outlined" style={{ fontSize: 16 }} aria-hidden="true">
                    arrow_forward
                  </span>
                </a>
                <button
                  className="ag-btn ag-btn-outline"
                  onClick={() => navigate('/login')}
                >
                  登录控制台
                </button>
                <a className="ag-btn ag-btn-outline" href="#features">
                  了解更多
                </a>
              </div>
            </div>
            <div className="ag-home-hero-code">
              <div className="ag-home-hero-code-glow" aria-hidden="true" />
              <div className="ag-home-code-card">
                <div className="ag-home-code-header" aria-hidden="true">
                  <div className="ag-home-code-dots">
                    <span className="ag-home-code-dot" />
                    <span className="ag-home-code-dot" />
                    <span className="ag-home-code-dot" />
                  </div>
                  <div className="ag-home-code-filename">
                    <span className="material-symbols-outlined">terminal</span>
                    <span>quickstart.py</span>
                  </div>
                </div>
                <pre className="ag-home-code-body"><code>{
`from openai import OpenAI

client = OpenAI(
    base_url="https://your-gateway.com/v1",
    api_key="gw-your-key-here",
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)

print(response.choices[0].message.content)`
                }</code></pre>
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="ag-home-features" id="features" aria-labelledby="features-heading">
          <div className="ag-home-section-inner">
            <div className="ag-home-section-header">
              <h2 id="features-heading" className="ag-home-section-title">
                <span className="ag-home-section-title-accent">为什么选择 Any Gateway？</span>
              </h2>
            </div>
            <p className="ag-home-section-subtitle">
              解决 AI 应用开发中的真实痛点，让你专注业务创新而非基础设施
            </p>
            <div className="ag-home-features-grid">
              {features.map((f) => (
                <div key={f.title} className="ag-home-feature-card">
                  <div className={`ag-home-feature-icon ag-home-feature-icon-${f.color}`} aria-hidden="true">
                    <span className="material-symbols-outlined">{f.icon}</span>
                  </div>
                  <h3 className="ag-home-feature-title">
                    {f.title}
                    <span className="material-symbols-outlined ag-home-feature-arrow" aria-hidden="true">
                      arrow_forward
                    </span>
                  </h3>
                  <p className="ag-home-feature-desc">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Model Logos Strip + Pricing Detail */}
        <section className="ag-home-models-strip" aria-label="已接入模型">
          <div className="ag-home-models-strip-divider" aria-hidden="true" />
          <div className="ag-home-section-inner">
            <h4 className="ag-home-models-strip-label">已接入主流 AI 模型，持续更新中</h4>
            <div className="ag-home-models-strip-logos">
              {sortedVendors.length > 0
                ? sortedVendors.map((name) => (
                    <span
                      key={name}
                      className={`ag-home-model-logo${activeVendor === name ? ' ag-home-model-logo-active' : ''}`}
                      onClick={() => setActiveVendor(name)}
                    >
                      {name}
                    </span>
                  ))
                : modelLogos.map((name) => (
                    <span key={name} className="ag-home-model-logo">{name}</span>
                  ))
              }
            </div>
            {!modelsLoading && activeModels.length > 0 && (
              <>
                <div className="ag-home-model-detail-table-wrap">
                  <table className="ag-home-model-detail-table">
                    <thead>
                      <tr>
                        <th>模型</th>
                        <th>上下文</th>
                        <th>输入价格</th>
                        <th>输出价格</th>
                        <th>缓存输入</th>
                        <th>稳定性</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeModels.map((m) => (
                        <tr key={m.model_name}>
                          <td>
                            <span className="ag-home-model-detail-name">{m.model_name}</span>
                          </td>
                          <td>
                            <span className="ag-home-model-detail-ctx">{formatCtx(m.context_length)}</span>
                          </td>
                          <td>
                            {m.input_token != null ? (
                              <>
                                <span className="ag-home-model-detail-price">{formatPrice(m.input_token)}</span>
                                <span className="ag-home-model-detail-unit">/ 1M</span>
                              </>
                            ) : (
                              <span className="ag-home-model-detail-na">-</span>
                            )}
                          </td>
                          <td>
                            {m.output_token != null ? (
                              <>
                                <span className="ag-home-model-detail-price">{formatPrice(m.output_token)}</span>
                                <span className="ag-home-model-detail-unit">/ 1M</span>
                              </>
                            ) : (
                              <span className="ag-home-model-detail-na">-</span>
                            )}
                          </td>
                          <td>
                            {m.cache_read_token != null ? (
                              <>
                                <span className="ag-home-model-detail-price ag-home-model-detail-price-muted">{formatPrice(m.cache_read_token)}</span>
                                <span className="ag-home-model-detail-unit">/ 1M</span>
                              </>
                            ) : (
                              <span className="ag-home-model-detail-na">-</span>
                            )}
                          </td>
                          <td>
                            {m.stability ? (
                              <span className={`ag-home-model-detail-stability ag-home-model-detail-stability-${m.stability === '稳定' || m.stability?.toLowerCase() === 'stable' ? 'stable' : m.stability?.toLowerCase() === 'beta' || m.stability === '测试' ? 'beta' : 'default'}`}>
                                {m.stability}
                              </span>
                            ) : (
                              <span className="ag-home-model-detail-na">-</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="ag-home-model-detail-footer">
                  <a href="/pricing" className="ag-btn ag-btn-outline">
                    查看完整价格对比
                    <span className="material-symbols-outlined" style={{ fontSize: 16 }} aria-hidden="true">arrow_forward</span>
                  </a>
                </div>
              </>
            )}
          </div>
        </section>

        {/* CTA */}
        <section className="ag-home-cta" id="contact" aria-labelledby="cta-heading">
          <div className="ag-home-section-inner">
            <div className="ag-home-cta-card">
              <div className="ag-home-cta-glow ag-home-cta-glow-1" aria-hidden="true" />
              <div className="ag-home-cta-glow ag-home-cta-glow-2" aria-hidden="true" />
              <h2 id="cta-heading" className="ag-home-cta-title">准备好了吗？</h2>
              <p className="ag-home-cta-subtitle">联系管理员申请账号，立即开始使用。改 2 行代码完成迁移，当天就能看到效果。</p>
              <div className="ag-home-cta-actions">
                <a className="ag-btn ag-btn-primary" href="mailto:admin@example.com">
                  联系管理员
                </a>
                <button className="ag-btn ag-btn-outline" onClick={() => navigate('/login')}>
                  登录控制台
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="ag-home-footer" aria-label="页脚">
        <div className="ag-home-section-inner ag-home-footer-inner">
          <div className="ag-home-footer-brand">
            <div className="ag-home-brand">
              <span
                className="material-symbols-outlined ag-home-brand-icon"
                style={{ fontVariationSettings: "'FILL' 1" }}
                aria-hidden="true"
              >
                hub
              </span>
              <span className="ag-home-brand-title">Any Gateway</span>
            </div>
            <p className="ag-home-footer-tagline">
              企业级 AI 中转网关，聚合主流模型，统一管理用量、成本与权限。
            </p>
          </div>
          <div className="ag-home-footer-col">
            <h4 className="ag-home-footer-col-title">产品与服务</h4>
            <ul className="ag-home-footer-links">
              <li><a href="/docs">开发文档</a></li>
              <li><a href="/login">管理控制台</a></li>
              <li><a href="/pricing">价格对比</a></li>
              <li><a href="#">快速开始</a></li>
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

export default Home
