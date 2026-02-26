/**
 * 管理员 - 供应商管理页面
 */
import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Switch, Select,
  message, Tag, Space, Card, Typography, Popconfirm, Tabs, Divider
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, KeyOutlined,
  CloudServerOutlined, DollarOutlined
} from '@ant-design/icons'
import { adminProviderApi } from '../api'

const { Title, Text } = Typography
const { TabPane } = Tabs
const { TextArea } = Input

export default function AdminProviders() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [providerModalVisible, setProviderModalVisible] = useState(false)
  const [keyModalVisible, setKeyModalVisible] = useState(false)
  const [pricingModalVisible, setPricingModalVisible] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState(null)
  const [providerKeys, setProviderKeys] = useState([])
  const [modelPricing, setModelPricing] = useState([])
  const [providerForm] = Form.useForm()
  const [keyForm] = Form.useForm()
  const [pricingForm] = Form.useForm()

  useEffect(() => {
    loadProviders()
  }, [])

  const loadProviders = async () => {
    setLoading(true)
    try {
      const response = await adminProviderApi.list()
      setProviders(response.data || [])
    } catch (error) {
      message.error('加载供应商列表失败')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateProvider = () => {
    setSelectedProvider(null)
    providerForm.resetFields()
    setProviderModalVisible(true)
  }

  const handleEditProvider = (record) => {
    setSelectedProvider(record)
    providerForm.setFieldsValue({
      name: record.name,
      base_url: record.base_url,
      enabled: record.enabled,
    })
    setProviderModalVisible(true)
  }

  const handleSaveProvider = async (values) => {
    try {
      if (selectedProvider) {
        await adminProviderApi.update(selectedProvider.id, values)
        message.success('更新成功')
      } else {
        await adminProviderApi.create(values)
        message.success('创建成功')
      }
      setProviderModalVisible(false)
      loadProviders()
    } catch (error) {
      message.error(selectedProvider ? '更新失败' : '创建失败')
    }
  }

  const handleDeleteProvider = async (id) => {
    try {
      await adminProviderApi.delete(id)
      message.success('删除成功')
      loadProviders()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleManageKeys = async (record) => {
    setSelectedProvider(record)
    try {
      const response = await adminProviderApi.keys(record.id)
      setProviderKeys(response.data || [])
      setKeyModalVisible(true)
    } catch (error) {
      message.error('加载 Key 列表失败')
    }
  }

  const handleAddKey = async (values) => {
    try {
      await adminProviderApi.addKey(selectedProvider.id, values)
      message.success('添加成功')
      keyForm.resetFields()
      // 刷新 Key 列表
      const response = await adminProviderApi.keys(selectedProvider.id)
      setProviderKeys(response.data || [])
    } catch (error) {
      message.error('添加失败')
    }
  }

  const handleDeleteKey = async (keyId) => {
    try {
      await adminProviderApi.deleteKey(selectedProvider.id, keyId)
      message.success('删除成功')
      // 刷新 Key 列表
      const response = await adminProviderApi.keys(selectedProvider.id)
      setProviderKeys(response.data || [])
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleManagePricing = async (record) => {
    setSelectedProvider(record)
    try {
      const response = await adminProviderApi.pricing(record.id)
      setModelPricing(response.data || [])
      setPricingModalVisible(true)
    } catch (error) {
      message.error('加载定价列表失败')
    }
  }

  const handleAddPricing = async (values) => {
    try {
      await adminProviderApi.setPricing(selectedProvider.id, values)
      message.success('添加成功')
      pricingForm.resetFields()
      // 刷新定价列表
      const response = await adminProviderApi.pricing(selectedProvider.id)
      setModelPricing(response.data || [])
    } catch (error) {
      message.error('添加失败')
    }
  }

  const providerColumns = [
    {
      title: '供应商',
      dataIndex: 'name',
      key: 'name',
      render: (name) => <Text strong>{name.toUpperCase()}</Text>,
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
    {
      title: 'Key 数量',
      dataIndex: 'key_count',
      key: 'key_count',
      render: (count) => count || 0,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space wrap>
          <Button type="link" onClick={() => handleManageKeys(record)}>
            Key 管理
          </Button>
          <Button type="link" onClick={() => handleManagePricing(record)}>
            定价
          </Button>
          <Button type="link" onClick={() => handleEditProvider(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个供应商吗？"
            onConfirm={() => handleDeleteProvider(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const keyColumns = [
    {
      title: 'Key 后缀',
      dataIndex: 'key_suffix',
      key: 'key_suffix',
      render: (suffix) => <Text code>...{suffix}</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status) => (
        <Tag color={status === 'active' ? 'success' : 'error'}>
          {status === 'active' ? '正常' : '禁用'}
        </Tag>
      ),
    },
    {
      title: 'RPM 限制',
      dataIndex: 'rpm_limit',
      key: 'rpm_limit',
      render: (rpm) => rpm || '无限制',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (time) => time ? new Date(time).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Popconfirm
          title="确定要删除这个 Key 吗？"
          onConfirm={() => handleDeleteKey(record.id)}
          okText="确定"
          cancelText="取消"
        >
          <Button type="link" danger>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  const pricingColumns = [
    {
      title: '模型名称',
      dataIndex: 'model_name',
      key: 'model_name',
    },
    {
      title: '输入价格 ($/1K tokens)',
      dataIndex: 'input_price_per_1k',
      key: 'input_price_per_1k',
      render: (price) => `$${parseFloat(price || 0).toFixed(6)}`,
    },
    {
      title: '输出价格 ($/1K tokens)',
      dataIndex: 'output_price_per_1k',
      key: 'output_price_per_1k',
      render: (price) => `$${parseFloat(price || 0).toFixed(6)}`,
    },
  ]

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>
            <CloudServerOutlined /> 供应商管理
          </Title>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreateProvider}>
            添加供应商
          </Button>
        </div>

        <Table
          columns={providerColumns}
          dataSource={providers}
          rowKey="id"
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 供应商编辑弹窗 */}
      <Modal
        title={selectedProvider ? '编辑供应商' : '添加供应商'}
        open={providerModalVisible}
        onCancel={() => setProviderModalVisible(false)}
        footer={null}
      >
        <Form form={providerForm} onFinish={handleSaveProvider} layout="vertical">
          <Form.Item
            name="name"
            label="供应商名称"
            rules={[{ required: true, message: '请输入供应商名称' }]}
          >
            <Select disabled={!!selectedProvider}>
              <Select.Option value="openai">OpenAI</Select.Option>
              <Select.Option value="anthropic">Anthropic</Select.Option>
              <Select.Option value="qwen">通义千问</Select.Option>
              <Select.Option value="ernie">文心一言</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="base_url"
            label="API 地址"
            rules={[{ required: true, message: '请输入 API 地址' }]}
          >
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked" initialValue={true}>
            <Switch />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              保存
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* Key 管理弹窗 */}
      <Modal
        title={`Key 管理 - ${selectedProvider?.name?.toUpperCase()}`}
        open={keyModalVisible}
        onCancel={() => {
          setKeyModalVisible(false)
          keyForm.resetFields()
        }}
        footer={null}
        width={700}
      >
        <div style={{ marginBottom: 24 }}>
          <Title level={5}>添加新 Key</Title>
          <Form form={keyForm} onFinish={handleAddKey} layout="inline">
            <Form.Item
              name="api_key"
              rules={[{ required: true, message: '请输入 API Key' }]}
              style={{ flex: 1 }}
            >
              <Input.Password placeholder="输入供应商 API Key" />
            </Form.Item>
            <Form.Item name="rpm_limit">
              <InputNumber placeholder="RPM 限制" min={0} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit">
                添加
              </Button>
            </Form.Item>
          </Form>
        </div>

        <Divider />

        <Title level={5}>已有 Key</Title>
        <Table
          columns={keyColumns}
          dataSource={providerKeys}
          rowKey="id"
          pagination={false}
          size="small"
        />
      </Modal>

      {/* 定价管理弹窗 */}
      <Modal
        title={`模型定价 - ${selectedProvider?.name?.toUpperCase()}`}
        open={pricingModalVisible}
        onCancel={() => {
          setPricingModalVisible(false)
          pricingForm.resetFields()
        }}
        footer={null}
        width={700}
      >
        <div style={{ marginBottom: 24 }}>
          <Title level={5}>添加模型定价</Title>
          <Form form={pricingForm} onFinish={handleAddPricing} layout="inline">
            <Form.Item
              name="model_name"
              rules={[{ required: true, message: '请输入模型名称' }]}
            >
              <Input placeholder="模型名称，如 gpt-4o" style={{ width: 150 }} />
            </Form.Item>
            <Form.Item
              name="input_price_per_1k"
              rules={[{ required: true, message: '请输入价格' }]}
            >
              <InputNumber placeholder="输入价格" min={0} step={0.001} />
            </Form.Item>
            <Form.Item
              name="output_price_per_1k"
              rules={[{ required: true, message: '请输入价格' }]}
            >
              <InputNumber placeholder="输出价格" min={0} step={0.001} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit">
                添加
              </Button>
            </Form.Item>
          </Form>
        </div>

        <Divider />

        <Title level={5}>已有定价</Title>
        <Table
          columns={pricingColumns}
          dataSource={modelPricing}
          rowKey="id"
          pagination={false}
          size="small"
        />
      </Modal>
    </div>
  )
}
