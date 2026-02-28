/**
 * Admin 用量分析页面
 * 显示全局用量统计、按模型/按用户分析、导出 CSV
 */
import React, { useState, useEffect } from 'react'
import {
  Card, Row, Col, Statistic, Typography, Spin, Empty, Select,
  Table, Tabs, DatePicker, Button, Tag, Progress, Space
} from 'antd'
import {
  DollarOutlined, ApiOutlined, TeamOutlined, DownloadOutlined,
  BarChartOutlined, UserOutlined, CloudServerOutlined
} from '@ant-design/icons'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip as RechartsTooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as BarTooltip
} from 'recharts'
import { adminUsageApi } from '../api'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

// 图表颜色
const COLORS = ['#1890ff', '#52c41a', '#faad14', '#722ed1', '#eb2f96', '#13c2c2', '#fa541c', '#2f54eb']

export default function AdminUsage() {
  const [loading, setLoading] = useState(true)
  const [period, setPeriod] = useState('month')
  const [activeTab, setActiveTab] = useState('model')
  const [overview, setOverview] = useState(null)
  const [byModel, setByModel] = useState(null)
  const [byUser, setByUser] = useState(null)
  const [exporting, setExporting] = useState(false)

  useEffect(() => {
    loadOverview()
  }, [period])

  useEffect(() => {
    if (activeTab === 'model') {
      loadByModel()
    } else {
      loadByUser()
    }
  }, [activeTab, period])

  const loadOverview = async () => {
    setLoading(true)
    try {
      const response = await adminUsageApi.overview({ period })
      setOverview(response.data)
    } catch (error) {
      console.error('Failed to load overview:', error)
    } finally {
      setLoading(false)
    }
  }

  const loadByModel = async () => {
    try {
      const response = await adminUsageApi.byModel({ period })
      setByModel(response.data)
    } catch (error) {
      console.error('Failed to load by model:', error)
    }
  }

  const loadByUser = async () => {
    try {
      const response = await adminUsageApi.byUser({ period, expand_models: true })
      setByUser(response.data)
    } catch (error) {
      console.error('Failed to load by user:', error)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const groupBy = activeTab === 'model' ? 'model' : 'user'
      const response = await adminUsageApi.export({ format: 'csv', group_by: groupBy, period })

      // 创建下载链接
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `usage_export_${groupBy}_${new Date().toISOString().split('T')[0]}.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
    } catch (error) {
      console.error('Export failed:', error)
    } finally {
      setExporting(false)
    }
  }

  // 模型表格列定义
  const modelColumns = [
    {
      title: '模型',
      dataIndex: 'model_id',
      key: 'model_id',
      render: (text, record) => (
        <span>
          {record.display_name || text}
          {record.display_name && record.display_name !== text && (
            <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>({text})</Text>
          )}
        </span>
      ),
    },
    {
      title: '请求数',
      dataIndex: 'request_count',
      key: 'request_count',
      sorter: (a, b) => a.request_count - b.request_count,
      render: (v) => v?.toLocaleString(),
    },
    {
      title: 'Input Tokens',
      dataIndex: 'input_tokens',
      key: 'input_tokens',
      render: (v) => v?.toLocaleString(),
    },
    {
      title: 'Output Tokens',
      dataIndex: 'output_tokens',
      key: 'output_tokens',
      render: (v) => v?.toLocaleString(),
    },
    {
      title: '费用 (USD)',
      dataIndex: 'cost_usd',
      key: 'cost_usd',
      sorter: (a, b) => (a.cost_usd || 0) - (b.cost_usd || 0),
      render: (v) => `$${parseFloat(v || 0).toFixed(4)}`,
    },
    {
      title: '占比',
      dataIndex: 'percentage',
      key: 'percentage',
      render: (v) => (
        <Progress
          percent={v || 0}
          size="small"
          style={{ width: 80 }}
        />
      ),
    },
  ]

  // 用户表格列定义
  const userColumns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '请求数',
      dataIndex: 'request_count',
      key: 'request_count',
      sorter: (a, b) => a.request_count - b.request_count,
      render: (v) => v?.toLocaleString(),
    },
    {
      title: '费用 (USD)',
      dataIndex: 'cost_usd',
      key: 'cost_usd',
      sorter: (a, b) => (a.cost_usd || 0) - (b.cost_usd || 0),
      render: (v) => `$${parseFloat(v || 0).toFixed(4)}`,
    },
  ]

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  // 准备饼图数据
  const pieData = byModel?.models?.slice(0, 8).map(m => ({
    name: m.display_name || m.model_id,
    value: parseFloat(m.cost_usd || 0),
  })) || []

  return (
    <div style={{ padding: '24px' }}>
      {/* 顶部控制栏 */}
      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>
            <BarChartOutlined /> 用量分析
          </Title>
          <Space>
            <Select
              value={period}
              onChange={setPeriod}
              style={{ width: 120 }}
              options={[
                { label: '今天', value: 'day' },
                { label: '本周', value: 'week' },
                { label: '本月', value: 'month' },
              ]}
            />
            <Button
              icon={<DownloadOutlined />}
              onClick={handleExport}
              loading={exporting}
            >
              导出 CSV
            </Button>
          </Space>
        </div>
      </Card>

      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总费用 (USD)"
              value={overview?.total_cost_usd || 0}
              precision={2}
              prefix={<DollarOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="总请求数"
              value={overview?.total_requests || 0}
              prefix={<ApiOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="活跃用户"
              value={overview?.active_users || 0}
              prefix={<TeamOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card>
            <Statistic
              title="使用模型数"
              value={overview?.top_models?.length || 0}
              prefix={<CloudServerOutlined />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      {/* Tab 切换 */}
      <Card>
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'model',
              label: <span><BarChartOutlined /> 按模型</span>,
              children: (
                <Row gutter={[24, 24]}>
                  <Col xs={24} lg={10}>
                    <div style={{ padding: '16px 0' }}>
                      {pieData.length > 0 ? (
                        <ResponsiveContainer width="100%" height={300}>
                          <PieChart>
                            <Pie
                              data={pieData}
                              cx="50%"
                              cy="50%"
                              labelLine={false}
                              outerRadius={100}
                              fill="#8884d8"
                              dataKey="value"
                              label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                            >
                              {pieData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                              ))}
                            </Pie>
                            <RechartsTooltip
                              formatter={(value) => `$${value.toFixed(4)}`}
                            />
                            <Legend />
                          </PieChart>
                        </ResponsiveContainer>
                      ) : (
                        <Empty description="暂无数据" style={{ padding: '80px 0' }} />
                      )}
                    </div>
                  </Col>
                  <Col xs={24} lg={14}>
                    <Table
                      columns={modelColumns}
                      dataSource={byModel?.models || []}
                      rowKey="model_id"
                      pagination={{ pageSize: 10 }}
                      size="small"
                    />
                  </Col>
                </Row>
              ),
            },
            {
              key: 'user',
              label: <span><UserOutlined /> 按用户</span>,
              children: (
                <Table
                  columns={userColumns}
                  dataSource={byUser?.users || []}
                  rowKey="user_id"
                  pagination={{ pageSize: 10 }}
                  expandable={{
                    expandedRowRender: (record) => (
                      <Table
                        columns={[
                          { title: '模型', dataIndex: 'model_id', key: 'model_id' },
                          { title: '请求数', dataIndex: 'request_count', key: 'request_count' },
                          {
                            title: '费用',
                            dataIndex: 'cost_usd',
                            key: 'cost_usd',
                            render: (v) => `$${parseFloat(v || 0).toFixed(4)}`,
                          },
                        ]}
                        dataSource={record.models || []}
                        rowKey="model_id"
                        pagination={false}
                        size="small"
                      />
                    ),
                    rowExpandable: (record) => record.models && record.models.length > 0,
                  }}
                  size="small"
                />
              ),
            },
          ]}
        />
      </Card>

      {/* Top 模型和用户 */}
      <Row gutter={[16, 16]} style={{ marginTop: 24 }}>
        <Col xs={24} lg={12}>
          <Card title="Top 5 模型" size="small">
            {overview?.top_models?.length > 0 ? (
              <Table
                columns={[
                  { title: '模型', dataIndex: 'model_id', key: 'model_id' },
                  {
                    title: '费用',
                    dataIndex: 'cost_usd',
                    key: 'cost_usd',
                    render: (v) => `$${parseFloat(v || 0).toFixed(4)}`,
                  },
                  { title: '请求数', dataIndex: 'requests', key: 'requests' },
                ]}
                dataSource={overview.top_models}
                rowKey="model_id"
                pagination={false}
                size="small"
              />
            ) : (
              <Empty description="暂无数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Top 5 用户" size="small">
            {overview?.top_users?.length > 0 ? (
              <Table
                columns={[
                  { title: '用户名', dataIndex: 'username', key: 'username' },
                  {
                    title: '费用',
                    dataIndex: 'cost_usd',
                    key: 'cost_usd',
                    render: (v) => `$${parseFloat(v || 0).toFixed(4)}`,
                  },
                ]}
                dataSource={overview.top_users}
                rowKey="user_id"
                pagination={false}
                size="small"
              />
            ) : (
              <Empty description="暂无数据" />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
