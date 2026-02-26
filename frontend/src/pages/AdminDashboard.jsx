/**
 * 管理员仪表盘页面
 */
import React, { useState, useEffect } from 'react'
import {
  Card, Row, Col, Statistic, Typography, Spin, Table, Tag
} from 'antd'
import {
  UserOutlined, ApiOutlined, DollarOutlined,
  TeamOutlined, CloudServerOutlined
} from '@ant-design/icons'
import { adminUserApi, adminProviderApi } from '../api'

const { Title } = Typography

export default function AdminDashboard() {
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({
    totalUsers: 0,
    totalProviders: 0,
    recentUsers: [],
    providers: [],
  })

  useEffect(() => {
    loadDashboard()
  }, [])

  const loadDashboard = async () => {
    setLoading(true)
    try {
      const [usersRes, providersRes] = await Promise.all([
        adminUserApi.list({ limit: 5 }),
        adminProviderApi.list(),
      ])

      setStats({
        totalUsers: usersRes.data.total || usersRes.data.length || 0,
        totalProviders: providersRes.data.length || 0,
        recentUsers: usersRes.data.items || usersRes.data || [],
        providers: providersRes.data || [],
      })
    } catch (error) {
      console.error('Failed to load dashboard:', error)
    } finally {
      setLoading(false)
    }
  }

  const userColumns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: '角色',
      dataIndex: 'role',
      key: 'role',
      render: (role) => (
        <Tag color={role === 'admin' ? 'red' : 'blue'}>
          {role === 'admin' ? '管理员' : '普通用户'}
        </Tag>
      ),
    },
    {
      title: '月度额度',
      dataIndex: 'monthly_quota_usd',
      key: 'monthly_quota_usd',
      render: (quota) => `$${parseFloat(quota || 0).toFixed(2)}`,
    },
  ]

  const providerColumns = [
    {
      title: '供应商',
      dataIndex: 'name',
      key: 'name',
      render: (name) => name.toUpperCase(),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      render: (enabled) => (
        <Tag color={enabled ? 'success' : 'default'}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: 'API 地址',
      dataIndex: 'base_url',
      key: 'base_url',
      ellipsis: true,
    },
  ]

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ padding: '24px' }}>
      <Title level={4} style={{ marginBottom: 24 }}>
        管理员仪表盘
      </Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="用户总数"
              value={stats.totalUsers}
              prefix={<TeamOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="供应商数量"
              value={stats.totalProviders}
              prefix={<CloudServerOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="本月活跃用户"
              value={stats.recentUsers.length}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="系统状态"
              value="正常"
              prefix={<ApiOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="最近用户">
            <Table
              columns={userColumns}
              dataSource={stats.recentUsers}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="供应商列表">
            <Table
              columns={providerColumns}
              dataSource={stats.providers}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
