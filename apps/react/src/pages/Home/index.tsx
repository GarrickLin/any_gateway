import React from 'react'
import { useNavigate } from 'react-router-dom'
import './index.css'

const models = [
  {
    name: 'GPT-4o',
    type: 'Chat',
    vendor: 'OpenAI',
    context: '128K',
    inputPrice: '18.00',
    outputPrice: '72.00',
    status: 'running',
    p99: '1.8s',
  },
  {
    name: 'Claude Sonnet 3.5',
    type: 'Chat',
    vendor: 'Anthropic',
    context: '200K',
    inputPrice: '21.60',
    outputPrice: '108.00',
    status: 'running',
    p99: '4.2s',
  },
  {
    name: 'DeepSeek V3',
    type: 'Chat',
    vendor: 'DeepSeek',
    context: '128K',
    inputPrice: '2.00',
    outputPrice: '8.00',
    status: 'running',
    p99: '0.9s',
  },
]

const features = [
  {
    icon: 'account_tree',
    title: '模型聚合',
    desc: '一个 API Key 接入 OpenAI、Anthropic、Gemini 等主流模型，兼容 OpenAI 接口格式，零改造迁移',
  },
  {
    icon: 'payments',
    title: '成本控制',
    desc: '分组限流、消费券、余额管理，精细化控制每个用户和团队的 AI 支出',
  },
  {
    icon: 'shield',
    title: '企业管理',
    desc: '用户分组、权限分层、完整请求日志与用量审计，满足企业合规需求',
  },
]

const audiences = [
  {
    role: '研发团队',
    desc: '统一 API 入口，不再为每个模型维护单独的 key 和 SDK',
  },
  {
    role: 'AI 平台团队',
    desc: '多渠道负载均衡、模型别名映射、流式响应透传',
  },
  {
    role: '企业管理员',
    desc: '用量审计、成本分摊、权限分组，满足合规要求',
  },
]

