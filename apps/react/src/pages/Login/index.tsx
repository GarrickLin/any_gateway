import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Form, Input, Button, Card, Message } from '@arco-design/web-react'
import { login } from '../../api/auth'
import { useAuthStore } from '../../store/auth'

const Login: React.FC = () => {
  const navigate = useNavigate()
  const { token, setAuth } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()

  // 已登录用户直接跳转首页
  useEffect(() => {
    if (token) {
      navigate('/', { replace: true })
    }
  }, [token, navigate])

  const handleSubmit = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const res = await login(values.username, values.password)
      setAuth(res.data.access_token, values.username, res.data.role)
      navigate('/')
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      Message.error(detail || '用户名或密码错误')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        height: '100vh',
        backgroundImage: 'url(/background.png)',
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >
      <Card style={{ width: 360, backdropFilter: 'blur(4px)', background: 'rgba(255,255,255,0.88)' }} title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <img src="/icon.png" alt="logo" style={{ width: 24, height: 24, borderRadius: 4 }} />
          <span>Any Gateway 登录</span>
        </div>
      }>
        <Form form={form} onSubmit={handleSubmit} layout="vertical">
          <Form.Item
            field="username"
            label="AD 用户名"
            rules={[{ required: true, message: '请输入域账号' }]}
          >
            <Input placeholder="请输入域账号" autoComplete="username" />
          </Form.Item>
          <Form.Item
            field="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password placeholder="请输入密码" autoComplete="current-password" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} long>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}

export default Login
