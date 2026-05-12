import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select,
  Popconfirm, Tag, Message, Typography, Tabs
} from '@arco-design/web-react'
import { getAdminUsers, promoteUser, demoteUser } from '../../api/users'
import { getGroups } from '../../api/groups'
import { useAuthStore } from '../../store/auth'
import client from '../../api/client'

const { TabPane } = Tabs

// ========================
// Tab 1: 管理员权限（原有功能）
// ========================
const AdminTab: React.FC = () => {
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
    <div className="ag-data-panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <div />
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

// ========================
// Tab 2: 用户分组管理
// ========================
const UserGroupTab: React.FC = () => {
  const [adUsers, setAdUsers] = useState<any[]>([])
  const [adLoading, setAdLoading] = useState(false)

  // 选中用户的分组
  const [selectedUser, setSelectedUser] = useState<string | null>(null)
  const [userGroups, setUserGroups] = useState<any[]>([])
  const [userGroupLoading, setUserGroupLoading] = useState(false)

  // 所有分组（用于添加下拉）
  const [allGroups, setAllGroups] = useState<any[]>([])
  const [addingGroupId, setAddingGroupId] = useState<string>('')
  const [addLoading, setAddLoading] = useState(false)

  // Modal 可见性
  const [groupModalOpen, setGroupModalOpen] = useState(false)

  const fetchAdUsers = async () => {
    setAdLoading(true)
    try {
      const res = await client.get('/admin/users-list')
      const raw = res.data?.data ?? res.data
      setAdUsers(Array.isArray(raw) ? raw : [])
    } catch {
      Message.error('获取用户列表失败')
    } finally {
      setAdLoading(false)
    }
  }

  const fetchAllGroups = async () => {
    try {
      const res = await getGroups()
      const raw = res.data?.data ?? res.data
      setAllGroups(Array.isArray(raw) ? raw : [])
    } catch {
      // 静默处理
    }
  }

  useEffect(() => {
    fetchAdUsers()
    fetchAllGroups()
  }, [])

  const openUserGroupModal = async (username: string) => {
    setSelectedUser(username)
    setAddingGroupId('')
    setGroupModalOpen(true)
    setUserGroupLoading(true)
    try {
      const res = await client.get(`/admin/users-list/${username}/groups`)
      const raw = res.data?.data ?? res.data
      setUserGroups(Array.isArray(raw) ? raw : [])
    } catch {
      Message.error('获取用户分组失败')
    } finally {
      setUserGroupLoading(false)
    }
  }

  const handleAddUserToGroup = async () => {
    if (!addingGroupId) {
      Message.warning('请选择要加入的分组')
      return
    }
    setAddLoading(true)
    try {
      await client.post(`/admin/users-list/${selectedUser}/groups/${addingGroupId}`)
      Message.success('已加入分组')
      setAddingGroupId('')
      // 刷新用户分组
      const res = await client.get(`/admin/users-list/${selectedUser}/groups`)
      const raw = res.data?.data ?? res.data
      setUserGroups(Array.isArray(raw) ? raw : [])
    } catch (err: any) {
      Message.error(err?.response?.data?.detail || '操作失败')
    } finally {
      setAddLoading(false)
    }
  }

  const handleRemoveUserFromGroup = async (groupId: string) => {
    try {
      await client.delete(`/admin/users-list/${selectedUser}/groups/${groupId}`)
      Message.success('已退出分组')
      setUserGroups((prev) => prev.filter((g) => g.id !== groupId))
    } catch (err: any) {
      Message.error(err?.response?.data?.detail || '操作失败')
    }
  }

  // 已在用户分组中的 id 集合
  const userGroupIds = new Set(userGroups.map((g) => g.id))
  const groupOptions = allGroups
    .filter((g) => !g.all_visible && !userGroupIds.has(g.id))
    .map((g) => ({ label: g.name, value: g.id }))

  const adUserColumns = [
    {
      title: '用户名',
      dataIndex: 'username',
      key: 'username',
    },
    {
      title: '首次登录',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (val: string) => val ? new Date(val).toLocaleString('zh-CN') : '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, row: any) => (
        <Button size="mini" type="text" onClick={() => openUserGroupModal(row.username)}>
          管理分组
        </Button>
      )
    },
  ]

  const userGroupColumns = [
    { title: '分组名称', dataIndex: 'name' },
    { title: 'Priority', dataIndex: 'priority' },
    {
      title: '类型',
      dataIndex: 'all_visible',
      render: (v: boolean) => v
        ? <Tag color="green" size="small">全员可见</Tag>
        : <Tag color="arcoblue" size="small">手动分配</Tag>
    },
    {
      title: '操作',
      render: (_: any, row: any) => row.all_visible ? (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>自动加入</Typography.Text>
      ) : (
        <Popconfirm
          title={`确认将用户 "${selectedUser}" 从分组 "${row.name}" 移除？`}
          onOk={() => handleRemoveUserFromGroup(row.id)}
        >
          <Button size="mini" type="text" status="danger">退出</Button>
        </Popconfirm>
      )
    },
  ]

  return (
    <div className="ag-data-panel">
      <div style={{ marginBottom: 16 }}>
        <Typography.Text type="secondary">
          显示所有 AD 用户，点击"管理分组"可查看并配置用户所属分组。
        </Typography.Text>
      </div>

      <Table
        columns={adUserColumns}
        data={adUsers}
        loading={adLoading}
        rowKey="username"
        pagination={{ pageSize: 20, showTotal: true }}
      />

      {/* 用户分组管理 Modal */}
      <Modal
        title={`用户分组 — ${selectedUser ?? ''}`}
        visible={groupModalOpen}
        onCancel={() => setGroupModalOpen(false)}
        footer={
          <Button onClick={() => setGroupModalOpen(false)}>关闭</Button>
        }
        style={{ width: 560 }}
        unmountOnExit
      >
        {/* 添加分组区域 */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <Select
            style={{ flex: 1 }}
            placeholder="选择要加入的分组"
            options={groupOptions}
            value={addingGroupId || undefined}
            onChange={(v) => setAddingGroupId(v)}
            showSearch
            allowClear
          />
          <Button
            type="primary"
            loading={addLoading}
            onClick={handleAddUserToGroup}
          >
            加入
          </Button>
        </div>

        {/* 已在的分组列表 */}
        <Table
          rowKey="id"
          columns={userGroupColumns}
          data={userGroups}
          loading={userGroupLoading}
          pagination={false}
          noDataElement={
            <div style={{ textAlign: 'center', color: '#999', padding: 16 }}>
              该用户尚未加入任何分组
            </div>
          }
        />
      </Modal>
    </div>
  )
}

// ========================
// 主组件：Users
// ========================
const Users: React.FC = () => {
  return (
    <div className="ag-page">
      <div className="ag-page-header">
        <div>
          <p className="ag-page-eyebrow">Identity</p>
          <h1 className="ag-page-title">Users</h1>
          <p className="ag-page-description">管理管理员角色与用户分组关系。</p>
        </div>
      </div>

      <Tabs defaultActiveTab="admin">
        <TabPane key="admin" title="管理员权限">
          <AdminTab />
        </TabPane>
        <TabPane key="usergroup" title="用户分组">
          <UserGroupTab />
        </TabPane>
      </Tabs>
    </div>
  )
}

export default Users
