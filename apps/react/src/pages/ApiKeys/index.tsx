import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber,
  Popconfirm, Tag, Message, Space, Typography
} from '@arco-design/web-react'
import { getTokens, createToken, deleteToken, freezeToken } from '../../api/tokens'

const ApiKeys: React.FC = () => {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [createVisible, setCreateVisible] = useState(false)
  const [newKeyVisible, setNewKeyVisible] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [form] = Form.useForm()

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

  useEffect(() => { fetchData() }, [])

  const handleCreate = async (values: any) => {
    try {
      const res = await createToken(values)
      setNewKey(res.data.key || '')
      setCreateVisible(false)
      setNewKeyVisible(true)
      form.resetFields()
    } catch {
      Message.error('创建失败')
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
    { title: 'Group', dataIndex: 'group_id' },
    {
      title: '额度',
      render: (_: any, row: any) =>
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
      render: (_: any, row: any) => (
        <Space>
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
        onCancel={() => { setCreateVisible(false); form.resetFields() }}
        onOk={() => form.submit()}
      >
        <Form form={form} onSubmit={handleCreate} layout="vertical">
          <Form.Item field="name" label="名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如：团队A开发用" />
          </Form.Item>
          <Form.Item field="quota_usd" label="额度限制（USD，0=无限制）">
            <InputNumber min={0} placeholder="0" style={{ width: '100%' }} />
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
        {/* <p style={{ color: '#ff7d00', marginBottom: 8 }}>请立即复制，此 Key 仅显示一次！</p> */}
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
