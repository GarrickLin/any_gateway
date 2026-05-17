import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import '../Home/index.css'
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
  cache_write_token?: number
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
    else if (row.unit === 'cache_write_token') entry.cache_write_token = row.price_per_unit
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

const PublicPricing: React.FC = () => {
  const navigate = useNavigate()
  const [groups, setGroups] = useState<GroupedModels>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    axios
      .get('/public/model-prices')
      .then((res) => {
        const rows: PriceRow[] = res.data?.data ?? res.data ?? []
        setGroups(buildModels(rows))
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [])

  const sortedVendors = vendorOrder.filter((v) => groups[v]?.length)

  return (
    <div className="ag-home">
      {/* Ambient glow orbs */}
      <div className="ag-home-glow ag-home-glow-1" />
      <div className="ag-home-glow ag-home-glow-2" />

      {/* Nav */}
      <nav className="ag-home-nav" aria-label="主导航">
        <div className="ag-home-nav-inner">
          <a href="/home" className="ag-home-brand" style={{ textDecoration: 'none' }}>
            <span
              className="material-symbols-outlined ag-home-brand-icon"
              style={{ fontVariationSettings: "'FILL' 1" }}
              aria-hidden="true"
            >
              hub
            </span>
            <span className="ag-home-brand-title">Any Gateway</span>
          </a>
          <div className="ag-home-nav-links">
            <a className="ag-home-nav-link" href="/docs">开发文档</a>
            <a className="ag-home-nav-link" href="/home#features">核心能力</a>
            <a className="ag-home-nav-link ag-home-nav-link-active" href="/pricing">价格对比</a>
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
        <section className="ag-pricing-hero" aria-labelledby="pricing-heading">
          <div className="ag-home-section-inner ag-pricing-hero-inner">
            <div className="ag-home-status-badge">
              <span className="material-symbols-outlined" style={{ fontSize: 14 }} aria-hidden="true">
                payments
              </span>
              透明定价
            </div>
            <h1 id="pricing-heading" className="ag-home-hero-title" style={{ textAlign: 'center' }}>
              同样的模型<br />
              <span className="ag-home-gradient-text">更低的价格</span>
            </h1>
            <p className="ag-pricing-hero-subtitle">
              批量采购优势直接让利给开发者。<strong>相同质量，平均便宜 20-40%。</strong>
              <br />按实际用量计费，无最低消费，无隐藏费用。
            </p>
          </div>
        </section>

        {/* Pricing Tables */}
        <section className="ag-pricing-tables" aria-label="模型定价">
          <div className="ag-home-section-inner">
            {loading && (
              <div className="ag-pricing-loading">
                <div className="ag-pricing-spinner" />
              </div>
            )}
            {error && (
              <div className="ag-pricing-error">
                <p>加载价格数据失败</p>
                <button className="ag-btn ag-btn-primary" onClick={() => location.reload()}>
                  重试
                </button>
              </div>
            )}
            {!loading && !error && sortedVendors.length === 0 && (
              <p className="ag-pricing-empty">暂无价格数据</p>
            )}
            {sortedVendors.map((vendor) => (
              <div key={vendor} className="ag-pricing-group">
                <div className="ag-pricing-group-header">
                  <h3 className="ag-pricing-group-title">{vendor}</h3>
                </div>
                <div className="ag-pricing-table-wrap">
                  <table className="ag-pricing-table">
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
                      {groups[vendor].map((m) => (
                        <tr key={m.model_name}>
                          <td>
                            <span className="ag-pricing-model-name">{m.model_name}</span>
                          </td>
                          <td>
                            <span className="ag-pricing-ctx">{formatCtx(m.context_length)}</span>
                          </td>
                          <td>
                            {m.input_token != null ? (
                              <>
                                <span className="ag-pricing-price">{formatPrice(m.input_token)}</span>
                                <span className="ag-pricing-price-unit">/ 1M</span>
                              </>
                            ) : (
                              <span className="ag-pricing-na">-</span>
                            )}
                          </td>
                          <td>
                            {m.output_token != null ? (
                              <>
                                <span className="ag-pricing-price">{formatPrice(m.output_token)}</span>
                                <span className="ag-pricing-price-unit">/ 1M</span>
                              </>
                            ) : (
                              <span className="ag-pricing-na">-</span>
                            )}
                          </td>
                          <td>
                            {m.cache_read_token != null ? (
                              <>
                                <span className="ag-pricing-price ag-pricing-price-muted">{formatPrice(m.cache_read_token)}</span>
                                <span className="ag-pricing-price-unit">/ 1M</span>
                              </>
                            ) : (
                              <span className="ag-pricing-na">-</span>
                            )}
                          </td>
                          <td>
                            {m.stability ? (
                              <span className={`ag-pricing-stability ag-pricing-stability-${m.stability === '稳定' || m.stability?.toLowerCase() === 'stable' ? 'stable' : m.stability?.toLowerCase() === 'beta' || m.stability === '测试' ? 'beta' : 'default'}`}>
                                {m.stability}
                              </span>
                            ) : (
                              <span className="ag-pricing-na">-</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Features */}
        <section className="ag-pricing-features" aria-label="定价优势">
          <div className="ag-home-section-inner">
            <div className="ag-pricing-features-card">
              <h2 className="ag-pricing-features-title">价格更低，服务更好</h2>
              <div className="ag-pricing-features-grid">
                <div className="ag-pricing-feature-item">
                  <div className="ag-pricing-feature-icon ag-pricing-feature-icon-amber" aria-hidden="true">
                    <span className="material-symbols-outlined">payments</span>
                  </div>
                  <h3 className="ag-pricing-feature-name">批量采购优势</h3>
                  <p className="ag-pricing-feature-desc">
                    直接对接上游，规模化采购降低成本，让利给每一位用户
                  </p>
                </div>
                <div className="ag-pricing-feature-item">
                  <div className="ag-pricing-feature-icon ag-pricing-feature-icon-blue" aria-hidden="true">
                    <span className="material-symbols-outlined">bolt</span>
                  </div>
                  <h3 className="ag-pricing-feature-name">缓存也享优惠</h3>
                  <p className="ag-pricing-feature-desc">
                    Prompt Cache 命中时同样按优惠价计费，不会像其他网关按全价收费
                  </p>
                </div>
                <div className="ag-pricing-feature-item">
                  <div className="ag-pricing-feature-icon ag-pricing-feature-icon-emerald" aria-hidden="true">
                    <span className="material-symbols-outlined">verified</span>
                  </div>
                  <h3 className="ag-pricing-feature-name">透明计费</h3>
                  <p className="ag-pricing-feature-desc">
                    每次调用精确到分，实时查看消费明细，月底对账清清楚楚
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="ag-home-cta" id="contact" aria-labelledby="pricing-cta-heading">
          <div className="ag-home-section-inner">
            <div className="ag-home-cta-card">
              <div className="ag-home-cta-glow ag-home-cta-glow-1" aria-hidden="true" />
              <div className="ag-home-cta-glow ag-home-cta-glow-2" aria-hidden="true" />
              <h2 id="pricing-cta-heading" className="ag-home-cta-title">免费试用，随时开始</h2>
              <p className="ag-home-cta-subtitle">
                联系管理员申请账号即可体验，按量付费，用多少付多少。
              </p>
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

export default PublicPricing
