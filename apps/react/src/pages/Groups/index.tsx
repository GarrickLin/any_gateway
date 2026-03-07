import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber,
  Popconfirm, Message, Space, Typography
} from '@arco-design/web-react'
import { getGroups, createGroup, updateGroup, deleteGroup } from '../../api/groups'

const Groups: React.FC = () => {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getGroups()
      const raw = res.data?.data ?? res.data
      setData(Array.isArray(raw) ? raw : [])
    } catch {
      Message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const handleOpen = (record?: any) => {
    setEditing(record || null)
    if (record) {
      form.setFieldsValue(record)
    } else {
      form.resetFields()
    }
    setVisible(true)
  }

  const handleSubmit = async (values: any) => {
    try {
      if (editing) {
        const { name, ...updateData } = values
        await updateGroup(editing.id, updateData)
        Message.success('已更新')
      } else {
        await createGroup(values)
        Message.success('已创建')
      }
      setVisible(false)
      fetchData()
    } catch {
      Message.error('操作失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteGroup(id)
      Message.success('已删除')
      fetchData()
    } catch {
      Message.error('删除失败')
    }
  }

  const columns = [
    { title: '名称', dataIndex: 'name' },
    { title: 'RPM 限制', dataIndex: 'rpm_limit' },
    { title: 'TPM 限制', dataIndex: 'tpm_limit' },
    { title: 'Priority', dataIndex: 'priority' },
    { title: '费率倍数', dataIndex: 'multiplier' },
    { title: '创建时间', dataIndex: 'created_at', render: (v: string) => v?.slice(0, 19) },
    {
      title: '操作',
      render: (_: any, row: any) => (
        <Space>
          <Button size="mini" type="text" onClick={() => handleOpen(row)}>编辑</Button>
          <Popconfirm title="确认删除此 Group？" onOk={() => handleDelete(row.id)}>
            <Button size="mini" type="text" status="danger">删除</Button>
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title heading={5} style={{ margin: 0 }}>Group 管理</Typography.Title>
        <Button type="primary" onClick={() => handleOpen()}>新建 Group</Button>
      </div>

      <Table columns={columns} data={data} loading={loading} rowKey="id" />

      <Modal
        title={editing ? '编辑 Group' : '新建 Group'}
        visible={visible}
        onCancel={() => setVisible(false)}
        onOk={() => form.submit()}
      >
        <Form form={form} onSubmit={handleSubmit} layout="vertical">
          <Form.Item field="name" label="名称" rules={[{ required: true }]}>
            <Input placeholder="如：core-dev" disabled={!!editing} />
          </Form.Item>
          <Form.Item field="rpm_limit" label="RPM 限制" initialValue={60}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item field="tpm_limit" label="TPM 限制" initialValue={100000}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item field="priority" label="Priority" initialValue={1}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item field="multiplier" label="费率倍数" initialValue={1.0}>
            <InputNumber min={0.01} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Groups
