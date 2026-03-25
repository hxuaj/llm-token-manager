/**
 * 管理员 - 供应商管理页面
 *
 * 支持两种创建模式：
 * 1. 快捷创建：选择预设 -> 输入 API Key -> 验证并创建
 * 2. 自定义创建：手动填写所有配置
 */
import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Switch, Select,
  message, Tag, Space, Card, Typography, Popconfirm, Divider, Steps,
  Alert, Spin, List, Badge, Tooltip, Statistic, Descriptions, Drawer
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, KeyOutlined,
  CloudServerOutlined, DollarOutlined, CheckCircleOutlined,
  CloseCircleOutlined, SyncOutlined, ApiOutlined, TeamOutlined,
  ReloadOutlined, UserOutlined, EyeOutlined
} from '@ant-design/icons'
import { adminProviderApi, adminModelApi } from '../api'

const { Title, Text, Paragraph } = Typography
const { TextArea } = Input
const { Step } = Steps

export default function AdminProviders() {
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [providerModalVisible, setProviderModalVisible] = useState(false)
  const [quickCreateModalVisible, setQuickCreateModalVisible] = useState(false)
  const [keyModalVisible, setKeyModalVisible] = useState(false)
  const [pricingModalVisible, setPricingModalVisible] = useState(false)
  const [selectedProvider, setSelectedProvider] = useState(null)
  const [providerKeys, setProviderKeys] = useState([])
  const [modelPricing, setModelPricing] = useState([])
  const [providerForm] = Form.useForm()
  const [keyForm] = Form.useForm()
  const [pricingForm] = Form.useForm()

  // 快捷创建相关状态
  const [presets, setPresets] = useState([])
  const [presetsLoading, setPresetsLoading] = useState(false)
  const [quickCreateForm] = Form.useForm()
  const [currentStep, setCurrentStep] = useState(0)
  const [validating, setValidating] = useState(false)
  const [validationResult, setValidationResult] = useState(null)
  const [creating, setCreating] = useState(false)
  const [selectedPreset, setSelectedPreset] = useState(null)

  // 模型目录相关状态
  const [providerModels, setProviderModels] = useState([])
  const [modelsLoading, setModelsLoading] = useState(false)

  // Key 分配相关状态
  const [keyAssignments, setKeyAssignments] = useState([])
  const [assignmentsLoading, setAssignmentsLoading] = useState(false)
  const [rebalancing, setRebalancing] = useState(false)

  // 分配用户抽屉相关状态
  const [usersDrawerVisible, setUsersDrawerVisible] = useState(false)
  const [selectedKeyInfo, setSelectedKeyInfo] = useState(null)
  const [assignedUsersList, setAssignedUsersList] = useState([])
  const [assignedUsersLoading, setAssignedUsersLoading] = useState(false)

  // Key 管理弹窗 - 添加 Key 验证状态
  const [addKeyValidating, setAddKeyValidating] = useState(false)
  const [addKeyValidated, setAddKeyValidated] = useState(false)

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

  const loadPresets = async () => {
    setPresetsLoading(true)
    try {
      const response = await adminProviderApi.presets()
      setPresets(response.data?.presets || [])
    } catch (error) {
      message.error('加载预设列表失败')
    } finally {
      setPresetsLoading(false)
    }
  }

  // 打开快捷创建弹窗
  const handleQuickCreate = () => {
    setCurrentStep(0)
    setValidationResult(null)
    setSelectedPreset(null)
    quickCreateForm.resetFields()
    loadPresets()
    setQuickCreateModalVisible(true)
  }

  // 选择预设
  const handleSelectPreset = (presetId) => {
    const preset = presets.find(p => p.id === presetId)
    setSelectedPreset(preset)
    if (preset) {
      quickCreateForm.setFieldsValue({
        custom_base_url: null
      })
    }
  }

  // 验证 API Key
  const handleValidateKey = async () => {
    try {
      const values = await quickCreateForm.validateFields(['provider_preset', 'api_key', 'custom_base_url'])
      setValidating(true)
      setValidationResult(null)

      const response = await adminProviderApi.validateKey({
        provider_preset: values.provider_preset,
        api_key: values.api_key,
        custom_base_url: values.custom_base_url || null
      })

      setValidationResult(response.data)
      if (response.data.valid) {
        setCurrentStep(2)
      }
    } catch (error) {
      if (error.response?.data?.detail) {
        message.error(error.response.data.detail)
      } else if (error.errorFields) {
        // 表单验证错误，忽略
      } else {
        message.error('验证失败')
      }
    } finally {
      setValidating(false)
    }
  }

  // 一键创建
  const handleQuickCreateSubmit = async () => {
    try {
      const values = await quickCreateForm.validateFields()
      setCreating(true)

      const response = await adminProviderApi.quickCreate({
        provider_preset: values.provider_preset,
        api_key: values.api_key,
        custom_base_url: values.custom_base_url || null,
        auto_activate_models: true
      })

      message.success(`供应商创建成功！发现 ${response.data.discovery_result.total_models} 个模型，已激活 ${response.data.discovery_result.activated_models} 个`)
      setQuickCreateModalVisible(false)
      loadProviders()
    } catch (error) {
      if (error.response?.data?.detail) {
        message.error(error.response.data.detail)
      } else {
        message.error('创建失败')
      }
    } finally {
      setCreating(false)
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
    setAssignmentsLoading(true)
    try {
      // 并行加载 Key 列表和分配统计
      const [keysRes, assignmentsRes] = await Promise.all([
        adminProviderApi.keys(record.id),
        adminProviderApi.keyAssignments(record.name).catch(() => ({ data: [] }))
      ])
      setProviderKeys(keysRes.data || [])
      setKeyAssignments(assignmentsRes.data || [])
      setKeyModalVisible(true)
    } catch (error) {
      message.error('加载 Key 列表失败')
    } finally {
      setAssignmentsLoading(false)
    }
  }

  const handleRebalanceKeys = async () => {
    if (!selectedProvider) return

    setRebalancing(true)
    try {
      const response = await adminProviderApi.rebalanceKeys(selectedProvider.name)
      const { reassigned, newly_assigned, total_users } = response.data
      let msg = `重平衡完成！共处理 ${total_users} 个用户`
      if (newly_assigned > 0) {
        msg += `，新分配 ${newly_assigned} 个用户`
      }
      if (reassigned > 0) {
        msg += `，重新分配 ${reassigned} 个用户`
      }
      message.success(msg)
      // 刷新分配统计
      const assignmentsRes = await adminProviderApi.keyAssignments(selectedProvider.name)
      setKeyAssignments(assignmentsRes.data || [])
    } catch (error) {
      message.error(error.response?.data?.detail || '重平衡失败')
    } finally {
      setRebalancing(false)
    }
  }

  // 获取 Key 的分配用户数
  const getKeyAssignedUsers = (keyId) => {
    const assignment = keyAssignments.find(a => a.key_id === keyId)
    return assignment?.assigned_users || 0
  }

  // 显示分配给某个 Key 的用户列表
  const handleShowAssignedUsers = async (keyRecord) => {
    setSelectedKeyInfo(keyRecord)
    setUsersDrawerVisible(true)
    setAssignedUsersLoading(true)

    try {
      const response = await adminProviderApi.keyAssignedUsers(
        selectedProvider.name,
        keyRecord.id
      )
      setAssignedUsersList(response.data || [])
    } catch (error) {
      message.error('加载用户列表失败')
      setAssignedUsersList([])
    } finally {
      setAssignedUsersLoading(false)
    }
  }

  // 验证新 Key
  const handleValidateAddKey = async () => {
    try {
      const values = await keyForm.validateFields(['api_key'])
      setAddKeyValidating(true)

      const response = await adminProviderApi.validateKey({
        provider_preset: selectedProvider.name,
        api_key: values.api_key,
        custom_base_url: null
      })

      if (response.data.valid) {
        setAddKeyValidated(true)
        message.success('验证成功')
      } else {
        message.error(response.data.error?.message || '验证失败')
      }
    } catch (error) {
      if (error.response?.data?.detail) {
        message.error(error.response.data.detail)
      } else if (!error.errorFields) {
        message.error('验证失败')
      }
    } finally {
      setAddKeyValidating(false)
    }
  }

  // 添加新 Key
  const handleAddKey = async (values) => {
    if (!addKeyValidated) {
      message.warning('请先验证 Key')
      return
    }
    try {
      await adminProviderApi.addKey(selectedProvider.id, values)
      message.success('添加成功')
      keyForm.resetFields()
      setAddKeyValidated(false)
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
      const response = await adminProviderApi.keys(selectedProvider.id)
      setProviderKeys(response.data || [])
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleManagePricing = async (record) => {
    setSelectedProvider(record)
    setModelsLoading(true)
    try {
      // 加载模型目录（包含定价信息）
      const modelsResponse = await adminModelApi.list(record.id)
      const models = modelsResponse.data?.models || []
      setProviderModels(models)
      // 直接使用模型目录数据作为定价数据
      setModelPricing(models.filter(m => m.status === 'active' || m.status === 'pending'))

      setPricingModalVisible(true)
    } catch (error) {
      message.error('加载数据失败')
    } finally {
      setModelsLoading(false)
    }
  }

  const handleModelSelect = (modelId) => {
    const selectedModel = providerModels.find(m => m.model_id === modelId)
    if (selectedModel) {
      // 定价单位已经是 USD/1M tokens，直接使用
      pricingForm.setFieldsValue({
        input_price: selectedModel.input_price || 0,
        output_price: selectedModel.output_price || 0,
        cache_write_price: selectedModel.cache_write_price || null,
        cache_read_price: selectedModel.cache_read_price || null
      })
    }
  }

  const handleUpdatePricing = async (values) => {
    try {
      // 使用模型 ID 更新定价
      await adminModelApi.updatePricing(values.model_id, {
        input_price: values.input_price,
        output_price: values.output_price,
        cache_write_price: values.cache_write_price || null,
        cache_read_price: values.cache_read_price || null
      })
      message.success('定价更新成功')
      pricingForm.resetFields()
      // 重新加载模型列表
      const modelsResponse = await adminModelApi.list(selectedProvider.id)
      const models = modelsResponse.data?.models || []
      setProviderModels(models)
      setModelPricing(models.filter(m => m.status === 'active' || m.status === 'pending'))
    } catch (error) {
      message.error('更新失败')
    }
  }

  const providerColumns = [
    {
      title: '供应商',
      dataIndex: 'display_name',
      key: 'display_name',
      render: (name, record) => (
        <Space>
          <Text strong>{name || record.name?.toUpperCase()}</Text>
          {record.source === 'preset' && (
            <Tag color="blue">预设</Tag>
          )}
        </Space>
      ),
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
      title: '支持端点',
      dataIndex: 'supported_endpoints',
      key: 'supported_endpoints',
      render: (endpoints) => (
        <Space>
          {endpoints?.includes('openai') && <Tag>OpenAI</Tag>}
          {endpoints?.includes('anthropic') && <Tag color="purple">Anthropic</Tag>}
        </Space>
      ),
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
      title: 'Key 类型',
      dataIndex: 'key_plan',
      key: 'key_plan',
      render: (plan) => (
        <Tag color={plan === 'coding_plan' ? 'purple' : 'default'}>
          {plan === 'coding_plan' ? 'Coding Plan' : 'Standard'}
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
      title: (
        <Tooltip title="绑定该 Key 为 Primary Key 的用户数">
          <span><UserOutlined /> 分配用户</span>
        </Tooltip>
      ),
      dataIndex: 'assigned_users',
      key: 'assigned_users',
      render: (_, record) => {
        const count = getKeyAssignedUsers(record.id)
        return (
          <Badge
            count={count}
            showZero
            color={count === 0 ? '#d9d9d9' : '#1890ff'}
            overflowCount={999}
            style={{ cursor: 'pointer' }}
            onClick={() => count > 0 && handleShowAssignedUsers(record)}
            title={count > 0 ? '点击查看用户列表' : '暂无用户'}
          />
        )
      },
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
          title="确定要删除这个 Key 吗？已绑定该 Key 的用户将自动解除绑定。"
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
      title: '模型 ID',
      dataIndex: 'model_id',
      key: 'model_id',
      render: (id, record) => (
        <Space direction="vertical" size={0}>
          <Text strong>{record.display_name}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{id}</Text>
        </Space>
      ),
    },
    {
      title: '输入价格 ($/1M)',
      dataIndex: 'input_price',
      key: 'input_price',
      render: (price) => `$${parseFloat(price || 0).toFixed(4)}`,
    },
    {
      title: '输出价格 ($/1M)',
      dataIndex: 'output_price',
      key: 'output_price',
      render: (price) => `$${parseFloat(price || 0).toFixed(4)}`,
    },
    {
      title: '缓存写入 ($/1M)',
      dataIndex: 'cache_write_price',
      key: 'cache_write_price',
      render: (price) => price != null ? `$${parseFloat(price).toFixed(4)}` : '-',
    },
    {
      title: '缓存读取 ($/1M)',
      dataIndex: 'cache_read_price',
      key: 'cache_read_price',
      render: (price) => price != null ? `$${parseFloat(price).toFixed(4)}` : '-',
    },
    {
      title: '定价来源',
      dataIndex: 'is_pricing_confirmed',
      key: 'is_pricing_confirmed',
      render: (confirmed) => (
        <Tag color={confirmed ? 'green' : 'orange'}>
          {confirmed ? '已确认' : '待配置'}
        </Tag>
      ),
    },
  ]

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>
            <CloudServerOutlined /> 供应商管理
          </Title>
          <Space>
            <Button icon={<PlusOutlined />} onClick={handleCreateProvider}>
              自定义创建
            </Button>
            <Button type="primary" icon={<ApiOutlined />} onClick={handleQuickCreate}>
              快捷创建
            </Button>
          </Space>
        </div>

        <Table
          columns={providerColumns}
          dataSource={providers}
          rowKey="id"
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 快捷创建弹窗 */}
      <Modal
        title="快捷创建供应商"
        open={quickCreateModalVisible}
        onCancel={() => setQuickCreateModalVisible(false)}
        footer={null}
        width={700}
      >
        <Steps current={currentStep} style={{ marginBottom: 24 }}>
          <Step title="选择预设" description="选择供应商类型" />
          <Step title="验证 Key" description="验证 API Key" />
          <Step title="确认创建" description="创建供应商" />
        </Steps>

        <Form form={quickCreateForm} layout="vertical">
          {/* Step 0: 选择预设 */}
          <div style={{ display: currentStep === 0 ? 'block' : 'none' }}>
            <Form.Item
              name="provider_preset"
              label="供应商类型"
              rules={[{ required: true, message: '请选择供应商类型' }]}
            >
              <Select
                placeholder="选择供应商"
                loading={presetsLoading}
                onChange={handleSelectPreset}
                showSearch
                filterOption={(input, option) =>
                  option.children?.toLowerCase().includes(input.toLowerCase())
                }
              >
                {presets.map(preset => (
                  <Select.Option key={preset.id} value={preset.id}>
                    {preset.display_name}
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>

            {selectedPreset && (
              <Alert
                type="info"
                style={{ marginBottom: 16 }}
                message={
                  <div>
                    <Paragraph style={{ marginBottom: 8 }}>
                      <Text strong>{selectedPreset.display_name}</Text>
                    </Paragraph>
                    <Paragraph style={{ marginBottom: 8 }}>
                      {selectedPreset.description}
                    </Paragraph>
                    <Space>
                      <Text type="secondary">支持端点:</Text>
                      {selectedPreset.supported_endpoints?.map(ep => (
                        <Tag key={ep} color={ep === 'anthropic' ? 'purple' : 'default'}>
                          {ep.toUpperCase()}
                        </Tag>
                      ))}
                    </Space>
                  </div>
                }
              />
            )}

            <Form.Item>
              <Button
                type="primary"
                onClick={() => setCurrentStep(1)}
                disabled={!selectedPreset}
              >
                下一步
              </Button>
            </Form.Item>
          </div>

          {/* Step 1: 输入并验证 API Key */}
          <div style={{ display: currentStep === 1 ? 'block' : 'none' }}>
            <Alert
              type="info"
              style={{ marginBottom: 16 }}
              message={
                <div>
                  <Text>供应商: <strong>{selectedPreset?.display_name}</strong></Text>
                  <br />
                  <Text type="secondary">默认 API 地址: {selectedPreset?.default_base_url}</Text>
                </div>
              }
            />

            <Form.Item
              name="api_key"
              label="API Key"
              rules={[{ required: true, message: '请输入 API Key' }]}
            >
              <Input.Password placeholder="输入供应商 API Key" />
            </Form.Item>

            <Form.Item
              name="custom_base_url"
              label="自定义 API 地址（可选）"
              extra="留空使用默认地址"
            >
              <Input placeholder={selectedPreset?.default_base_url} />
            </Form.Item>

            <Form.Item>
              <Space>
                <Button onClick={() => setCurrentStep(0)}>
                  上一步
                </Button>
                <Button
                  type="primary"
                  onClick={handleValidateKey}
                  loading={validating}
                  icon={validating ? <SyncOutlined spin /> : null}
                >
                  验证并发现模型
                </Button>
              </Space>
            </Form.Item>
          </div>

          {/* Step 2: 确认创建 */}
          {currentStep === 2 && validationResult && (
            <>
              {validationResult.valid ? (
                <>
                  <Alert
                    type="success"
                    style={{ marginBottom: 16 }}
                    message="验证成功"
                    description={
                      <div>
                        <Text>发现 {validationResult.summary?.total_models || 0} 个可用模型</Text>
                        <br />
                        <Text type="secondary">
                          定价已确认: {validationResult.summary?.pricing_confirmed || 0} 个，
                          待配置: {validationResult.summary?.pricing_pending || 0} 个
                        </Text>
                      </div>
                    }
                  />

                  {validationResult.discovered_models?.length > 0 && (
                    <div style={{ marginBottom: 16 }}>
                      <Title level={5}>发现的模型</Title>
                      <List
                        size="small"
                        bordered
                        dataSource={validationResult.discovered_models.slice(0, 10)}
                        renderItem={model => (
                          <List.Item>
                            <Space>
                              <Text>{model.display_name}</Text>
                              <Tag>{model.model_id}</Tag>
                              {model.is_pricing_confirmed ? (
                                <Tag color="green">定价已确认</Tag>
                              ) : (
                                <Tag color="orange">定价待配置</Tag>
                              )}
                            </Space>
                          </List.Item>
                        )}
                        locale={{ emptyText: '暂无模型' }}
                      />
                      {validationResult.discovered_models.length > 10 && (
                        <Text type="secondary" style={{ marginTop: 8, display: 'block' }}>
                          还有 {validationResult.discovered_models.length - 10} 个模型...
                        </Text>
                      )}
                    </div>
                  )}

                  <Form.Item>
                    <Space>
                      <Button onClick={() => {
                        setCurrentStep(1)
                        setValidationResult(null)
                      }}>
                        重新验证
                      </Button>
                      <Button
                        type="primary"
                        onClick={handleQuickCreateSubmit}
                        loading={creating}
                      >
                        确认创建
                      </Button>
                    </Space>
                  </Form.Item>
                </>
              ) : (
                <>
                  <Alert
                    type="error"
                    style={{ marginBottom: 16 }}
                    message="验证失败"
                    description={validationResult.error?.message || '未知错误'}
                  />
                  <Form.Item>
                    <Button onClick={() => {
                      setCurrentStep(1)
                      setValidationResult(null)
                    }}>
                      返回修改
                    </Button>
                  </Form.Item>
                </>
              )}
            </>
          )}
        </Form>
      </Modal>

      {/* 供应商编辑弹窗 */}
      <Modal
        title={selectedProvider ? '编辑供应商' : '自定义创建供应商'}
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
            <Input placeholder="例如: my-custom-provider" disabled={!!selectedProvider} />
          </Form.Item>
          <Form.Item
            name="base_url"
            label="API 地址"
            rules={[{ required: true, message: '请输入 API 地址' }]}
          >
            <Input placeholder="https://api.example.com/v1" />
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
        title={`Key 管理 - ${selectedProvider?.display_name || selectedProvider?.name?.toUpperCase()}`}
        open={keyModalVisible}
        onCancel={() => {
          setKeyModalVisible(false)
          keyForm.resetFields()
          setKeyAssignments([])
          setAddKeyValidated(false)
        }}
        footer={null}
        width={800}
      >
        {/* Key 分配统计概览 */}
        {keyAssignments.length > 0 && (
          <Alert
            type="info"
            style={{ marginBottom: 16 }}
            message={
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                  <TeamOutlined />
                  <span>共 {keyAssignments.reduce((sum, k) => sum + k.assigned_users, 0)} 个用户绑定到此供应商的 Key</span>
                </Space>
                <Tooltip title="重新均匀分配用户到各个 Key">
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    loading={rebalancing}
                    onClick={handleRebalanceKeys}
                  >
                    重平衡
                  </Button>
                </Tooltip>
              </div>
            }
          />
        )}

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
            <Form.Item name="rpm_limit" initialValue={0}>
              <InputNumber placeholder="0 表示无限制" min={0} />
            </Form.Item>
            <Form.Item>
              <Space>
                <Button
                  icon={<CheckCircleOutlined />}
                  loading={addKeyValidating}
                  onClick={handleValidateAddKey}
                >
                  验证
                </Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  disabled={!addKeyValidated}
                >
                  添加
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </div>

        <Divider />

        <Title level={5}>已有 Key</Title>
        <Spin spinning={assignmentsLoading}>
          <Table
            columns={keyColumns}
            dataSource={providerKeys}
            rowKey="id"
            pagination={false}
            size="small"
          />
        </Spin>
      </Modal>

      {/* 定价管理弹窗 */}
      <Modal
        title={`模型定价 - ${selectedProvider?.display_name || selectedProvider?.name?.toUpperCase()}`}
        open={pricingModalVisible}
        onCancel={() => {
          setPricingModalVisible(false)
          pricingForm.resetFields()
          setProviderModels([])
        }}
        footer={null}
        width={1000}
      >
        <div style={{ marginBottom: 24 }}>
          <Title level={5}>更新模型定价</Title>
          <Form form={pricingForm} onFinish={handleUpdatePricing} layout="inline">
            <Form.Item
              name="model_id"
              rules={[{ required: true, message: '请选择模型' }]}
            >
              <Select
                placeholder="选择模型"
                style={{ width: 250 }}
                loading={modelsLoading}
                showSearch
                filterOption={(input, option) => {
                  const label = option.children?.toString().toLowerCase() || ''
                  const value = option.value?.toLowerCase() || ''
                  return label.includes(input.toLowerCase()) || value.includes(input.toLowerCase())
                }}
                onChange={handleModelSelect}
              >
                {providerModels.map(model => (
                  <Select.Option key={model.id} value={model.model_id}>
                    {model.display_name} ({model.model_id})
                  </Select.Option>
                ))}
              </Select>
            </Form.Item>
            <Form.Item
              name="input_price"
              rules={[{ required: true, message: '请输入价格' }]}
            >
              <InputNumber placeholder="输入价格 ($/1M)" min={0} step={0.01} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item
              name="output_price"
              rules={[{ required: true, message: '请输入价格' }]}
            >
              <InputNumber placeholder="输出价格 ($/1M)" min={0} step={0.01} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="cache_write_price">
              <InputNumber placeholder="缓存写入 ($/1M)" min={0} step={0.01} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item name="cache_read_price">
              <InputNumber placeholder="缓存读取 ($/1M)" min={0} step={0.01} style={{ width: 140 }} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit">
                更新
              </Button>
            </Form.Item>
          </Form>
        </div>

        <Divider />

        <Title level={5}>模型列表</Title>
        <Table
          columns={pricingColumns}
          dataSource={modelPricing}
          rowKey="id"
          pagination={false}
          size="small"
        />
      </Modal>

      {/* 分配用户列表抽屉 */}
      <Drawer
        title={
          <Space>
            <UserOutlined />
            <span>分配用户 - ...{selectedKeyInfo?.key_suffix}</span>
          </Space>
        }
        placement="right"
        width={600}
        open={usersDrawerVisible}
        onClose={() => {
          setUsersDrawerVisible(false)
          setSelectedKeyInfo(null)
          setAssignedUsersList([])
        }}
      >
        {assignedUsersLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <Spin />
          </div>
        ) : assignedUsersList.length === 0 ? (
          <Alert type="info" message="暂无用户绑定此 Key" />
        ) : (
          <>
            <Alert
              type="info"
              style={{ marginBottom: 16 }}
              message={`共 ${assignedUsersList.length} 个用户绑定此 Key`}
            />
            <Table
              dataSource={assignedUsersList}
              rowKey="id"
              size="small"
              pagination={assignedUsersList.length > 10 ? { pageSize: 10 } : false}
              columns={[
                {
                  title: '用户名',
                  dataIndex: 'username',
                  key: 'username',
                  width: 150,
                  render: (name) => <Text strong>{name}</Text>,
                },
                {
                  title: '邮箱',
                  dataIndex: 'email',
                  key: 'email',
                  ellipsis: true,
                  render: (email) => <Text type="secondary">{email}</Text>,
                },
              ]}
            />
          </>
        )}
      </Drawer>
    </div>
  )
}
