import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select,
  Popconfirm, Tag, Message, Typography
} from '@arco-design/web-react'
import { getAdminUsers, promoteUser, demoteUser } from '../../api/users'
import { useAuthStore } from '../../store/auth'

const Users: React.FC = () => {
  const { username: currentUser } = useAuthStore()
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const [form] = Form.useForm()

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getAdminUsers()
      setData(Array.isArray(res.data) ? res.data : [])
    } catch {
      // 普通用户无权限时静默处理
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handlePromote = async (values: { username: string; role: string }) => {
    try {
      await promoteUser(values as any)
      Message.success('操作成功')
      setVisible(false)
      form.resetFields()
      fetchData()
    } catch {
      Message.error('操作失败')
    }
  }

  const handleDemote = async (username: string) => {
    try {
      await demoteUser(username)
      Message.success('已降权')
      fetchData()
    } catch (err: any) {
      Message.error(err?.response?.data?.detail || '降权失败')
    }
  }

  const columns = [
    { title: '用户名', dataIndex: 'username' },
    {
      title: '角色',
      dataIndex: 'role',
      render: (role: string) => (
        <Tag color={role === 'superadmin' ? 'red' : 'arcoblue'}>
          {role === 'superadmin' ? '超级管理员' : '管理员'}
        </Tag>
      )
    },
    { title: '提权人', dataIndex: 'created_by', render: (v: string) => v || 'system' },
    { title: '提权时间', dataIndex: 'created_at', render: (v: string) => v?.slice(0, 19) },
    {
      title: '操作',
      render: (_: any, row: any) => (
        <Popconfirm
          title={`确认降权用户 ${row.username}？`}
          onOk={() => handleDemote(row.username)}
        >
          <Button
            size="mini"
            type="text"
            status="danger"
            disabled={row.username === currentUser}
          >
            降权
          </Button>
        </Popconfirm>
      )
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title heading={5} style={{ margin: 0 }}>用户权限管理</Typography.Title>
        <Button type="primary" onClick={() => setVisible(true)}>提权用户</Button>
      </div>

      <Table columns={columns} data={data} loading={loading} rowKey="username" />

      <Modal
        title="提权用户"
        visible={visible}
        onCancel={() => { setVisible(false); form.resetFields() }}
        onOk={() => form.submit()}
      >
        <Form form={form} onSubmit={handlePromote} layout="vertical">
          <Form.Item field="username" label="LDAP 用户名" rules={[{ required: true }]}>
            <Input placeholder="输入域账号（不含域前缀）" />
          </Form.Item>
          <Form.Item field="role" label="角色" rules={[{ required: true }]} initialValue="admin">
            <Select options={[
              { label: '管理员', value: 'admin' },
              { label: '超级管理员', value: 'superadmin' },
            ]} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Users