const Home: React.FC = () => {
  const navigate = useNavigate()

  return (
    <div className="ag-home">
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
          <button
            className="ag-btn ag-btn-outline"
            onClick={() => navigate('/login')}
          >
            登录
          </button>
        </div>
      </nav>

      <main>
        {/* Hero */}
        <section className="ag-home-hero" aria-labelledby="hero-heading">
          <div className="ag-home-section-inner ag-home-hero-inner">
            <div className="ag-home-hero-text">
              <h1 id="hero-heading" className="ag-home-hero-title">
                一个 API，连接所有 AI
              </h1>
              <p className="ag-home-hero-subtitle">
                企业级 AI 中转网关，聚合 OpenAI、Anthropic、Gemini 等主流模型，统一管理用量、成本与权限
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
                  联系管理员
                </a>
                <button
                  className="ag-btn ag-btn-outline"
                  onClick={() => navigate('/login')}
                >
                  登录
                </button>
              </div>
            </div>
            <div className="ag-home-hero-code">
              <div className="ag-home-code-card">
                <div className="ag-home-code-header" aria-hidden="true">
                  <span className="ag-home-code-dot" />
                  <span className="ag-home-code-dot" />
                  <span className="ag-home-code-dot" />
                </div>
                <pre className="ag-home-code-body">
                  <code>{`curl https://your-gateway.com/v1/chat/completions \\
  -H "Authorization: Bearer sk-xxx" \\
  -d '{"model": "gpt-5.5", "messages": [{"role":"user", "content":"Hello"}]}'`}</code>
                </pre>
              </div>
              <div className="ag-home-badges" aria-label="核心功能">
                {['分组限流', '用量审计', '多渠道路由', '消费券'].map((badge) => (
                  <span key={badge} className="ag-home-badge">{badge}</span>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="ag-home-features" id="features" aria-labelledby="features-heading">
          <div className="ag-home-section-inner">
            <div className="ag-home-section-header">
              <h2 id="features-heading" className="ag-home-section-title">核心能力</h2>
            </div>
            <div className="ag-home-features-grid">
              {features.map((f) => (
                <div key={f.title} className="ag-home-feature-card">
                  <div className="ag-home-feature-icon" aria-hidden="true">
                    <span className="material-symbols-outlined">{f.icon}</span>
                  </div>
                  <h3 className="ag-home-feature-title">{f.title}</h3>
                  <p className="ag-home-feature-desc">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Audience */}
        <section className="ag-home-audience" id="audience" aria-labelledby="audience-heading">
          <div className="ag-home-section-inner">
            <div className="ag-home-section-header">
              <h2 id="audience-heading" className="ag-home-section-title">适用对象</h2>
            </div>
            <div className="ag-home-audience-grid">
              {audiences.map((a) => (
                <div key={a.role} className="ag-home-audience-card">
                  <h4 className="ag-home-audience-role">{a.role}</h4>
                  <p className="ag-home-audience-desc">{a.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Model Matrix */}
        <section className="ag-home-models" id="models" aria-labelledby="models-heading">
          <div className="ag-home-section-inner">
            <div className="ag-home-models-header">
              <h2 id="models-heading" className="ag-home-section-title ag-home-section-title-left">
                模型矩阵 · 实时价格 + 状态
              </h2>
              <a className="ag-home-models-link" href="#">
                查看全部
                <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
              </a>
            </div>
            <div className="ag-home-models-table-wrap">
              <table className="ag-home-models-table" aria-label="模型价格与状态">
                <thead>
                  <tr>
                    <th scope="col">模型</th>
                    <th scope="col">厂商</th>
                    <th scope="col">上下文</th>
                    <th scope="col">输入价 (¥/M tok)</th>
                    <th scope="col">输出价 (¥/M tok)</th>
                    <th scope="col">状态</th>
                    <th scope="col">p99</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <tr key={m.name}>
                      <td>
                        <span className="ag-model-name">{m.name}</span>
                        <span className="ag-model-type">{m.type}</span>
                      </td>
                      <td>{m.vendor}</td>
                      <td>{m.context}</td>
                      <td>{m.inputPrice}</td>
                      <td>{m.outputPrice}</td>
                      <td>
                        <div className="ag-model-status">
                          <span className="ag-model-status-dot" aria-hidden="true" />
                          运行中
                        </div>
                      </td>
                      <td>{m.p99}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="ag-home-cta" id="contact" aria-labelledby="cta-heading">
          <div className="ag-home-section-inner ag-home-cta-inner">
            <h2 id="cta-heading" className="ag-home-cta-title">准备好了吗？</h2>
            <p className="ag-home-cta-subtitle">联系管理员申请账号，立即开始使用</p>
            <div className="ag-home-cta-actions">
              <a className="ag-btn ag-btn-primary" href="mailto:admin@example.com">
                联系管理员
              </a>
              <button className="ag-btn ag-btn-outline" onClick={() => navigate('/login')}>
                登录
              </button>
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
            <p className="ag-home-footer-tagline">企业级 AI 中转网关，聚合主流模型，统一管理用量、成本与权限。</p>
            <p className="ag-home-footer-copy">© {new Date().getFullYear()} Any Gateway AI Infrastructure. All rights reserved.</p>
          </div>
          <div className="ag-home-footer-col">
            <h4 className="ag-home-footer-col-title">产品</h4>
            <ul className="ag-home-footer-links">
              <li><a href="#">API Documentation</a></li>
              <li><a href="/login">登录控制台</a></li>
            </ul>
          </div>
          <div className="ag-home-footer-col">
            <h4 className="ag-home-footer-col-title">法律与支持</h4>
            <ul className="ag-home-footer-links">
              <li><a href="#">Privacy Policy</a></li>
              <li><a href="#">Terms of Service</a></li>
              <li><a href="mailto:admin@example.com">Contact Us</a></li>
              <li><a href="#">Support</a></li>
            </ul>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default Home
