/**
 * 主应用组件
 * 路由配置和全局布局
 */
import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link, useLocation } from 'react-router-dom'
import { Layout, Menu, Dropdown, Avatar, Typography, message, Tabs, Steps, Alert, Tooltip } from 'antd'
import {
  ApiOutlined, UserOutlined, KeyOutlined, BarChartOutlined,
  DashboardOutlined, TeamOutlined, CloudServerOutlined,
  LogoutOutlined, LoginOutlined, CodeOutlined, CopyOutlined, CheckOutlined,
  SettingOutlined
} from '@ant-design/icons'

import { AuthProvider, useAuth } from './components/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import Login from './pages/Login'
import Register from './pages/Register'
import MyKeys from './pages/MyKeys'
import MyUsage from './pages/MyUsage'
import Profile from './pages/Profile'
import AdminDashboard from './pages/AdminDashboard'
import AdminUsers from './pages/AdminUsers'
import AdminProviders from './pages/AdminProviders'
import AdminUsage from './pages/AdminUsage'

const { Header, Content, Footer, Sider } = Layout
const { Text, Paragraph } = Typography

/**
 * 可复制代码块组件
 */
function CopyableCode({ code, language = 'bash' }) {
  const [copied, setCopied] = React.useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    message.success('已复制到剪贴板')
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div style={{ position: 'relative' }}>
      <pre style={{
        background: '#1e1e1e',
        color: '#d4d4d4',
        padding: 16,
        borderRadius: 4,
        overflow: 'auto',
        fontSize: 13,
        margin: 0,
      }}>
        <code>{code}</code>
      </pre>
      <Tooltip title={copied ? '已复制' : '复制'}>
        <div
          onClick={handleCopy}
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            cursor: 'pointer',
            padding: 4,
            borderRadius: 4,
            background: copied ? '#52c41a' : '#333',
            transition: 'background 0.2s',
          }}
        >
          {copied ? (
            <CheckOutlined style={{ color: '#fff', fontSize: 14 }} />
          ) : (
            <CopyOutlined style={{ color: '#fff', fontSize: 14 }} />
          )}
        </div>
      </Tooltip>
    </div>
  )
}

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
        key: 'settings',
        icon: <SettingOutlined />,
        label: <Link to="/profile">个人设置</Link>,
      },
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
    if (path === '/profile') return 'profile'
    if (path === '/admin') return 'admin'
    if (path === '/admin/users') return 'admin-users'
    if (path === '/admin/providers') return 'admin-providers'
    if (path === '/admin/usage') return 'admin-usage'
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
            key: 'admin-usage',
            icon: <BarChartOutlined />,
            label: <Link to="/admin/usage">用量分析</Link>,
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
            LLM Token Manager ©2026
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
        <Paragraph>
          <Text code>ltm-sk-xxxx</Text> 是您的平台 Key，以下是常用工具的配置方法：
        </Paragraph>

        <Tabs
          defaultActiveKey="opencode"
          items={[
            {
              key: 'opencode',
              label: (
                <span>
                  <CodeOutlined style={{ marginRight: 4 }} />
                  OpenCode
                </span>
              ),
              children: (
                <div>
                  <Alert
                    message="OpenCode 配置指南"
                    description="将平台 Key 配置到 OpenCode 中，即可使用网关提供的所有模型。推荐使用 OpenCode 客户端。"
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                  />
                  <Steps
                    direction="vertical"
                    current={-1}
                    items={[
                      {
                        title: '打开配置文件',
                        description: (
                          <div>
                            <Paragraph>OpenCode 配置文件位于：</Paragraph>
                            <CopyableCode code="~/.config/opencode/opencode.json" />
                          </div>
                        ),
                      },
                      {
                        title: '添加 Provider 配置',
                        description: (
                          <div>
                            <Paragraph>在 <Text code>provider</Text> 字段中添加 <Text code>ltm-anthropic</Text> 配置：</Paragraph>
                            <CopyableCode
                              code={`{
  "provider": {
    "ltm-anthropic": {
      "name": "LTM Anthropic",
      "npm": "@ai-sdk/anthropic",
      "options": {
        "baseURL": "https://your-gateway.com/v1",
        "apiKey": "ltm-sk-your-key-here"
      },
      "models": {
        "MiniMax-M2.5": {
          "name": "MiniMax M2.5",
          "reasoning": true,
          "limit": {
            "context": 204800,
            "output": 131072
          }
        }
      }
    }
  }
}`}
                            />
                            <Alert
                              message="请将 baseURL 和 apiKey 替换为实际值"
                              type="warning"
                              showIcon
                              style={{ marginTop: 12 }}
                            />
                          </div>
                        ),
                      },
                      {
                        title: '重启 OpenCode',
                        description: (
                          <div>
                            <Paragraph>保存配置文件后，重新启动 OpenCode，使用以下命令切换模型：</Paragraph>
                            <CopyableCode code="/model ltm-anthropic/MiniMax-M2.5" />
                          </div>
                        ),
                      },
                    ]}
                  />
                </div>
              ),
            },
            {
              key: 'python',
              label: 'Python SDK',
              children: (
                <div>
                  <Paragraph>使用 OpenAI Python SDK 调用：</Paragraph>
                  <CopyableCode
                    code={`from openai import OpenAI

client = OpenAI(
    base_url="https://your-gateway.com/v1",
    api_key="ltm-sk-your-key-here"
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}]
)`}
                  />
                </div>
              ),
            },
            {
              key: 'curl',
              label: 'cURL',
              children: (
                <div>
                  <Paragraph>使用 cURL 直接调用 API：</Paragraph>
                  <CopyableCode
                    code={`curl https://your-gateway.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer ltm-sk-your-key-here" \\
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'`}
                  />
                </div>
              ),
            },
          ]}
        />
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
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <MainLayout>
              <Profile />
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
        path="/admin/usage"
        element={
          <ProtectedRoute adminOnly>
            <MainLayout>
              <AdminUsage />
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

// 获取基础路径（去除尾部斜杠，用于 React Router basename）
const getBasename = () => {
  const base = import.meta.env.BASE_URL || '/'
  return base.endsWith('/') && base.length > 1 ? base.slice(0, -1) : base
}

/**
 * 根组件
 */
function App() {
  return (
    <BrowserRouter basename={getBasename()}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
