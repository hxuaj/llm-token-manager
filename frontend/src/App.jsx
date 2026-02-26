/**
 * 主应用组件
 * 路由配置和全局布局
 */
import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { Layout, Menu, Dropdown, Avatar, Typography, message } from 'antd'
import {
  ApiOutlined, UserOutlined, KeyOutlined, BarChartOutlined,
  DashboardOutlined, TeamOutlined, CloudServerOutlined,
  LogoutOutlined, LoginOutlined
} from '@ant-design/icons'

import { AuthProvider, useAuth } from './components/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import MyKeys from './pages/MyKeys'
import MyUsage from './pages/MyUsage'
import AdminDashboard from './pages/AdminDashboard'
import AdminUsers from './pages/AdminUsers'
import AdminProviders from './pages/AdminProviders'

const { Header, Content, Footer, Sider } = Layout
const { Text } = Typography

/**
 * 主布局组件
 */
function MainLayout({ children }) {
  const { user, logout, isAdmin } = useAuth()
  const location = useLocation()

  const handleLogout = () => {
    logout()
    message.success('已退出登录')
  }

  // 用户下拉菜单
  const userMenu = {
    items: [
      {
        key: 'profile',
        icon: <UserOutlined />,
        label: user?.username,
        disabled: true,
      },
      { type: 'divider' },
      {
        key: 'logout',
        icon: <LogoutOutlined />,
        label: '退出登录',
        onClick: handleLogout,
      },
    ],
  }

  // 获取当前选中的菜单项
  const getSelectedKey = () => {
    const path = location.pathname
    if (path === '/keys') return 'keys'
    if (path === '/usage') return 'usage'
    if (path === '/admin') return 'admin'
    if (path === '/admin/users') return 'admin-users'
    if (path === '/admin/providers') return 'admin-providers'
    return 'home'
  }

  // 侧边栏菜单项
  const menuItems = [
    {
      key: 'home',
      icon: <DashboardOutlined />,
      label: <Link to="/">首页</Link>,
    },
    {
      key: 'keys',
      icon: <KeyOutlined />,
      label: <Link to="/keys">我的 Key</Link>,
    },
    {
      key: 'usage',
      icon: <BarChartOutlined />,
      label: <Link to="/usage">用量统计</Link>,
    },
  ]

  // 管理员菜单
  if (isAdmin()) {
    menuItems.push(
      { type: 'divider' },
      {
        key: 'admin',
        icon: <TeamOutlined />,
        label: '管理员',
        children: [
          {
            key: 'admin-dashboard',
            icon: <DashboardOutlined />,
            label: <Link to="/admin">仪表盘</Link>,
          },
          {
            key: 'admin-users',
            icon: <TeamOutlined />,
            label: <Link to="/admin/users">用户管理</Link>,
          },
          {
            key: 'admin-providers',
            icon: <CloudServerOutlined />,
            label: <Link to="/admin/providers">供应商管理</Link>,
          },
        ],
      }
    )
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={220}
        style={{
          background: '#fff',
          borderRight: '1px solid #f0f0f0',
        }}
      >
        <div style={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderBottom: '1px solid #f0f0f0',
        }}>
          <ApiOutlined style={{ fontSize: 24, color: '#1890ff', marginRight: 8 }} />
          <Text strong style={{ fontSize: 16 }}>LLM Gateway</Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[getSelectedKey()]}
          defaultOpenKeys={['admin']}
          items={menuItems}
          style={{ borderRight: 0 }}
        />
      </Sider>
      <Layout>
        <Header style={{
          padding: '0 24px',
          background: '#fff',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderBottom: '1px solid #f0f0f0',
        }}>
          <Text type="secondary">
            大模型 Token 管理网关
          </Text>
          <Dropdown menu={userMenu} placement="bottomRight">
            <div style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} style={{ marginRight: 8 }} />
              <Text>{user?.username}</Text>
            </div>
          </Dropdown>
        </Header>
        <Content style={{
          margin: 0,
          background: '#f5f5f5',
          minHeight: 'calc(100vh - 64px - 70px)',
        }}>
          {children}
        </Content>
        <Footer style={{
          padding: '16px 24px',
          background: '#fff',
          borderTop: '1px solid #f0f0f0',
          textAlign: 'center',
        }}>
          <Text type="secondary">
            LLM Token Manager ©2026 - 统一管理团队的 LLM API 使用
          </Text>
        </Footer>
      </Layout>
    </Layout>
  )
}

