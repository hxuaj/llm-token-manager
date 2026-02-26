/**
 * 我的 Key 管理页面
 */
import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, message, Tag, Space,
  Typography, Popconfirm, Card, Descriptions, Statistic, Row, Col
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, KeyOutlined,
  CopyOutlined, CheckCircleOutlined, CloseCircleOutlined
} from '@ant-design/icons'
import { userKeyApi } from '../api'

const { Title, Text, Paragraph } = Typography

export default function MyKeys() {
  const [keys, setKeys] = useState([])
  const [loading, setLoading] = useState(true)
  const [createModalVisible, setCreateModalVisible] = useState(false)
  const [statsModalVisible, setStatsModalVisible] = useState(false)
  const [selectedKey, setSelectedKey] = useState(null)
  const [keyStats, setKeyStats] = useState(null)
  const [newKey, setNewKey] = useState(null)
  const [createForm] = Form.useForm()

  // 加载 Key 列表
  const loadKeys = async () => {
    setLoading(true)
    try {
      const response = await userKeyApi.list()
      setKeys(response.data)
    } catch (error) {
      message.error('加载 Key 列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadKeys()
  }, [])

  // 创建 Key
  const handleCreate = async (values) => {
    try {
      const response = await userKeyApi.create(values.name)
      setNewKey(response.data.key)
      message.success('Key 创建成功')
      createForm.resetFields()
      setCreateModalVisible(false)
      loadKeys()
    } catch (error) {
      const detail = error.response?.data?.detail
      message.error(typeof detail === 'string' ? detail : '创建 Key 失败')
    }
  }

  // 吊销 Key
  const handleRevoke = async (id) => {
    try {
      await userKeyApi.revoke(id)
      message.success('Key 已吊销')
      loadKeys()
    } catch (error) {
      message.error('吊销 Key 失败')
    }
  }

  // 查看统计
  const handleViewStats = async (record) => {
    setSelectedKey(record)
    try {
      const response = await userKeyApi.stats(record.id)
      setKeyStats(response.data)
      setStatsModalVisible(true)
    } catch (error) {
      message.error('加载统计信息失败')
    }
  }

  // 复制 Key
  const copyKey = (key) => {
    navigator.clipboard.writeText(key)
    message.success('已复制到剪贴板')
  }

  // 表格列定义
  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Key',
      key: 'key',
      render: (_, record) => (
        <Text code>{record.key_prefix}...{record.key_suffix}</Text>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'active' ? 'success' : 'error'}>
          {status === 'active' ? '正常' : '已吊销'}
        </Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '最后使用',
      dataIndex: 'last_used_at',
      key: 'last_used_at',
      render: (time) => time ? new Date(time).toLocaleString() : '从未使用',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space>
          <Button type="link" onClick={() => handleViewStats(record)}>
            统计
          </Button>
          {record.status === 'active' && (
            <Popconfirm
              title="确定要吊销这个 Key 吗？"
              description="吊销后 Key 将立即失效，无法恢复"
              onConfirm={() => handleRevoke(record.id)}
              okText="确定"
              cancelText="取消"
            >
              <Button type="link" danger>
                吊销
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>
            <KeyOutlined /> 我的 API Key
          </Title>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalVisible(true)}
          >
            创建 Key
          </Button>
        </div>

        <Table
          columns={columns}
          dataSource={keys}
          rowKey="id"
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 创建 Key 弹窗 */}
      <Modal
        title="创建新 Key"
        open={createModalVisible}
        onCancel={() => {
          setCreateModalVisible(false)
          createForm.resetFields()
        }}
        footer={null}
      >
        <Form form={createForm} onFinish={handleCreate} layout="vertical">
          <Form.Item
            name="name"
            label="Key 名称"
            rules={[{ required: true, message: '请输入 Key 名称' }]}
          >
            <Input placeholder="例如：项目A-后端、本地调试" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              创建
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 显示新 Key 弹窗 */}
      <Modal
        title="Key 创建成功"
        open={!!newKey}
        onCancel={() => setNewKey(null)}
        footer={[
          <Button key="close" onClick={() => setNewKey(null)}>
            关闭
          </Button>,
        ]}
      >
        <div style={{ marginBottom: 16 }}>
          <Text type="danger">
            请立即复制并妥善保管此 Key，关闭后将无法再次查看完整内容。
          </Text>
        </div>
        <Input.Group compact>
          <Input
            style={{ width: 'calc(100% - 50px)' }}
            value={newKey}
            readOnly
          />
          <Button icon={<CopyOutlined />} onClick={() => copyKey(newKey)}>
            复制
          </Button>
        </Input.Group>
      </Modal>

      {/* 统计弹窗 */}
      <Modal
        title="Key 统计"
        open={statsModalVisible}
        onCancel={() => {
          setStatsModalVisible(false)
          setKeyStats(null)
        }}
        footer={[
          <Button key="close" onClick={() => setStatsModalVisible(false)}>
            关闭
          </Button>,
        ]}
      >
        {keyStats && (
          <Row gutter={16}>
            <Col span={12}>
              <Statistic
                title="总请求数"
                value={keyStats.total_requests || 0}
              />
            </Col>
            <Col span={12}>
              <Statistic
                title="总 Token 数"
                value={keyStats.total_tokens || 0}
              />
            </Col>
            <Col span={12}>
              <Statistic
                title="总费用 (USD)"
                value={keyStats.total_cost_usd || 0}
                precision={4}
              />
            </Col>
            <Col span={12}>
              <Statistic
                title="Key ID"
                value={keyStats.key_id?.slice(0, 8) + '...'}
              />
            </Col>
          </Row>
        )}
      </Modal>
    </div>
  )
}
