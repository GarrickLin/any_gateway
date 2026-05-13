import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Grid, Typography } from '@arco-design/web-react'
import './index.css'

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { Row, Col } = Grid
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const { Title, Paragraph, Text } = Typography

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
        <div className="ag-home-section-inner">
          <p>Hero 区占位</p>
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
