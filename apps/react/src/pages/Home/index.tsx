import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Grid, Typography } from '@arco-design/web-react'
import { IconBranch, IconSafe } from '@arco-design/web-react/icon'
import './index.css'

const { Row, Col } = Grid
const { Title, Paragraph, Text } = Typography

const Home: React.FC = () => {
  const navigate = useNavigate()

  const features = [
    {
      icon: <IconBranch />,
      title: '模型聚合',
      desc: '一个 API Key 接入 OpenAI、Anthropic、Gemini 等主流模型，兼容 OpenAI 接口格式，零改造迁移。',
    },
    {
      icon: (
        <span
          className="material-symbols-outlined"
          style={{ fontVariationSettings: "'FILL' 1", fontSize: '24px' }}
          aria-hidden="true"
        >
          payments
        </span>
      ),
      title: '成本控制',
      desc: '分组限流、消费券、余额管理，精细化控制每个用户和团队的 AI 支出。',
      highlights: ['滑动窗口限流，按请求/Token/费用三维度', '消费券与余额独立管理'],
    },
    {
      icon: <IconSafe />,
      title: '企业管理',
      desc: '用户分组、权限分层、完整请求日志与用量审计，满足企业合规需求。',
      highlights: ['完整请求日志，支持按用户/模型筛选', '权限分层：user / admin / superadmin'],
    },
  ]

  const audiences = [
    {
      role: '研发团队',
      desc: '统一 API 入口，不再为每个模型维护单独的 key 和 SDK，一行代码切换模型。',
    },
    {
      role: 'AI 平台团队',
      desc: '多渠道负载均衡、模型别名映射、流式响应透传，灵活编排上游资源。',
    },
    {
      role: '企业管理员',
      desc: '用量审计、成本分摊、权限分组，满足企业合规与预算管控要求。',
    },
  ]

  return (
    <div className="ag-home">
      {/* Navbar */}
      <nav className="ag-home-nav">
        <div className="ag-home-nav-inner">
          <div className="ag-brand">
            <div className="ag-brand-mark">
              <span
                className="material-symbols-outlined"
                style={{ fontVariationSettings: "'FILL' 1" }}
                aria-hidden="true"
              >
                hub
              </span>
            </div>
            <div>
              <div className="ag-brand-title">Gateway</div>
              <div className="ag-brand-subtitle">AI Infrastructure</div>
            </div>
          </div>
          <Button onClick={() => navigate('/login')}>登录</Button>
        </div>
      </nav>

      {/* Hero */}
      <section className="ag-home-hero" id="hero">
        <div className="ag-home-section-inner ag-home-hero-inner">
          <div className="ag-home-hero-text">
            <Title className="ag-home-hero-title">一个 API，连接所有 AI</Title>
            <Paragraph className="ag-home-hero-subtitle">
              企业级 AI 中转网关，聚合 OpenAI、Anthropic、Gemini 等主流模型，
              统一管理用量、成本与权限
            </Paragraph>
            <div className="ag-home-hero-actions">
              <Button
                type="primary"
                size="large"
                onClick={() => document.getElementById('contact')?.scrollIntoView({ behavior: 'smooth' })}
              >
                联系管理员
              </Button>
              <Button size="large" onClick={() => navigate('/login')}>
                登录
              </Button>
            </div>
          </div>
          <div className="ag-home-hero-code">
            <div className="ag-home-code-card">
              <div className="ag-home-code-header">
                <span className="ag-home-code-dot" />
                <span className="ag-home-code-dot" />
                <span className="ag-home-code-dot" />
                <span className="ag-home-code-label">POST /v1/chat/completions</span>
              </div>
              <pre
                className="ag-home-code-body"
                // eslint-disable-next-line react/no-danger
                dangerouslySetInnerHTML={{
                  __html: [
                    '<span class="ag-code-comment"># 请求：切换模型只需改一个字段</span>',
                    '<span class="ag-code-keyword">curl</span> https://gateway.example.com/v1/chat/completions \\',
                    '  -H <span class="ag-code-string">"Authorization: Bearer sk-xxx"</span> \\',
                    '  -d <span class="ag-code-string">\'{"model": "<span class="ag-code-highlight">claude-opus-4-5</span>",</span>',
                    '      <span class="ag-code-string">"messages": [{"role": "user", "content": "Hello"}]}\'</span>',
                    '',
                    '<span class="ag-code-comment"># 响应</span>',
                    '<span class="ag-code-punctuation">{</span>',
                    '  <span class="ag-code-key">"model"</span>: <span class="ag-code-string">"claude-opus-4-5"</span>,',
                    '  <span class="ag-code-key">"usage"</span>: { <span class="ag-code-key">"total_tokens"</span>: <span class="ag-code-number">42</span> },',
                    '  <span class="ag-code-key">"choices"</span>: [{"message": {"content": <span class="ag-code-string">"Hi!"</span>}}]',
                    '<span class="ag-code-punctuation">}</span>',
                  ].join('\n'),
                }}
              />
            </div>
            <div className="ag-home-badges">
              {['分组限流', '用量审计', '多渠道路由', '消费券'].map((badge) => (
                <span key={badge} className="ag-home-badge">{badge}</span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="ag-home-features" id="features">
        <div className="ag-home-section-inner">
          <div className="ag-home-features-header">
            <Title heading={2} className="ag-home-section-title">核心能力</Title>
            <p className="ag-home-features-sub">一套 API，统一管理所有 AI 资源</p>
          </div>
          <div className="ag-home-features-grid">
            {/* 主卡片：模型聚合 */}
            <Card className="ag-home-feature-card ag-home-feature-card-primary" bordered={false}>
              <div className="ag-home-feature-icon">{features[0].icon}</div>
              <Title heading={3} className="ag-home-feature-title">{features[0].title}</Title>
              <Paragraph className="ag-home-feature-desc">{features[0].desc}</Paragraph>
              <ul className="ag-home-feature-highlights">
                <li>兼容 OpenAI 接口格式，零改造迁移</li>
                <li>模型别名映射，一行代码切换上游</li>
                <li>多渠道加权负载均衡，自动故障转移</li>
              </ul>
              <div className="ag-home-feature-models">
                {['OpenAI', 'Anthropic', 'Gemini', 'DeepSeek'].map((m) => (
                  <span key={m} className="ag-home-feature-model-tag">{m}</span>
                ))}
              </div>
            </Card>
            {/* 次要卡片列 */}
            <div className="ag-home-features-secondary">
              {features.slice(1).map((f) => (
                <Card key={f.title} className="ag-home-feature-card" bordered={false}>
                  <div className="ag-home-feature-icon">{f.icon}</div>
                  <Title heading={5} className="ag-home-feature-title">{f.title}</Title>
                  <Paragraph className="ag-home-feature-desc">{f.desc}</Paragraph>
                  {f.highlights && (
                    <ul className="ag-home-feature-highlights ag-home-feature-highlights-sm">
                      {f.highlights.map((h) => <li key={h}>{h}</li>)}
                    </ul>
                  )}
                </Card>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Audience */}
      <section className="ag-home-audience" id="audience">
        <div className="ag-home-section-inner">
          <Title heading={2} className="ag-home-section-title">适用对象</Title>
          <div className="ag-home-audience-list">
            {audiences.map((a, i) => (
              <div key={a.role} className="ag-home-audience-item">
                <span className="ag-home-audience-index">0{i + 1}</span>
                <div className="ag-home-audience-content">
                  <Text className="ag-home-audience-role">{a.role}</Text>
                  <Paragraph className="ag-home-audience-desc">{a.desc}</Paragraph>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="ag-home-cta" id="contact">
        <div className="ag-home-section-inner ag-home-cta-inner">
          <Title heading={2} className="ag-home-cta-title">准备好了吗？</Title>
          <Paragraph className="ag-home-cta-subtitle">
            联系管理员申请账号，立即开始使用
          </Paragraph>
          <div className="ag-home-cta-actions">
            <Button
              type="primary"
              size="large"
              href="mailto:admin@example.com"
              onClick={() => window.location.href = 'mailto:admin@example.com'}
            >
              联系管理员
            </Button>
            <Button size="large" onClick={() => navigate('/login')}>
              登录
            </Button>
          </div>
        </div>
      </section>

      <footer className="ag-home-footer" id="footer">
        <div className="ag-home-section-inner ag-home-footer-inner">
          <div className="ag-brand">
            <div className="ag-brand-mark ag-brand-mark-sm">
              <span
                className="material-symbols-outlined"
                style={{ fontVariationSettings: "'FILL' 1" }}
                aria-hidden="true"
              >
                hub
              </span>
            </div>
            <span className="ag-home-footer-name">Any Gateway</span>
          </div>
          <Text className="ag-home-footer-copy">
            © {new Date().getFullYear()} Any Gateway. All rights reserved.
          </Text>
        </div>
      </footer>
    </div>
  )
}

export default Home
