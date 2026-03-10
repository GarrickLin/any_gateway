import React, { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  Layout as ArcoLayout,
  Menu,
  Button,
  Typography,
  Space,
} from '@arco-design/web-react'
import {
  IconLock,
  IconMessage,
  IconList,
  IconApps,
  IconSettings,
  IconDashboard,
  IconUser,
} from '@arco-design/web-react/icon'
import { useAuthStore } from '../../store/auth'

const { Sider, Header, Content } = ArcoLayout
const MenuItem = Menu.Item

const Layout: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const { username, role, logout } = useAuthStore()
  const [collapsed, setCollapsed] = useState(false)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const currentKey = location.pathname.slice(1) || 'apikeys'

  const isAdmin = role === 'admin' || role === 'superadmin'
  const isSuperAdmin = role === 'superadmin'

  return (
    <ArcoLayout style={{ height: '100vh' }}>
      <Sider
        collapsed={collapsed}
        onCollapse={setCollapsed}
        collapsible
        width={200}
        style={{ background: '#fff', borderRight: '1px solid #e5e6eb' }}
      >
        <div style={{ padding: '16px', textAlign: 'center', fontWeight: 600, fontSize: 16 }}>
          {collapsed ? 'AG' : 'Any Gateway'}
        </div>
        <Menu
          selectedKeys={[currentKey]}
          onClickMenuItem={(key) => navigate(`/${key}`)}
          style={{ border: 'none' }}
        >
          <MenuItem key="dashboard">
            <IconDashboard /> 仪表板
          </MenuItem>
          <MenuItem key="apikeys">
            <IconLock /> API 密钥
          </MenuItem>
          <MenuItem key="chat">
            <IconMessage /> 对话
          </MenuItem>
          <MenuItem key="logs">
            <IconList /> 日志
          </MenuItem>
          {isAdmin && (
            <>
              <MenuItem key="groups">
                <IconApps /> 分组
              </MenuItem>
              <MenuItem key="channels">
                <IconSettings /> 渠道
              </MenuItem>
            </>
          )}
          {isSuperAdmin && (
            <MenuItem key="users">
              <IconUser /> 用户管理
            </MenuItem>
          )}
        </Menu>
      </Sider>
      <ArcoLayout>
        <Header
          style={{
            background: '#fff',
            borderBottom: '1px solid #e5e6eb',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            padding: '0 16px',
          }}
        >
          <Space>
            <Typography.Text>
              {username}
              {role && (
                <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                  [{role}]
                </Typography.Text>
              )}
            </Typography.Text>
            <Button size="small" onClick={handleLogout}>
              退出登录
            </Button>
          </Space>
        </Header>
        <Content style={{ padding: 24, overflow: 'auto' }}>
          <Outlet />
        </Content>
      </ArcoLayout>
    </ArcoLayout>
  )
}

export default Layout