/**
 * 首页组件
 */
function HomePage() {
  const { user, isAdmin } = useAuth()

  return (
    <div style={{ padding: '24px' }}>
      <div style={{
        background: '#fff',
        padding: '32px',
        borderRadius: 8,
        marginBottom: 24,
      }}>
        <Typography.Title level={3} style={{ marginTop: 0 }}>
          欢迎，{user?.username}！
        </Typography.Title>
        <Typography.Text type="secondary">
          这是 LLM Token Manager 管理后台，您可以在这里管理您的 API Key、查看用量统计。
        </Typography.Text>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
        gap: 16,
      }}>
        <Link to="/keys" style={{ textDecoration: 'none' }}>
          <div style={{
            background: '#fff',
            padding: '24px',
            borderRadius: 8,
            cursor: 'pointer',
            transition: 'box-shadow 0.3s',
          }}
          onMouseEnter={(e) => e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'}
          onMouseLeave={(e) => e.currentTarget.style.boxShadow = 'none'}
          >
            <KeyOutlined style={{ fontSize: 32, color: '#1890ff', marginBottom: 16 }} />
            <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 8 }}>
              我的 Key
            </Typography.Title>
            <Typography.Text type="secondary">
              创建和管理您的 API Key
            </Typography.Text>
          </div>
        </Link>

        <Link to="/usage" style={{ textDecoration: 'none' }}>
          <div style={{
            background: '#fff',
            padding: '24px',
            borderRadius: 8,
            cursor: 'pointer',
            transition: 'box-shadow 0.3s',
          }}
          onMouseEnter={(e) => e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'}
          onMouseLeave={(e) => e.currentTarget.style.boxShadow = 'none'}
          >
            <BarChartOutlined style={{ fontSize: 32, color: '#52c41a', marginBottom: 16 }} />
            <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 8 }}>
              用量统计
            </Typography.Title>
            <Typography.Text type="secondary">
              查看您的使用情况和费用
            </Typography.Text>
          </div>
        </Link>

        {isAdmin() && (
          <Link to="/admin" style={{ textDecoration: 'none' }}>
            <div style={{
              background: '#fff',
              padding: '24px',
              borderRadius: 8,
              cursor: 'pointer',
              transition: 'box-shadow 0.3s',
            }}
            onMouseEnter={(e) => e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'}
            onMouseLeave={(e) => e.currentTarget.style.boxShadow = 'none'}
            >
              <TeamOutlined style={{ fontSize: 32, color: '#722ed1', marginBottom: 16 }} />
              <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 8 }}>
                管理员
              </Typography.Title>
              <Typography.Text type="secondary">
                管理用户和供应商
              </Typography.Text>
            </div>
          </Link>
        )}
      </div>

      <div style={{
        background: '#fff',
        padding: '24px',
        borderRadius: 8,
        marginTop: 24,
      }}>
        <Typography.Title level={5} style={{ marginTop: 0 }}>
          快速开始
        </Typography.Title>
        <Typography.Paragraph>
          <Typography.Text code>ltm-sk-xxxx</Typography.Text> 是您的平台 Key，使用方法：
        </Typography.Paragraph>
        <pre style={{
          background: '#f5f5f5',
          padding: 16,
          borderRadius: 4,
          overflow: 'auto',
        }}>
{`from openai import OpenAI

client = OpenAI(
    base_url="https://your-gateway.com/v1",
    api_key="ltm-sk-your-key-here"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)`}
        </pre>
      </div>
    </div>
  )
}

/**
 * 路由配置
 */
function AppRoutes() {
  return (
    <Routes>
      {/* 公开路由 */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />

      {/* 受保护路由 */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MainLayout>
              <HomePage />
            </MainLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/keys"
        element={
          <ProtectedRoute>
            <MainLayout>
              <MyKeys />
            </MainLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/usage"
        element={
          <ProtectedRoute>
            <MainLayout>
              <MyUsage />
            </MainLayout>
          </ProtectedRoute>
        }
      />

      {/* 管理员路由 */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute adminOnly>
            <MainLayout>
              <AdminDashboard />
            </MainLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/users"
        element={
          <ProtectedRoute adminOnly>
            <MainLayout>
              <AdminUsers />
            </MainLayout>
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/providers"
        element={
          <ProtectedRoute adminOnly>
            <MainLayout>
              <AdminProviders />
            </MainLayout>
          </ProtectedRoute>
        }
      />

      {/* 默认重定向 */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

/**
 * 根组件
 */
function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
