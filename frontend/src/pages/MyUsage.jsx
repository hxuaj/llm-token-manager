/**
 * 我的用量页面
 * 显示用户按模型、按 Key 的用量统计和时间线趋势
 */
import React, { useState, useEffect } from 'react'
import {
  Card, Row, Col, Statistic, Progress, Typography, Spin, Empty,
  Select, Table, Tabs, DatePicker, Tooltip
} from 'antd'
import {
  DollarOutlined, ApiOutlined, ThunderboltOutlined,
  CalendarOutlined, ClockCircleOutlined, KeyOutlined
} from '@ant-design/icons'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip as RechartsTooltip,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as LineTooltip
} from 'recharts'
import dayjs from 'dayjs'
import { userKeyApi, userUsageApi } from '../api'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

// 图表颜色
const COLORS = ['#1890ff', '#52c41a', '#faad14', '#722ed1', '#eb2f96', '#13c2c2', '#fa541c', '#2f54eb']

export default function MyUsage() {
  const [loading, setLoading] = useState(true)
  const [period, setPeriod] = useState('month')
  const [usageByModel, setUsageByModel] = useState(null)
  const [usageByKey, setUsageByKey] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [basicUsage, setBasicUsage] = useState(null)

  useEffect(() => {
    loadAllData()
  }, [period])

  const loadAllData = async () => {
    setLoading(true)
    try {
      const params = { period }

      // 并行加载所有数据
      const [basicRes, modelRes, keyRes, timelineRes] = await Promise.all([
        userKeyApi.usage().catch(() => ({ data: null })),
        userUsageApi.byModel(params).catch(() => ({ data: null })),
        userUsageApi.byKey(params).catch(() => ({ data: null })),
        userUsageApi.timeline({ ...params, granularity: 'day' }).catch(() => ({ data: null })),
      ])

      setBasicUsage(basicRes.data)
      setUsageByModel(modelRes.data)
      setUsageByKey(keyRes.data)
      setTimeline(timelineRes.data)
    } catch (error) {
      console.error('Failed to load usage data:', error)
    } finally {
      setLoading(false)
    }
  }

  // 计算额度使用百分比
  const quotaPercent = basicUsage?.quota_limit > 0
    ? Math.min(100, (basicUsage.quota_used / basicUsage.quota_limit) * 100)
    : 0

  // 根据使用量确定进度条颜色
  const getProgressColor = (percent) => {
    if (percent >= 90) return '#ff4d4f'
    if (percent >= 70) return '#faad14'
    return '#1890ff'
  }

  // 模型表格列定义
  const modelColumns = [
    {
      title: '模型',
      dataIndex: 'model_id',
      key: 'model_id',
      render: (text, record) => record.display_name || text,
    },
    {
      title: '请求数',
      dataIndex: 'request_count',
      key: 'request_count',
      sorter: (a, b) => a.request_count - b.request_count,
    },
    {
      title: '输入 Tokens',
      dataIndex: 'input_tokens',
      key: 'input_tokens',
      render: (v) => v?.toLocaleString(),
    },
    {
      title: '输出 Tokens',
      dataIndex: 'output_tokens',
      key: 'output_tokens',
      render: (v) => v?.toLocaleString(),
    },
    {
      title: '费用 (USD)',
      dataIndex: 'cost_usd',
      key: 'cost_usd',
      render: (v) => `$${parseFloat(v || 0).toFixed(4)}`,
      sorter: (a, b) => (a.cost_usd || 0) - (b.cost_usd || 0),
    },
    {
      title: '占比',
      dataIndex: 'percentage',
      key: 'percentage',
      render: (v) => (
        <Progress
          percent={v || 0}
          size="small"
          showInfo={false}
          strokeColor="#1890ff"
        />
      ),
    },
  ]

  // Key 表格列定义
  const keyColumns = [
    {
      title: 'Key',
      dataIndex: 'key_suffix',
      key: 'key_suffix',
      render: (suffix) => <Text code>...{suffix}</Text>,
    },
    {
      title: '名称',
      dataIndex: 'key_name',
      key: 'key_name',
    },
    {
      title: '总费用 (USD)',
      dataIndex: 'total_cost_usd',
      key: 'total_cost_usd',
      render: (v) => `$${parseFloat(v || 0).toFixed(4)}`,
    },
    {
      title: '使用模型',
      dataIndex: 'models',
      key: 'models',
      render: (models) => (
        <span>
          {models?.map((m, i) => (
            <Text key={i} style={{ marginRight: 8 }}>
              {m.display_name || m.model_id} ({m.request_count})
            </Text>
          ))}
        </span>
      ),
    },
  ]

  // 饼图数据
  const pieData = usageByModel?.models?.map((m) => ({
    name: m.display_name || m.model_id,
    value: parseFloat(m.cost_usd || 0),
  }))?.filter(d => d.value > 0) || []

  // 时间线数据
  const timelineData = timeline?.data?.map((d) => ({
    date: d.date,
    cost: parseFloat(d.cost_usd || 0),
    requests: d.requests,
  })) || []

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  return (
    <div style={{ padding: '24px' }}>
      {/* 顶部统计卡片 */}
      <Card style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
          <Title level={4} style={{ margin: 0 }}>
            <CalendarOutlined /> 我的用量统计
          </Title>
          <Select
            value={period}
            onChange={setPeriod}
            style={{ width: 120 }}
            options={[
              { value: 'day', label: '今天' },
              { value: 'week', label: '最近 7 天' },
              { value: 'month', label: '本月' },
            ]}
          />
        </div>

        <Row gutter={[24, 24]}>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="总请求数"
                value={usageByModel?.total_requests || 0}
                prefix={<ApiOutlined />}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="总费用 (USD)"
                value={usageByModel?.total_cost_usd || 0}
                precision={4}
                prefix={<DollarOutlined />}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="已用额度"
                value={basicUsage?.quota_used || 0}
                precision={4}
                prefix={<DollarOutlined />}
                suffix={`/ $${basicUsage?.quota_limit?.toFixed(2) || '0.00'}`}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="模型数量"
                value={usageByModel?.models?.length || 0}
                prefix={<ThunderboltOutlined />}
                valueStyle={{ color: '#722ed1' }}
              />
            </Card>
          </Col>
        </Row>

        {/* 额度使用进度条 */}
        {basicUsage?.quota_limit > 0 && (
          <div style={{ marginTop: 24 }}>
            <Text type="secondary">额度使用情况</Text>
            <Progress
              percent={quotaPercent}
              strokeColor={getProgressColor(quotaPercent)}
              format={(percent) => `${percent.toFixed(1)}%`}
              style={{ marginTop: 8 }}
            />
            {quotaPercent >= 80 && (
              <div style={{ marginTop: 8, padding: 12, background: '#fff7e6', borderRadius: 4 }}>
                <Text type="warning">
                  {quotaPercent >= 100
                    ? '您的额度已用完，请联系管理员增加额度'
                    : '您的额度使用已超过 80%，请注意控制用量'}
                </Text>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* 图表区域 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        {/* 饼图 - 按模型费用分布 */}
        <Col xs={24} lg={12}>
          <Card title="费用分布（按模型）" style={{ height: '100%' }}>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(1)}%`}
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
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
              <Empty description="暂无数据" style={{ padding: '60px 0' }} />
            )}
          </Card>
        </Col>

        {/* 折线图 - 费用趋势 */}
        <Col xs={24} lg={12}>
          <Card title="费用趋势" style={{ height: '100%' }}>
            {timelineData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={timelineData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 12 }} />
                  <LineTooltip
                    formatter={(value, name) => [
                      name === 'cost' ? `$${value.toFixed(4)}` : value,
                      name === 'cost' ? '费用' : '请求数'
                    ]}
                  />
                  <Line
                    type="monotone"
                    dataKey="cost"
                    stroke="#1890ff"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    name="cost"
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Empty description="暂无数据" style={{ padding: '60px 0' }} />
            )}
          </Card>
        </Col>
      </Row>

      {/* Tab 切换详细数据 */}
      <Card>
        <Tabs
          defaultActiveKey="model"
          items={[
            {
              key: 'model',
              label: <span><ThunderboltOutlined /> 按模型</span>,
              children: (
                <Table
                  columns={modelColumns}
                  dataSource={usageByModel?.models || []}
                  rowKey="model_id"
                  pagination={{ pageSize: 10 }}
                  size="small"
                />
              ),
            },
            {
              key: 'key',
              label: <span><KeyOutlined /> 按 Key</span>,
              children: (
                <Table
                  columns={keyColumns}
                  dataSource={usageByKey?.keys || []}
                  rowKey="key_suffix"
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
                  }}
                  size="small"
                />
              ),
            },
          ]}
        />
      </Card>
    </div>
  )
}
