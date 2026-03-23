/**
 * 管理员 - 用户管理页面
 */
import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, Switch, message,
  Tag, Space, Card, Typography, Popconfirm, Descriptions, Divider, Spin,
  Badge, Tooltip, Alert
} from 'antd'
import {
  EditOutlined, KeyOutlined, EyeOutlined, SearchOutlined,
  ApiOutlined, SettingOutlined, UserOutlined
} from '@ant-design/icons'
import { adminUserApi, adminProviderApi } from '../api'

const { Title, Text } = Typography

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [detailModalVisible, setDetailModalVisible] = useState(false)
  const [primaryKeyModalVisible, setPrimaryKeyModalVisible] = useState(false)
  const [selectedUser, setSelectedUser] = useState(null)
  const [userKeys, setUserKeys] = useState([])
  const [editForm] = Form.useForm()
  const [searchText, setSearchText] = useState('')

  // Primary Key 管理相关状态
  const [userPrimaryKeys, setUserPrimaryKeys] = useState({})
  const [providers, setProviders] = useState([])
  const [providerKeys, setProviderKeys] = useState([])
  const [selectedProviderName, setSelectedProviderName] = useState(null)
  const [savingPrimaryKey, setSavingPrimaryKey] = useState(false)
  const [loadingProviderKeys, setLoadingProviderKeys] = useState(false)
  const [primaryKeyForm] = Form.useForm()

  useEffect(() => {
    loadUsers()
  }, [])

  const loadUsers = async () => {
    setLoading(true)
    try {
      const response = await adminUserApi.list()
      setUsers(response.data.items || response.data || [])
    } catch (error) {
      message.error('加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  const handleEdit = (record) => {
    setSelectedUser(record)
    editForm.setFieldsValue({
      monthly_quota_usd: parseFloat(record.monthly_quota_usd || 0),
      rpm_limit: record.rpm_limit || 30,
      max_keys: record.max_keys || 5,
      role: record.role || 'user',
      is_active: record.is_active !== false,
    })
    setEditModalVisible(true)
  }

  const handleUpdate = async (values) => {
    try {
      await adminUserApi.update(selectedUser.id, values)
      message.success('更新成功')
      setEditModalVisible(false)
      loadUsers()
    } catch (error) {
      message.error('更新失败')
    }
  }

  const handleViewDetail = async (record) => {
    setSelectedUser(record)
    setDetailModalVisible(true)
    try {
      const response = await adminUserApi.keys(record.id)
      setUserKeys(response.data || [])
    } catch (error) {
      setUserKeys([])
    }
  }

  const handleRevokeKey = async (keyId) => {
    try {
      await adminUserApi.revokeKey(selectedUser.id, keyId)
      message.success('Key 已吊销')
      // 刷新 Key 列表
      const response = await adminUserApi.keys(selectedUser.id)
      setUserKeys(response.data || [])
    } catch (error) {
      message.error('吊销失败')
    }
  }

  // Primary Key 管理函数
  const handleManagePrimaryKeys = async (record) => {
    setSelectedUser(record)
    setUserPrimaryKeys(record.primary_provider_keys || {})
    try {
      // 加载供应商列表
      const response = await adminProviderApi.list()
      setProviders(response.data || [])
      setPrimaryKeyModalVisible(true)
    } catch (error) {
      message.error('加载供应商列表失败')
    }
  }

  const handleProviderSelect = async (providerName) => {
    setSelectedProviderName(providerName)
    setLoadingProviderKeys(true)
    setProviderKeys([])

    const provider = providers.find(p => p.name === providerName)
    if (provider) {
      try {
        const keysRes = await adminProviderApi.keys(provider.id)
        setProviderKeys(keysRes.data || [])
        // 设置当前选中的 Key
        const currentKeyId = userPrimaryKeys[providerName]
        primaryKeyForm.setFieldsValue({ key_id: currentKeyId || undefined })
      } catch (error) {
        setProviderKeys([])
      } finally {
        setLoadingProviderKeys(false)
      }
    } else {
      setLoadingProviderKeys(false)
    }
  }

  const handleSetPrimaryKey = async (values) => {
    if (!selectedUser || !selectedProviderName || !values.key_id) {
      message.warning('请选择供应商和 Key')
      return
    }

    setSavingPrimaryKey(true)
    try {
      await adminUserApi.setPrimaryKey(selectedUser.id, {
        provider_name: selectedProviderName,
        key_id: values.key_id
      })
      message.success('Primary Key 更新成功')
      // 更新本地状态
      setUserPrimaryKeys(prev => ({
        ...prev,
        [selectedProviderName]: values.key_id
      }))
      // 刷新用户列表
      loadUsers()
    } catch (error) {
      message.error(error.response?.data?.detail || '设置失败')
    } finally {
      setSavingPrimaryKey(false)
    }
  }

  // 获取 Key 的友好显示名称
  const getKeyDisplayName = (keyId) => {
    if (!keyId || !providerKeys.length) return null
    const key = providerKeys.find(k => k.id === keyId)
    return key ? `...${key.key_suffix}` : keyId
  }

  const columns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
      filteredValue: searchText ? [searchText] : null,
      onFilter: (value, record) =>
        record.username?.toLowerCase().includes(value.toLowerCase()) ||
        record.email?.toLowerCase().includes(value.toLowerCase()),
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
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active) => (
        <Tag color={active !== false ? 'success' : 'default'}>
          {active !== false ? '正常' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '月度额度',
      dataIndex: 'monthly_quota_usd',
      key: 'monthly_quota_usd',
      render: (quota) => `$${parseFloat(quota || 0).toFixed(2)}`,
    },
    {
      title: 'Key 数量',
      dataIndex: 'key_count',
      key: 'key_count',
      render: (count) => <Badge count={count || 0} showZero color="blue" />,
    },
    {
      title: '操作',
      key: 'action',
      render: (_, record) => (
        <Space wrap>
          <Button
            type="link"
            size="small"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record)}
          >
            详情
          </Button>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            icon={<SettingOutlined />}
            onClick={() => handleManagePrimaryKeys(record)}
          >
            Primary Key
          </Button>
        </Space>
      ),
    },
  ]

  const keyColumns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'Key',
      key: 'key',
      render: (_, record) => (
        <span style={{ fontFamily: 'monospace' }}>
          {record.key_prefix}...{record.key_suffix}
        </span>
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
      title: '操作',
      key: 'action',
      render: (_, record) => (
        record.status === 'active' && (
          <Popconfirm
            title="确定要吊销这个 Key 吗？"
            onConfirm={() => handleRevokeKey(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger size="small">
              吊销
            </Button>
          </Popconfirm>
        )
      ),
    },
  ]

  return (
    <div style={{ padding: '24px' }}>
      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}>
            <UserOutlined /> 用户管理
          </Title>
          <Input
            placeholder="搜索用户名或邮箱"
            prefix={<SearchOutlined />}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
        </div>

        <Table
          columns={columns}
          dataSource={users}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
      </Card>

      {/* 编辑用户弹窗 */}
      <Modal
        title="编辑用户"
        open={editModalVisible}
        onCancel={() => setEditModalVisible(false)}
        footer={null}
      >
        <Form form={editForm} onFinish={handleUpdate} layout="vertical">
          <Form.Item name="monthly_quota_usd" label="月度额度 (USD)">
            <InputNumber min={0} step={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="rpm_limit" label="RPM 限制">
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="max_keys" label="最大 Key 数量">
            <InputNumber min={1} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="role" label="角色">
            <Select>
              <Select.Option value="user">普通用户</Select.Option>
              <Select.Option value="admin">管理员</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item name="is_active" label="状态" valuePropName="checked">
            <Switch checkedChildren="正常" unCheckedChildren="禁用" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>
              保存
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* 用户详情弹窗 */}
      <Modal
        title="用户详情"
        open={detailModalVisible}
        onCancel={() => setDetailModalVisible(false)}
        footer={null}
        width={700}
      >
        {selectedUser && (
          <div>
            <Descriptions bordered column={2} size="small" style={{ marginBottom: 24 }}>
              <Descriptions.Item label="用户名">{selectedUser.username}</Descriptions.Item>
              <Descriptions.Item label="邮箱">{selectedUser.email}</Descriptions.Item>
              <Descriptions.Item label="角色">
                <Tag color={selectedUser.role === 'admin' ? 'red' : 'blue'}>
                  {selectedUser.role === 'admin' ? '管理员' : '普通用户'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={selectedUser.is_active !== false ? 'success' : 'default'}>
                  {selectedUser.is_active !== false ? '正常' : '禁用'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="月度额度">
                ${parseFloat(selectedUser.monthly_quota_usd || 0).toFixed(2)}
              </Descriptions.Item>
              <Descriptions.Item label="RPM 限制">
                {selectedUser.rpm_limit || 30}/min
              </Descriptions.Item>
            </Descriptions>

            <Title level={5}>用户的 Key 列表</Title>
            <Table
              columns={keyColumns}
              dataSource={userKeys}
              rowKey="id"
              pagination={false}
              size="small"
            />
          </div>
        )}
      </Modal>

      {/* Primary Key 管理弹窗 */}
      <Modal
        title={
          <Space>
            <SettingOutlined />
            <span>管理 Primary Key - {selectedUser?.username}</span>
          </Space>
        }
        open={primaryKeyModalVisible}
        onCancel={() => {
          setPrimaryKeyModalVisible(false)
          setSelectedProviderName(null)
          setProviderKeys([])
        }}
        destroyOnHidden
        footer={null}
        width={600}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="Primary Key 是用户在该供应商上的主要绑定 Key。当用户的 Primary Key RPM 满时，会自动溢出到其他 Key。"
        />

        <Form layout="vertical">
          <Form.Item label="选择供应商">
            <Select
              placeholder="选择供应商"
              onChange={handleProviderSelect}
              value={selectedProviderName}
            >
              {providers.map(p => (
                <Select.Option key={p.id} value={p.name}>
                  <Space>
                    <span>{p.display_name || p.name}</span>
                    {userPrimaryKeys[p.name] && (
                      <Tag color="green" style={{ marginLeft: 8 }}>
                        已绑定
                      </Tag>
                    )}
                  </Space>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        </Form>

        {selectedProviderName && (
          <Spin spinning={loadingProviderKeys}>
            <Card size="small" title={`设置 ${selectedProviderName} 的 Primary Key`}>
              <Form
                form={primaryKeyForm}
                onFinish={handleSetPrimaryKey}
                layout="vertical"
              >
                <Form.Item
                  name="key_id"
                  label="选择 Key"
                  rules={[{ required: true, message: '请选择一个 Key' }]}
                >
                  <Select
                    placeholder="选择 Primary Key"
                    allowClear
                  >
                    {providerKeys
                      .filter(k => k.status === 'active')
                      .map(k => (
                        <Select.Option key={k.id} value={k.id}>
                          <Space>
                            <Text code>...{k.key_suffix}</Text>
                            <Text type="secondary">
                              RPM: {k.rpm_limit || '无限'}
                            </Text>
                          </Space>
                        </Select.Option>
                      ))}
                  </Select>
                </Form.Item>

                <Form.Item>
                  <Space>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={savingPrimaryKey}
                    >
                      保存
                    </Button>
                    <Button onClick={() => {
                      setSelectedProviderName(null)
                      setProviderKeys([])
                      primaryKeyForm.resetFields()
                    }}>
                      取消
                    </Button>
                  </Space>
                </Form.Item>
              </Form>
            </Card>
          </Spin>
        )}

        {/* 当前绑定的 Primary Keys */}
        {Object.keys(userPrimaryKeys).length > 0 && (
          <div style={{ marginTop: 24 }}>
            <Divider />
            <Title level={5}>当前 Primary Key 绑定</Title>
            <Descriptions bordered size="small" column={1}>
              {Object.entries(userPrimaryKeys).map(([providerName, keyId]) => (
                <Descriptions.Item key={providerName} label={providerName}>
                  <Space>
                    <Text code>{keyId ? `${keyId.slice(0, 8)}...` : '未设置'}</Text>
                    <Button
                      type="link"
                      size="small"
                      onClick={() => handleProviderSelect(providerName)}
                    >
                      修改
                    </Button>
                  </Space>
                </Descriptions.Item>
              ))}
            </Descriptions>
          </div>
        )}
      </Modal>
    </div>
  )
}
