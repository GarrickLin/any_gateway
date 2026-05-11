import React, { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  Layout as ArcoLayout,
  Menu,
  Button,
  Tooltip,
} from '@arco-design/web-react'
import {
  IconLock,
  IconMessage,
  IconList,
  IconApps,
  IconSettings,
  IconDashboard,
  IconUser,
  IconTag,
  IconStorage,
  IconPoweroff,
} from '@arco-design/web-react/icon'
import { useAuthStore } from '../../store/auth'

const { Sider, Header, Content } = ArcoLayout
const MenuItem = Menu.Item

const pageTitles: Record<string, string> = {
  dashboard: 'Dashboard',
  apikeys: 'API Keys',
  chat: 'Conversations',
  logs: 'Request Logs',
  groups: 'Groups',
  channels: 'Channels',
  prices: 'Pricing',
  vouchers: 'Vouchers',
  users: 'User Management',
}

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
  const currentPageTitle = pageTitles[currentKey] ?? 'Workspace'

  const isAdmin = role === 'admin' || role === 'superadmin'
  const isSuperAdmin = role === 'superadmin'

  return (
    <ArcoLayout className="ag-shell">
      <Sider
        className="ag-sidebar"
        collapsed={collapsed}
        onCollapse={setCollapsed}
        collapsible
        width={200}
        collapsedWidth={64}
      >
        <div className="ag-brand">
          <div className="ag-brand-mark">
            <img src="/icon.png" alt="" />
          </div>
          {!collapsed && (
            <div>
              <div className="ag-brand-title">Gateway</div>
              <div className="ag-brand-subtitle">AI Infrastructure</div>
            </div>
          )}
        </div>
        <Menu
          className="ag-nav"
          selectedKeys={[currentKey]}
          onClickMenuItem={(key) => navigate(`/${key}`)}
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
              <MenuItem key="prices">
                <IconStorage /> 价格管理
              </MenuItem>
              <MenuItem key="vouchers">
                <IconTag /> 消费券
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
        <Header className="ag-topbar">
          <div className="ag-topbar-title">
            <span className="ag-topbar-system">Any Gateway</span>
            <span className="ag-topbar-page">{currentPageTitle}</span>
          </div>
          <div className="ag-topbar-actions">
            <span className="ag-username">{username}</span>
            {role && <span className="ag-role-badge">{role}</span>}
            <Tooltip content="退出登录">
              <Button
                className="ag-icon-button"
                icon={<IconPoweroff />}
                aria-label="退出登录"
                onClick={handleLogout}
              />
            </Tooltip>
          </div>
        </Header>
        <Content className="ag-content">
          <Outlet />
        </Content>
      </ArcoLayout>
    </ArcoLayout>
  )
}

export default Layout
