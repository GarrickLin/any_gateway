import React from 'react'
import { Navigate } from 'react-router-dom'
import { Result } from '@arco-design/web-react'
import { useAuthStore } from '../../store/auth'

interface AuthGuardProps {
  children: React.ReactNode
  roles?: string[]
}

const AuthGuard: React.FC<AuthGuardProps> = ({ children, roles }) => {
  const { token, role } = useAuthStore()

  if (!token) {
    return <Navigate to="/login" replace />
  }

  if (roles && role && !roles.includes(role)) {
    return (
      <Result
        status="403"
        title="无访问权限"
        subTitle="你没有权限访问此页面"
      />
    )
  }

  return <>{children}</>
}

export default AuthGuard
