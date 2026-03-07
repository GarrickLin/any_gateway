import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber,
  Popconfirm, Message, Space, Typography, Select, Tag
} from '@arco-design/web-react'
import { getGroups, createGroup, updateGroup, deleteGroup } from '../../api/groups'
import { getChannels } from '../../api/channels'
import client from '../../api/client'

const Groups: React.FC = () => {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()

  // 管理渠道相关状态
  const [channelModalOpen, setChannelModalOpen] = useState(false)
  const [managingGroup, setManagingGroup] = useState<any>(null)
  const [groupChannels, setGroupChannels] = useState<any[]>([])
  const [allChannels, setAllChannels] = useState<any[]>([])
  const [addingChannelId, setAddingChannelId] = useState<string>('')
  const [channelLoading, setChannelLoading] = useState(false)
  const [addLoading, setAddLoading] = useState(false)

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

  // 打开"管理渠道" Modal，加载该分组已有渠道和所有渠道
  const openChannelModal = async (group: any) => {
    setManagingGroup(group)
    setAddingChannelId('')
    setChannelModalOpen(true)
    setChannelLoading(true)
    try {
      const [groupRes, allRes] = await Promise.all([
        client.get(`/admin/groups/${group.id}/channels`),
        getChannels(),
      ])
      const gc = groupRes.data?.data ?? groupRes.data
      setGroupChannels(Array.isArray(gc) ? gc : [])
      const ac = allRes.data?.data ?? allRes.data
      setAllChannels(Array.isArray(ac) ? ac : [])
    } catch {
      Message.error('加载渠道失败')
    } finally {
      setChannelLoading(false)
    }
  }

  // 添加渠道到分组
  const handleAddChannelToGroup = async () => {
    if (!addingChannelId) {
      Message.warning('请选择要添加的渠道')
      return
    }
    setAddLoading(true)
    try {
      await client.post(`/admin/groups/${managingGroup.id}/channels/${addingChannelId}`)
      Message.success('渠道已添加')
      setAddingChannelId('')
      // 刷新分组渠道列表
      const res = await client.get(`/admin/groups/${managingGroup.id}/channels`)
      const gc = res.data?.data ?? res.data
      setGroupChannels(Array.isArray(gc) ? gc : [])
    } catch (err: any) {
      Message.error(err?.response?.data?.detail || '添加失败')
    } finally {
      setAddLoading(false)
    }
  }

  // 从分组移除渠道
  const handleRemoveChannelFromGroup = async (channelId: string) => {
    try {
      await client.delete(`/admin/groups/${managingGroup.id}/channels/${channelId}`)
      Message.success('渠道已移除')
      setGroupChannels((prev) => prev.filter((c) => c.id !== channelId))
    } catch (err: any) {
      Message.error(err?.response?.data?.detail || '移除失败')
    }
  }

  // 已在分组中的渠道 id 集合，用于过滤下拉选项
  const groupChannelIds = new Set(groupChannels.map((c) => c.id))

  const channelOptions = allChannels
    .filter((c) => !groupChannelIds.has(c.id))
    .map((c) => ({ label: `${c.name} (${c.provider})`, value: c.id }))

  const groupChannelColumns = [
    { title: '名称', dataIndex: 'name' },
    {
      title: 'Provider',
      dataIndex: 'provider',
      render: (p: string) => <Tag color="arcoblue">{p}</Tag>
    },
    {
      title: '操作',
      render: (_: any, row: any) => (
        <Popconfirm
          title={`确认从分组移除渠道 "${row.name}"？`}
          onOk={() => handleRemoveChannelFromGroup(row.id)}
        >
          <Button size="mini" type="text" status="danger">移除</Button>
        </Popconfirm>
      )
    },
  ]

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
          <Button size="mini" type="text" onClick={() => openChannelModal(row)}>管理渠道</Button>
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

      {/* 新建/编辑 Group Modal */}
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

      {/* 管理渠道 Modal */}
      <Modal
        title={`管理渠道 — ${managingGroup?.name ?? ''}`}
        visible={channelModalOpen}
        onCancel={() => setChannelModalOpen(false)}
        footer={
          <Button onClick={() => setChannelModalOpen(false)}>关闭</Button>
        }
        style={{ width: 600 }}
        unmountOnExit
      >
        {/* 添加渠道区域 */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
          <Select
            style={{ flex: 1 }}
            placeholder="选择要添加的渠道"
            options={channelOptions}
            value={addingChannelId || undefined}
            onChange={(v) => setAddingChannelId(v)}
            showSearch
            allowClear
          />
          <Button
            type="primary"
            loading={addLoading}
            onClick={handleAddChannelToGroup}
          >
            添加
          </Button>
        </div>

        {/* 已有渠道列表 */}
        <Table
          rowKey="id"
          columns={groupChannelColumns}
          data={groupChannels}
          loading={channelLoading}
          pagination={false}
          noDataElement={<div style={{ textAlign: 'center', color: '#999', padding: 16 }}>暂无渠道，请添加</div>}
        />
      </Modal>
    </div>
  )
}

export default Groups
