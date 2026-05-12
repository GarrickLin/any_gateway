import React, { useState } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  Layout as ArcoLayout,
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
  const initials = username
    ? username
      .split(/[._@\s-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('')
    : 'U'
  const navItems: Array<{ key: string; label: string; icon: React.ReactNode; visible?: boolean }> = [
    { key: 'dashboard', label: '仪表板', icon: <IconDashboard /> },
    { key: 'apikeys', label: 'API 密钥', icon: <IconLock /> },
    { key: 'chat', label: '对话', icon: <IconMessage /> },
    { key: 'logs', label: '日志', icon: <IconList /> },
    { key: 'groups', label: '分组', icon: <IconApps />, visible: isAdmin },
    { key: 'channels', label: '渠道', icon: <IconSettings />, visible: isAdmin },
    { key: 'prices', label: '价格管理', icon: <IconStorage />, visible: isAdmin },
    { key: 'vouchers', label: '消费券', icon: <IconTag />, visible: isAdmin },
    { key: 'users', label: '用户管理', icon: <IconUser />, visible: isSuperAdmin },
  ]

  return (
    <ArcoLayout className="ag-shell">
      <Sider
        className="ag-sidebar"
        collapsed={collapsed}
        onCollapse={setCollapsed}
        collapsible
        width={256}
        collapsedWidth={64}
      >
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
          {!collapsed && (
            <div>
              <div className="ag-brand-title">Gateway</div>
              <div className="ag-brand-subtitle">AI Infrastructure</div>
            </div>
          )}
        </div>
        <nav className="ag-sidebar-nav">
          {navItems
            .filter((item) => item.visible !== false)
            .map((item) => {
              const selected = item.key === currentKey
              const button = (
                <button
                  key={item.key}
                  type="button"
                  className={selected ? 'ag-sidebar-nav-item ag-sidebar-nav-item-active' : 'ag-sidebar-nav-item'}
                  aria-current={selected ? 'page' : undefined}
                  onClick={() => navigate(`/${item.key}`)}
                >
                  {item.icon}
                  {!collapsed && <span>{item.label}</span>}
                </button>
              )

              return collapsed ? (
                <Tooltip key={item.key} content={item.label} position="right">
                  {button}
                </Tooltip>
              ) : button
            })}
        </nav>
        {!collapsed && (
          <div className="ag-sidebar-user">
            <div className="ag-sidebar-avatar">{initials}</div>
            <div className="ag-sidebar-user-meta">
              <div className="ag-sidebar-username">{username || 'User'}</div>
              <div className="ag-sidebar-role">{role || 'Authenticated'}</div>
            </div>
          </div>
        )}
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
