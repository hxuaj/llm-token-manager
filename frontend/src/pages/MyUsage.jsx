/**
 * 我的用量页面
 */
import React, { useState, useEffect } from 'react'
import {
  Card, Row, Col, Statistic, Progress, Typography, Spin, Empty, Descriptions
} from 'antd'
import {
  DollarOutlined, ApiOutlined, ThunderboltOutlined,
  CalendarOutlined
} from '@ant-design/icons'
import { userKeyApi } from '../api'

const { Title, Text } = Typography

export default function MyUsage() {
  const [loading, setLoading] = useState(true)
  const [usage, setUsage] = useState(null)

  useEffect(() => {
    loadUsage()
  }, [])

  const loadUsage = async () => {
    setLoading(true)
    try {
      const response = await userKeyApi.usage()
      setUsage(response.data)
    } catch (error) {
      console.error('Failed to load usage:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!usage) {
    return (
      <div style={{ padding: '24px' }}>
        <Card>
          <Empty description="暂无用量数据" />
        </Card>
      </div>
    )
  }

  // 计算额度使用百分比
  const quotaPercent = usage.quota_limit > 0
    ? Math.min(100, (usage.quota_used / usage.quota_limit) * 100)
    : 0

  // 根据使用量确定进度条颜色
  const getProgressColor = (percent) => {
    if (percent >= 90) return '#ff4d4f'
    if (percent >= 70) return '#faad14'
    return '#1890ff'
  }

  return (
    <div style={{ padding: '24px' }}>
      <Card style={{ marginBottom: 24 }}>
        <Title level={4} style={{ marginTop: 0, marginBottom: 24 }}>
          <CalendarOutlined /> 本月用量统计 ({usage.year_month || '-'})
        </Title>

        <Row gutter={[24, 24]}>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="总请求数"
                value={usage.total_requests || 0}
                prefix={<ApiOutlined />}
                valueStyle={{ color: '#1890ff' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="总 Token 数"
                value={usage.total_tokens || 0}
                prefix={<ThunderboltOutlined />}
                valueStyle={{ color: '#722ed1' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="已用额度 (USD)"
                value={usage.quota_used || 0}
                precision={4}
                prefix={<DollarOutlined />}
                valueStyle={{ color: '#52c41a' }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card>
              <Statistic
                title="额度上限 (USD)"
                value={usage.quota_limit || 0}
                precision={2}
                prefix={<DollarOutlined />}
              />
            </Card>
          </Col>
        </Row>
      </Card>

      <Card>
        <Title level={5} style={{ marginTop: 0, marginBottom: 24 }}>
          额度使用情况
        </Title>

        <div style={{ marginBottom: 16 }}>
          <Progress
            percent={quotaPercent}
            strokeColor={getProgressColor(quotaPercent)}
            format={(percent) => `${percent.toFixed(1)}%`}
          />
        </div>

        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="本月已用">
            ${typeof usage.quota_used === 'number' ? usage.quota_used.toFixed(4) : '0.0000'}
          </Descriptions.Item>
          <Descriptions.Item label="月度额度">
            ${typeof usage.quota_limit === 'number' ? usage.quota_limit.toFixed(2) : '0.00'}
          </Descriptions.Item>
          <Descriptions.Item label="剩余额度">
            ${typeof usage.quota_limit === 'number' && typeof usage.quota_used === 'number'
              ? Math.max(0, usage.quota_limit - usage.quota_used).toFixed(4)
              : '0.0000'}
          </Descriptions.Item>
          <Descriptions.Item label="RPM 限制">
            {usage.rpm_limit || 0} 次/分钟
          </Descriptions.Item>
        </Descriptions>

        {quotaPercent >= 80 && (
          <div style={{ marginTop: 16, padding: 12, background: '#fff7e6', borderRadius: 4 }}>
            <Text type="warning">
              {quotaPercent >= 100
                ? '您的额度已用完，请联系管理员增加额度'
                : '您的额度使用已超过 80%，请注意控制用量'}
            </Text>
          </div>
        )}
      </Card>
    </div>
  )
}
