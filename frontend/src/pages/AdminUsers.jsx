/**
 * 管理员 - 用户管理页面
 */
import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, Switch, message,
  Tag, Space, Card, Typography, Popconfirm, Descriptions
} from 'antd'
import {
  EditOutlined, KeyOutlined, EyeOutlined, SearchOutlined
} from '@ant-design/icons'
import { adminUserApi } from '../api'

const { Title } = Typography

export default function AdminUsers() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [detailModalVisible, setDetailModalVisible] = useState(false)
  const [selectedUser, setSelectedUser] = useState(null)
  const [userKeys, setUserKeys] = useState([])
  const [editForm] = Form.useForm()
  const [searchText, setSearchText] = useState('')

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
      title: 'RPM 限制',
      dataIndex: 'rpm_limit',
      key: 'rpm_limit',
      render: (rpm) => `${rpm || 30}/min`,
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
        <Space>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => handleViewDetail(record)}
          >
            详情
          </Button>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
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
            <Button type="link" danger>
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
            <KeyOutlined /> 用户管理
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
    </div>
  )
}
