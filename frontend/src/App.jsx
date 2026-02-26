import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import { Layout, Menu } from 'antd'
import { ApiOutlined, DashboardOutlined, UserOutlined } from '@ant-design/icons'

const { Header, Content, Footer } = Layout

function HomePage() {
  return (
    <div style={{ padding: '50px', textAlign: 'center' }}>
      <h1>LLM Token Manager</h1>
      <p>大模型 Token 管理网关 — 统一管理团队的 LLM API 使用</p>
      <p style={{ color: '#888' }}>前端页面将在 Step 7 实现</p>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Layout style={{ minHeight: '100vh' }}>
        <Header style={{ display: 'flex', alignItems: 'center' }}>
          <div style={{ color: 'white', fontSize: '18px', marginRight: '30px' }}>
            <ApiOutlined /> LLM Token Manager
          </div>
          <Menu
            theme="dark"
            mode="horizontal"
            defaultSelectedKeys={['home']}
            items={[
              { key: 'home', label: <Link to="/">首页</Link>, icon: <DashboardOutlined /> },
              { key: 'login', label: <Link to="/login">登录</Link>, icon: <UserOutlined /> },
            ]}
          />
        </Header>
        <Content style={{ padding: '0 50px' }}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/login" element={<div style={{ padding: '50px' }}>登录页面（Step 2 实现）</div>} />
            <Route path="/register" element={<div style={{ padding: '50px' }}>注册页面（Step 2 实现）</div>} />
          </Routes>
        </Content>
        <Footer style={{ textAlign: 'center' }}>
          LLM Token Manager ©2026
        </Footer>
      </Layout>
    </BrowserRouter>
  )
}

export default App
