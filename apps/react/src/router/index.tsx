import { createBrowserRouter, Navigate } from 'react-router-dom'
import Layout from '../components/Layout'
import AuthGuard from '../components/AuthGuard'
import Login from '../pages/Login'
import Home from '../pages/Home'
import Dashboard from '../pages/Dashboard'
import Groups from '../pages/Groups'
import Channels from '../pages/Channels'
import ApiKeys from '../pages/ApiKeys'
import Users from '../pages/Users'
import Logs from '../pages/Logs'
import Chat from '../pages/Chat'
import Prices from '../pages/Prices'
import Vouchers from '../pages/Vouchers'

const router = createBrowserRouter([
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/home',
    element: <Home />,
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
