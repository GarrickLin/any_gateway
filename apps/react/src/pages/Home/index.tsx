import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Grid, Typography } from '@arco-design/web-react'
import './index.css'

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { Row, Col } = Grid
const { Title, Paragraph } = Typography

const Home: React.FC = () => {
  const navigate = useNavigate()

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
              </div>
              <pre className="ag-home-code-body">{`curl https://your-gateway.com/v1/chat/completions \\
  -H "Authorization: Bearer sk-xxx" \\
  -d '{
    "model": "gpt-5.5",
    "messages": [{"role": "user", "content": "Hello"}]
  }'`}</pre>
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
          <p>卖点卡片占位</p>
        </div>
      </section>

      {/* Audience */}
      <section className="ag-home-audience" id="audience">
        <div className="ag-home-section-inner">
          <p>适用对象占位</p>
        </div>
      </section>

      {/* CTA + Footer */}
      <section className="ag-home-cta" id="contact">
        <div className="ag-home-section-inner">
          <p>底部 CTA 占位</p>
        </div>
      </section>

      <footer className="ag-home-footer">
        <div className="ag-home-section-inner">
          <p>Footer 占位</p>
        </div>
      </footer>
    </div>
  )
}

export default Home
