import React, { useState, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber,
  Popconfirm, Message, Space, Typography, Select, Tag, Radio, Switch
} from '@arco-design/web-react'
import { getGroups, createGroup, updateGroup, deleteGroup } from '../../api/groups'
import { getChannels } from '../../api/channels'
import { getRateLimits, createRateLimit, deleteRateLimit } from '../../api/rateLimits'
import client from '../../api/client'
import { getGroupPrices, createGroupPrice, deleteGroupPrice } from '../../api/groupPrices'

const Groups: React.FC = () => {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()

  // 管理规则相关状态
  const [ruleModalOpen, setRuleModalOpen] = useState(false)
  const [managingRuleGroup, setManagingRuleGroup] = useState<any>(null)
  const [rules, setRules] = useState<any[]>([])
  const [ruleLoading, setRuleLoading] = useState(false)
  const [newLimitType, setNewLimitType] = useState<string>('request_limit')
  const [newWindowNum, setNewWindowNum] = useState<number>(1)
  const [newWindowUnit, setNewWindowUnit] = useState<number>(60)
  const [newValue, setNewValue] = useState<number>(10)
  const [addRuleLoading, setAddRuleLoading] = useState(false)

  // 管理渠道相关状态
  const [channelModalOpen, setChannelModalOpen] = useState(false)
  const [managingGroup, setManagingGroup] = useState<any>(null)
  const [groupChannels, setGroupChannels] = useState<any[]>([])
  const [allChannels, setAllChannels] = useState<any[]>([])
  const [addingChannelId, setAddingChannelId] = useState<string>('')
  const [channelLoading, setChannelLoading] = useState(false)
  const [addLoading, setAddLoading] = useState(false)

  // 管理价格相关状态
  const [priceModalOpen, setPriceModalOpen] = useState(false)
  const [managingPriceGroup, setManagingPriceGroup] = useState<any>(null)
  const [groupPrices, setGroupPrices] = useState<any[]>([])
  const [priceLoading, setPriceLoading] = useState(false)
  const [newPriceMode, setNewPriceMode] = useState<'token' | 'request'>('token')
  const [newPriceModelName, setNewPriceModelName] = useState('')
  const [newPriceUnit, setNewPriceUnit] = useState('input_token')
  const [newPriceValue, setNewPriceValue] = useState<number>(0)
  const [addPriceLoading, setAddPriceLoading] = useState(false)

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

  // 加载限流规则
  const fetchRules = async (groupId: string) => {
    setRuleLoading(true)
    try {
      const res = await getRateLimits(groupId)
      const raw = res.data?.data ?? res.data
      setRules(Array.isArray(raw) ? raw : [])
    } catch { Message.error('加载规则失败') }
    finally { setRuleLoading(false) }
  }

  // 打开"管理规则" Modal
  const handleOpenRules = (record: any) => {
    setManagingRuleGroup(record)
    setRuleModalOpen(true)
    fetchRules(record.id)
  }

  // 添加规则
  const handleAddRule = async () => {
    setAddRuleLoading(true)
    try {
      await createRateLimit({
        group_id: managingRuleGroup.id,
        window_sec: newWindowNum * newWindowUnit,
        limit_type: newLimitType as any,
        value: newValue,
      })
      Message.success('规则已添加')
      fetchRules(managingRuleGroup.id)
      setNewLimitType('request_limit')
      setNewWindowNum(1)
      setNewWindowUnit(60)
      setNewValue(10)
    } catch { Message.error('添加失败') }
    finally { setAddRuleLoading(false) }
  }

  // 删除规则
  const handleDeleteRule = async (ruleId: string) => {
    try {
      await deleteRateLimit(ruleId)
      Message.success('已删除')
      fetchRules(managingRuleGroup.id)
    } catch { Message.error('删除失败') }
  }

  // 窗口时长反显示
  const formatWindowSec = (sec: number): string => {
    if (sec % 86400 === 0) return `${sec / 86400} 天`
    if (sec % 3600 === 0) return `${sec / 3600} 小时`
    return `${Math.round(sec / 60)} 分钟`
  }

  const limitTypeLabel: Record<string, string> = {
    request_limit: '请求数',
    token_limit: 'Token',
    quota_limit: '金额 (USD)',
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

  // 加载 Group 价格
  const fetchGroupPrices = async (groupId: string) => {
    setPriceLoading(true)
    try {
      const res = await getGroupPrices(groupId)
      const raw = res.data?.data ?? res.data
      setGroupPrices(Array.isArray(raw) ? raw : [])
    } catch { Message.error('加载价格失败') }
    finally { setPriceLoading(false) }
  }

  // 打开"管理价格" Modal
  const handleOpenPrices = (record: any) => {
    setManagingPriceGroup(record)
    setPriceModalOpen(true)
    setNewPriceMode('token')
    setNewPriceModelName('')
    setNewPriceUnit('input_token')
    setNewPriceValue(0)
    fetchGroupPrices(record.id)
  }

  // 添加价格
  const handleAddGroupPrice = async () => {
    if (!newPriceModelName.trim()) {
      Message.warning('请输入模型名称')
      return
    }
    if (newPriceValue <= 0) {
      Message.warning('单价必须大于 0')
      return
    }
    setAddPriceLoading(true)
    try {
      const unit = newPriceMode === 'request' ? 'request' : newPriceUnit
      await createGroupPrice({
        group_id: managingPriceGroup.id,
        model_name: newPriceModelName.trim(),
        unit,
        price_per_unit: newPriceValue,
      })
      Message.success('价格已添加')
      fetchGroupPrices(managingPriceGroup.id)
      setNewPriceModelName('')
      setNewPriceValue(0)
    } catch { Message.error('添加失败') }
    finally { setAddPriceLoading(false) }
  }

  // 删除价格
  const handleDeleteGroupPrice = async (priceId: string) => {
    try {
      await deleteGroupPrice(priceId)
      Message.success('已删除')
      fetchGroupPrices(managingPriceGroup.id)
    } catch { Message.error('删除失败') }
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
    {
      title: '名称',
      dataIndex: 'name',
      render: (v: string) => <span style={{ fontWeight: 700 }}>{v}</span>,
    },
    {
      title: 'Priority',
      dataIndex: 'priority',
      render: (v: number) => <strong style={{ fontFamily: 'monospace' }}>{v}</strong>,
    },
    {
      title: '费率倍数',
      dataIndex: 'multiplier',
      render: (v: number) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}×</span>,
    },
    {
      title: '全员可见',
      dataIndex: 'all_visible',
      render: (v: boolean) => v ? <Tag color="green">是</Tag> : <Tag color="gray">否</Tag>
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      render: (v: string) => <span style={{ color: 'var(--ag-outline)', fontSize: 11, fontFamily: 'monospace' }}>{v?.slice(0, 10)}</span>,
    },
    {
      title: '操作',
      render: (_: any, row: any) => (
        <Space>
          <Button size="mini" type="text" onClick={() => handleOpen(row)}>编辑</Button>
          <Button size="mini" type="text" onClick={() => openChannelModal(row)}>管理渠道</Button>
          <Button size="mini" type="text" onClick={() => handleOpenRules(row)}>管理规则</Button>
          <Button size="mini" type="text" onClick={() => handleOpenPrices(row)}>管理价格</Button>
          <Popconfirm title="确认删除此 Group？" onOk={() => handleDelete(row.id)}>
            <Button size="mini" type="text" status="danger">删除</Button>
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <div className="ag-page ag-workbench-page">
      <div className="ag-page-header">
        <div>
          <p className="ag-page-eyebrow">Access Policy</p>
          <h1 className="ag-page-title">Groups</h1>
          <p className="ag-page-description">管理分组、限流规则、渠道授权与分组价格。</p>
        </div>
        <div className="ag-header-actions">
          <Button type="primary" onClick={() => handleOpen()}>新建 Group</Button>
        </div>
      </div>

      <div className="ag-data-panel ag-workbench-panel ag-table-panel">
        <div className="ag-panel-header">
          <div>
            <h2 className="ag-panel-title">分组策略</h2>
            <p className="ag-panel-subtitle">集中维护用户访问策略、渠道授权、限流和价格覆盖</p>
          </div>
        </div>

        <Table columns={columns} data={data} loading={loading} rowKey="id" />
      </div>

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
          <Form.Item field="priority" label="Priority" initialValue={1}>
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item field="multiplier" label="费率倍数" initialValue={1.0}>
            <InputNumber min={0.01} step={0.1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item field="all_visible" label="全员可见" initialValue={false}>
            <Switch checkedText="是" uncheckedText="否" />
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
      {/* 管理限流规则 Modal */}
      <Modal
        title={`管理限流规则 — ${managingRuleGroup?.name}`}
        visible={ruleModalOpen}
        onCancel={() => setRuleModalOpen(false)}
        footer={null}
        style={{ width: 600 }}
      >
        <Table
          loading={ruleLoading}
          data={rules}
          rowKey="id"
          pagination={false}
          columns={[
            { title: '类型', dataIndex: 'limit_type', render: (v: string) => limitTypeLabel[v] ?? v },
            { title: '窗口', dataIndex: 'window_sec', render: (v: number) => formatWindowSec(v) },
            { title: '限制值', dataIndex: 'value' },
            {
              title: '操作', render: (_: any, record: any) => (
                <Popconfirm title="确认删除？" onOk={() => handleDeleteRule(record.id)}>
                  <Button type="text" status="danger" size="small">删除</Button>
                </Popconfirm>
              )
            },
          ]}
        />

        <div style={{ marginTop: 16 }}>
          <Typography.Text bold>添加规则</Typography.Text>
          <Space style={{ marginTop: 8, flexWrap: 'wrap' }}>
            <Select value={newLimitType} onChange={setNewLimitType} style={{ width: 120 }}>
              <Select.Option value="request_limit">请求数</Select.Option>
              <Select.Option value="token_limit">Token</Select.Option>
              <Select.Option value="quota_limit">金额 (USD)</Select.Option>
            </Select>
            <InputNumber min={1} value={newWindowNum} onChange={(v) => setNewWindowNum(v ?? 1)} style={{ width: 80 }} />
            <Select value={newWindowUnit} onChange={setNewWindowUnit} style={{ width: 80 }}>
              <Select.Option value={60}>分钟</Select.Option>
              <Select.Option value={3600}>小时</Select.Option>
              <Select.Option value={86400}>天</Select.Option>
            </Select>
            <InputNumber min={0} value={newValue} onChange={(v) => setNewValue(v ?? 0)} style={{ width: 100 }} placeholder="限制值" />
            <Button type="primary" loading={addRuleLoading} onClick={handleAddRule}>添加</Button>
          </Space>
        </div>
      </Modal>

      {/* 管理价格 Modal */}
      <Modal
        title={`管理价格 — ${managingPriceGroup?.name ?? ''}`}
        visible={priceModalOpen}
        onCancel={() => setPriceModalOpen(false)}
        footer={<Button onClick={() => setPriceModalOpen(false)}>关闭</Button>}
        style={{ width: 620 }}
        unmountOnExit
      >
        <Table
          loading={priceLoading}
          data={groupPrices}
          rowKey="id"
          pagination={false}
          columns={[
            { title: '模型名称', dataIndex: 'model_name' },
            {
              title: '计价单位',
              dataIndex: 'unit',
              render: (v: string) => ({
                input_token: 'Input / 1M',
                output_token: 'Output / 1M',
                cache_read_token: 'Cache Read / 1M',
                cache_write_token: 'Cache Write / 1M',
                extra_context_token: 'Extra / 1M',
                request: '每次请求',
              }[v] ?? v),
            },
            {
              title: '单价 (USD)',
              dataIndex: 'price_per_unit',
              render: (v: number) => v.toFixed(6),
            },
            {
              title: '操作',
              render: (_: any, record: any) => (
                <Popconfirm title="确认删除？" onOk={() => handleDeleteGroupPrice(record.id)}>
                  <Button type="text" status="danger" size="small">删除</Button>
                </Popconfirm>
              ),
            },
          ]}
        />

        <div style={{ marginTop: 16 }}>
          <Typography.Text bold>添加覆盖价格</Typography.Text>
          <div style={{ marginTop: 8 }}>
            <Radio.Group
              value={newPriceMode}
              onChange={(v: 'token' | 'request') => { setNewPriceMode(v); setNewPriceUnit('input_token') }}
              style={{ marginBottom: 8 }}
            >
              <Radio value="token">按 Token</Radio>
              <Radio value="request">按请求次数</Radio>
            </Radio.Group>
            <Space wrap>
              <Input
                placeholder="模型名称"
                value={newPriceModelName}
                onChange={setNewPriceModelName}
                style={{ width: 150 }}
              />
              {newPriceMode === 'token' && (
                <Select
                  value={newPriceUnit}
                  onChange={setNewPriceUnit}
                  style={{ width: 180 }}
                  options={[
                    { label: 'Input / 1M', value: 'input_token' },
                    { label: 'Output / 1M', value: 'output_token' },
                    { label: 'Cache Read / 1M', value: 'cache_read_token' },
                    { label: 'Cache Write / 1M', value: 'cache_write_token' },
                    { label: 'Extra Context / 1M', value: 'extra_context_token' },
                  ]}
                />
              )}
              <InputNumber
                min={0}
                step={0.001}
                precision={6}
                value={newPriceValue}
                onChange={(v) => setNewPriceValue(v ?? 0)}
                placeholder="单价 USD"
                style={{ width: 120 }}
              />
              <Button type="primary" loading={addPriceLoading} onClick={handleAddGroupPrice}>添加</Button>
            </Space>
          </div>
        </div>
      </Modal>
    </div>
  )
}

export default Groups
