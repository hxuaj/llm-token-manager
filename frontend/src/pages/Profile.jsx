/**
 * 个人设置页面
 */
import React, { useState } from 'react'
import { Card, Form, Input, Button, message, Typography, Divider, Descriptions } from 'antd'
import { LockOutlined, UserOutlined, MailOutlined } from '@ant-design/icons'
import { useAuth } from '../components/AuthContext'
import { authApi } from '../api'

const { Title, Text } = Typography

export default function Profile() {
  const [loading, setLoading] = useState(false)
  const [form] = Form.useForm()
  const { user } = useAuth()

  const handleChangePassword = async (values) => {
    setLoading(true)
    try {
      await authApi.changePassword({
        old_password: values.old_password,
        new_password: values.new_password,
      })
      message.success('密码修改成功')
      form.resetFields()
    } catch (error) {
      const detail = error.response?.data?.detail
      if (typeof detail === 'string') {
        message.error(detail)
      } else {
        message.error('密码修改失败')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: '24px', maxWidth: 800, margin: '0 auto' }}>
      <Card>
        <Title level={4} style={{ marginTop: 0 }}>个人信息</Title>
        <Descriptions column={1} styles={{ label: { width: 100 } }}>
          <Descriptions.Item label="用户名">
            <Text><UserOutlined style={{ marginRight: 8 }} />{user?.username}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="邮箱">
            <Text><MailOutlined style={{ marginRight: 8 }} />{user?.email}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="真实姓名">
            <Text>{user?.real_name}</Text>
          </Descriptions.Item>
          <Descriptions.Item label="角色">
            <Text>{user?.role === 'admin' ? '管理员' : '普通用户'}</Text>
          </Descriptions.Item>
        </Descriptions>

        <Divider />

        <Title level={4}>修改密码</Title>
        <Form
          form={form}
          layout="vertical"
          onFinish={handleChangePassword}
          style={{ maxWidth: 400 }}
        >
          <Form.Item
            name="old_password"
            label="当前密码"
            rules={[{ required: true, message: '请输入当前密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入当前密码"
            />
          </Form.Item>

          <Form.Item
            name="new_password"
            label="新密码"
            rules={[
              { required: true, message: '请输入新密码' },
              { min: 6, message: '密码长度至少 6 位' },
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请输入新密码（至少 6 位）"
            />
          </Form.Item>

          <Form.Item
            name="confirm_password"
            label="确认新密码"
            dependencies={['new_password']}
            rules={[
              { required: true, message: '请确认新密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) {
                    return Promise.resolve()
                  }
                  return Promise.reject(new Error('两次输入的密码不一致'))
                },
              }),
            ]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              placeholder="请再次输入新密码"
            />
          </Form.Item>

          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading}>
              修改密码
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
