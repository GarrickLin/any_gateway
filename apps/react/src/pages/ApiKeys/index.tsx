import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Select,
  Popconfirm, Tag, Message, Space, Typography
} from '@arco-design/web-react'
import {
  getTokens, createToken, deleteToken, freezeToken, updateToken,
  getUserGroups, type GroupOption, type Token, type TokenCreate, type TokenUpdate
} from '../../api/tokens'

const ApiKeys: React.FC = () => {
  const [data, setData] = useState<Token[]>([])
  const [groups, setGroups] = useState<GroupOption[]>([])
  const [loading, setLoading] = useState(false)
  const [createVisible, setCreateVisible] = useState(false)
  const [editVisible, setEditVisible] = useState(false)
  const [editingToken, setEditingToken] = useState<Token | null>(null)
  const [newKeyVisible, setNewKeyVisible] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [createForm] = Form.useForm()
  const [editForm] = Form.useForm()

  // 分组 id → name 映射
  const groupMap = React.useMemo(
    () => Object.fromEntries(groups.map(g => [g.id, g.name])),
    [groups]
  )

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getTokens()
      const raw = res.data?.data ?? res.data
      setData(Array.isArray(raw) ? raw : [])
    } catch {
      Message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchGroups = async () => {
    try {
      const res = await getUserGroups()
      setGroups(Array.isArray(res.data) ? res.data : [])
    } catch {
      // 分组加载失败不阻塞主流程
    }
  }

  useEffect(() => {
    fetchData()
    fetchGroups()
  }, [])

  const handleCreate = async (values: TokenCreate) => {
    try {
      const res = await createToken({ ...values, group_id: values.group_id || null })
      setNewKey(res.data.key || '')
      setCreateVisible(false)
      setNewKeyVisible(true)
      createForm.resetFields()
    } catch {
      Message.error('创建失败')
    }
  }

  const handleEdit = (record: Token) => {
    setEditingToken(record)
    editForm.setFieldsValue({ group_id: record.group_id ?? undefined })
    setEditVisible(true)
  }

  const handleEditSubmit = async (values: TokenUpdate) => {
    if (!editingToken) return
    try {
      await updateToken(editingToken.id, { group_id: values.group_id || null })
      Message.success('已更新')
      setEditVisible(false)
      setEditingToken(null)
      fetchData()
    } catch {
      Message.error('更新失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteToken(id)
      Message.success('已删除')
      fetchData()
    } catch {
      Message.error('删除失败')
    }
  }

  const handleFreeze = async (id: string, frozen: boolean) => {
    try {
      await freezeToken(id, frozen)
      Message.success(frozen ? '已冻结' : '已解冻')
      fetchData()
    } catch {
      Message.error('操作失败')
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'name' },
    {
      title: 'Key',
      dataIndex: 'key',
      render: (key: string) => (
        <Typography.Text copyable={{ text: key }}>
          {key?.slice(0, 8)}****
        </Typography.Text>
      )
    },
    {
      title: '绑定分组',
      dataIndex: 'group_id',
      render: (gid: string | null) =>
        gid ? <Tag color="arcoblue">{groupMap[gid] ?? gid}</Tag> : <span style={{ color: '#999' }}>—</span>
    },
    {
      title: '额度',
      render: (_: unknown, row: Token) =>
        `${row.used_usd?.toFixed(4)} / ${row.quota_usd === 0 ? '无限制' : row.quota_usd + ' USD'}`
    },
    {
      title: '状态',
      dataIndex: 'frozen',
      render: (frozen: boolean) => (
        <Tag color={frozen ? 'red' : 'green'}>{frozen ? '冻结' : '正常'}</Tag>
      )
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      render: (v: string) => v?.slice(0, 19)
    },
    {
      title: '操作',
      render: (_: unknown, row: Token) => (
        <Space>
          <Button size="mini" type="text" onClick={() => handleEdit(row)}>绑定分组</Button>
          <Popconfirm
            title={row.frozen ? '确认解冻？' : '确认冻结？'}
            onOk={() => handleFreeze(row.id, !row.frozen)}
          >
            <Button size="mini" type="text">{row.frozen ? '解冻' : '冻结'}</Button>
          </Popconfirm>
          <Popconfirm title="确认删除？" onOk={() => handleDelete(row.id)}>
            <Button size="mini" type="text" status="danger">删除</Button>
          </Popconfirm>
        </Space>
      )
    },
  ]

  const groupOptions = [
    { label: '不绑定（使用用户默认分组）', value: '' },
    ...groups.map(g => ({ label: g.name, value: g.id })),
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title heading={5} style={{ margin: 0 }}>API Keys</Typography.Title>
        <Button type="primary" onClick={() => setCreateVisible(true)}>创建 API Key</Button>
      </div>

      <Table columns={columns} data={data} loading={loading} rowKey="id" />

      {/* 创建 Modal */}
      <Modal
        title="创建 API Key"
        visible={createVisible}
        onCancel={() => { setCreateVisible(false); createForm.resetFields() }}
        onOk={() => createForm.submit()}
      >
        <Form form={createForm} onSubmit={handleCreate} layout="vertical">
          <Form.Item field="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：团队A开发用" />
          </Form.Item>
          <Form.Item field="quota_usd" label="额度限制（USD，0=无限制）">
            <InputNumber min={0} placeholder="0" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item field="group_id" label="绑定分组（可选）">
            <Select
              placeholder="不绑定则使用用户所属分组"
              allowClear
              options={groups.map(g => ({ label: g.name, value: g.id }))}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 编辑分组绑定 Modal */}
      <Modal
        title={`绑定分组 — ${editingToken?.name}`}
        visible={editVisible}
        onCancel={() => { setEditVisible(false); setEditingToken(null); editForm.resetFields() }}
        onOk={() => editForm.submit()}
      >
        <Form form={editForm} onSubmit={handleEditSubmit} layout="vertical">
          <Form.Item field="group_id" label="绑定分组">
            <Select
              placeholder="不绑定则使用用户所属分组"
              allowClear
              options={groupOptions}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新 Key 展示 Modal（一次性） */}
      <Modal
        title="API Key 已创建"
        visible={newKeyVisible}
        footer={
          <Button
            type="primary"
            onClick={() => { setNewKeyVisible(false); fetchData() }}
          >
            我已复制，关闭
          </Button>
        }
        onCancel={() => { setNewKeyVisible(false); fetchData() }}
      >
        <Typography.Text
          copyable={{
            text: newKey,
            onCopy: () => Message.success('已复制到剪贴板')
          }}
          style={{ wordBreak: 'break-all' }}
        >
          {newKey}
        </Typography.Text>
      </Modal>
    </div>
  )
}

export default ApiKeys
