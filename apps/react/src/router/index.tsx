import { createBrowserRouter, Navigate } from 'react-router-dom'
import Layout from '../components/Layout'
import AuthGuard from '../components/AuthGuard'
import Login from '../pages/Login'
import ApiKeys from '../pages/ApiKeys'
import Channels from '../pages/Channels'
import Chat from '../pages/Chat'
import Dashboard from '../pages/Dashboard'
import Groups from '../pages/Groups'
import Home from '../pages/Home'
import Docs from '../pages/Docs'
import PublicPricing from '../pages/Pricing/public'
import Logs from '../pages/Logs'
import Prices from '../pages/Prices'
import Users from '../pages/Users'
import Vouchers from '../pages/Vouchers'

const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  // 公开页面：营销主页，无需认证，由 Caddy 路由控制
  {
    path: '/home',
    element: <Home />,
  },
  {
    path: '/pricing',
    element: <PublicPricing />,
  },
  {
    path: '/docs',
    element: <Docs />,
  },
  {
    path: '/',
    element: (
      <AuthGuard>
        <Layout />
      </AuthGuard>
    ),
    children: [
      { index: true, element: <Navigate to="/apikeys" replace /> },
      { path: 'apikeys', element: <ApiKeys /> },
      { path: 'chat', element: <Chat /> },
      { path: 'logs', element: <Logs /> },
      {
        path: 'groups',
        element: (
          <AuthGuard roles={['admin', 'superadmin']}>
            <Groups />
          </AuthGuard>
        ),
      },
      {
        path: 'channels',
        element: (
          <AuthGuard roles={['admin', 'superadmin']}>
            <Channels />
          </AuthGuard>
        ),
      },
      {
        path: 'prices',
        element: (
          <AuthGuard roles={['admin', 'superadmin']}>
            <Prices />
          </AuthGuard>
        ),
      },
      {
        path: 'vouchers',
        element: (
          <AuthGuard roles={['admin', 'superadmin']}>
            <Vouchers />
          </AuthGuard>
        ),
      },
      { path: 'dashboard', element: <Dashboard /> },
      {
        path: 'users',
        element: (
          <AuthGuard roles={['superadmin']}>
            <Users />
          </AuthGuard>
        ),
      },
    ],
  },
])

export default router
