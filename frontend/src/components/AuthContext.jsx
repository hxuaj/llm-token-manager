/**
 * 认证上下文
 * 管理全局认证状态
 */
import React, { createContext, useContext, useState, useEffect } from 'react'
import { authApi } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // 初始化时检查本地存储的登录状态
  useEffect(() => {
    const initAuth = async () => {
      const token = localStorage.getItem('token')
      const savedUser = localStorage.getItem('user')

      if (token && savedUser) {
        try {
          setUser(JSON.parse(savedUser))
          // 可选：验证 token 是否有效
          // const response = await authApi.me()
          // setUser(response.data)
        } catch (error) {
          console.error('Failed to verify token:', error)
          localStorage.removeItem('token')
          localStorage.removeItem('user')
        }
      }
      setLoading(false)
    }

    initAuth()
  }, [])

  // 登录
  const login = async (username, password) => {
    // 先获取 token
    const loginResponse = await authApi.login({ username, password })
    const { access_token } = loginResponse.data

    // 保存 token
    localStorage.setItem('token', access_token)

    // 然后获取用户信息
    const meResponse = await authApi.me()
    const userData = meResponse.data

    localStorage.setItem('user', JSON.stringify(userData))
    setUser(userData)

    return userData
  }

  // 注册
  const register = async (username, email, password) => {
    // 先注册
    await authApi.register({ username, email, password })

    // 然后自动登录
    return await login(username, password)
  }

  // 登出
  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('user')
    setUser(null)
  }

  // 检查是否是管理员
  const isAdmin = () => {
    return user?.role === 'admin'
  }

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    isAdmin,
    isAuthenticated: !!user,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
