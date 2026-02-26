/**
 * 受保护路由组件
 * 用于需要登录才能访问的页面
 */
import React from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { Spin } from 'antd'
import { useAuth } from './AuthContext'

export function ProtectedRoute({ children, adminOnly = false }) {
  const { user, loading, isAdmin } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!user) {
    // 未登录，重定向到登录页
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (adminOnly && !isAdmin()) {
    // 非管理员访问管理员页面，重定向到首页
    return <Navigate to="/" replace />
  }

  return children
}
