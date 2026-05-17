import React, { useState, useEffect, useCallback } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber,
  Radio, Popconfirm, Message, Space, Tag, Select,
} from '@arco-design/web-react'
import { IconPlus } from '@arco-design/web-react/icon'
import { getPrices, createPrice, updatePrice, deletePrice } from '../../api/prices'

interface PriceRow {
  id: string
  model_name: string
  unit: string
  price_per_unit: number
  context_length?: number
  vendor?: string
  stability?: string
}

interface ModelGroup {
  model_name: string
  vendor?: string
  context_length?: number
  stability?: string
  input_token?: number
  output_token?: number
  cache_read_token?: number
  cache_write_token?: number
  extra_context_token?: number
  request?: number
  rows: PriceRow[]
}

function groupByModel(data: PriceRow[]): ModelGroup[] {
  const map = new Map<string, ModelGroup>()
  for (const row of data) {
    let g = map.get(row.model_name)
    if (!g) {
      g = { model_name: row.model_name, rows: [] }
      map.set(row.model_name, g)
    }
    g.rows.push(row)
    if (row.vendor) g.vendor = row.vendor
    if (row.context_length) g.context_length = row.context_length
    if (row.stability) g.stability = row.stability
    const unit = row.unit as keyof ModelGroup
    if (['input_token', 'output_token', 'cache_read_token', 'cache_write_token', 'extra_context_token', 'request'].includes(row.unit)) {
      ;(g as any)[unit] = row.price_per_unit
    }
  }
  return Array.from(map.values()).sort((a, b) => a.model_name.localeCompare(b.model_name))
}

function formatCtx(n?: number) {
  if (!n) return '-'
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${Math.round(n / 1000)}K`
  return String(n)
}

function formatPrice(v?: number) {
  if (v == null) return '-'
  return `$${v.toFixed(2)}`
}

const VENDOR_OPTIONS = ['DeepSeek', 'Anthropic', 'OpenAI', 'Google', 'Alibaba', 'Volcengine', 'Zhipu AI', 'Other']

const Prices: React.FC = () => {
  const [data, setData] = useState<PriceRow[]>([])
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const [editing, setEditing] = useState<ModelGroup | null>(null)
  const [priceMode, setPriceMode] = useState<'token' | 'request'>('token')
  const [form] = Form.useForm()
  const [searchText, setSearchText] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getPrices()
      const raw = res.data?.data ?? res.data
      setData(Array.isArray(raw) ? raw : [])
    } catch {
      Message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const groups = groupByModel(data)
  const filtered = searchText
    ? groups.filter(g => g.model_name.toLowerCase().includes(searchText.toLowerCase()))
    : groups

  const handleOpen = (group?: ModelGroup) => {
    setEditing(group || null)
    if (group) {
      const hasRequest = group.rows.some(r => r.unit === 'request')
      setPriceMode(hasRequest ? 'request' : 'token')
      form.setFieldsValue({
        model_name: group.model_name,
        vendor: group.vendor || undefined,
        context_length: group.context_length || undefined,
        stability: group.stability || undefined,
        input_price: group.input_token,
        output_price: group.output_token,
        cache_read_price: group.cache_read_token,
        cache_write_price: group.cache_write_token,
        extra_context_price: group.extra_context_token,
        request_price: group.request,
      })
    } else {
      setPriceMode('token')
      form.resetFields()
    }
    setVisible(true)
  }

  const handleSubmit = async (values: any) => {
    try {
      const meta = {
        context_length: values.context_length || undefined,
        vendor: values.vendor || undefined,
        stability: values.stability || undefined,
      }

      if (editing) {
        const unitPriceMap: Record<string, number | undefined> = {
          input_token: values.input_price,
          output_token: values.output_price,
          cache_read_token: values.cache_read_price,
          cache_write_token: values.cache_write_price,
          extra_context_token: values.extra_context_price,
          request: values.request_price,
        }

        for (const row of editing.rows) {
          const newPrice = unitPriceMap[row.unit]
          await updatePrice(row.id, {
            price_per_unit: newPrice ?? row.price_per_unit,
            ...meta,
          })
        }

        if (priceMode === 'token') {
          const existingUnits = new Set(editing.rows.map(r => r.unit))
          const newUnits = [
            { unit: 'input_token', price: values.input_price },
            { unit: 'output_token', price: values.output_price },
            { unit: 'cache_read_token', price: values.cache_read_price },
            { unit: 'cache_write_token', price: values.cache_write_price },
            { unit: 'extra_context_token', price: values.extra_context_price },
          ].filter(c => c.price != null && c.price > 0 && !existingUnits.has(c.unit))

          await Promise.all(
            newUnits.map(c => createPrice({
              model_name: editing.model_name,
              unit: c.unit,
              price_per_unit: c.price,
              ...meta,
            }))
          )
        }

        Message.success('已更新')
      } else {
        if (priceMode === 'request') {
          await createPrice({
            model_name: values.model_name,
            unit: 'request',
            price_per_unit: values.request_price,
            ...meta,
          })
        } else {
          const creates = [
            { unit: 'input_token', price: values.input_price },
            { unit: 'output_token', price: values.output_price },
            { unit: 'cache_read_token', price: values.cache_read_price },
            { unit: 'cache_write_token', price: values.cache_write_price },
            { unit: 'extra_context_token', price: values.extra_context_price },
          ].filter(c => c.price != null && c.price > 0)

          await Promise.all(
            creates.map(c => createPrice({
              model_name: values.model_name,
              unit: c.unit,
              price_per_unit: c.price,
              ...meta,
            }))
          )
        }
        Message.success('已创建')
      }
      setVisible(false)
      fetchData()
    } catch {
      Message.error('操作失败')
    }
  }

  const handleDeleteModel = async (group: ModelGroup) => {
    try {
      await Promise.all(group.rows.map(r => deletePrice(r.id)))
      Message.success('已删除')
      fetchData()
    } catch {
      Message.error('删除失败')
    }
  }

  const columns = [
    {
      title: '模型名称',
      dataIndex: 'model_name',
      width: 200,
      render: (v: string) => <span style={{ fontWeight: 700 }}>{v}</span>,
    },
    {
      title: '来源',
      dataIndex: 'vendor',
      width: 110,
      render: (v?: string) => v ? <Tag color="arcoblue">{v}</Tag> : <span style={{ color: '#c0c0c0' }}>-</span>,
    },
    {
      title: '上下文',
      dataIndex: 'context_length',
      width: 90,
      render: (v?: number) => <span style={{ fontFamily: 'monospace' }}>{formatCtx(v)}</span>,
    },
    {
      title: '输入 (/1M)',
      dataIndex: 'input_token',
      width: 110,
      render: (v?: number) => <strong style={{ fontFamily: 'monospace', fontSize: 12 }}>{formatPrice(v)}</strong>,
    },
    {
      title: '输出 (/1M)',
      dataIndex: 'output_token',
      width: 110,
      render: (v?: number) => <strong style={{ fontFamily: 'monospace', fontSize: 12 }}>{formatPrice(v)}</strong>,
    },
    {
      title: '缓存读 (/1M)',
      dataIndex: 'cache_read_token',
      width: 110,
      render: (v?: number) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{formatPrice(v)}</span>,
    },
    {
      title: '缓存写 (/1M)',
      dataIndex: 'cache_write_token',
      width: 110,
      render: (v?: number) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{formatPrice(v)}</span>,
    },
    {
      title: '稳定性',
      dataIndex: 'stability',
      width: 90,
      render: (v?: string) => {
        if (!v) return <span style={{ color: '#c0c0c0' }}>-</span>
        const colorMap: Record<string, string> = {
          '稳定': 'green', 'stable': 'green',
          'beta': 'orange', 'Beta': 'orange', '测试': 'orange',
          '下线': 'red', 'deprecated': 'red',
        }
        return <Tag color={colorMap[v] || 'gray'}>{v}</Tag>
      },
    },
    {
      title: '操作',
      width: 120,
      render: (_: any, row: ModelGroup) => (
        <Space>
          <Button size="mini" type="text" onClick={() => handleOpen(row)}>编辑</Button>
          <Popconfirm title={`删除 ${row.model_name} 的所有价格？`} onOk={() => handleDeleteModel(row)}>
            <Button size="mini" type="text" status="danger">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="ag-page ag-workbench-page">
      <div className="ag-page-header">
        <div>
          <p className="ag-page-eyebrow">Billing</p>
          <h1 className="ag-page-title">Prices</h1>
          <p className="ag-page-description">配置模型与请求计价，影响成本统计与扣费计算。</p>
        </div>
        <Space className="ag-header-actions">
          <Input
            placeholder="搜索模型名"
            value={searchText}
            onChange={setSearchText}
            allowClear
            style={{ width: 200 }}
          />
          <Button type="primary" icon={<IconPlus />} onClick={() => handleOpen()}>新增模型</Button>
        </Space>
      </div>

      <div className="ag-data-panel ag-workbench-panel ag-table-panel">
        <div className="ag-panel-header">
          <div>
            <h2 className="ag-panel-title">价格配置</h2>
            <p className="ag-panel-subtitle">每行代表一个模型，展示各维度价格</p>
          </div>
        </div>

        <Table
          columns={columns}
          data={filtered}
          loading={loading}
          rowKey="model_name"
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 20, showTotal: true }}
        />
      </div>

      <Modal
        title={editing ? `编辑 ${editing.model_name}` : '新增模型价格'}
        visible={visible}
        onCancel={() => setVisible(false)}
        onOk={() => form.submit()}
        unmountOnExit
        style={{ width: 520 }}
      >
        <Form form={form} onSubmit={handleSubmit} layout="vertical">
          {!editing && (
            <Form.Item label="计价模式">
              <Radio.Group
                value={priceMode}
                onChange={(v) => { setPriceMode(v); form.resetFields(['unit']) }}
              >
                <Radio value="token">按 Token</Radio>
                <Radio value="request">按请求次数</Radio>
              </Radio.Group>
            </Form.Item>
          )}

          {!editing && (
            <Form.Item
              field="model_name"
              label="模型名称"
              rules={[{ required: true }]}
            >
              <Input placeholder="如 gpt-4o 或 deepseek-v3" />
            </Form.Item>
          )}

          <Form.Item field="vendor" label="模型来源">
            <Select placeholder="选择或输入" allowCreate allowClear>
              {VENDOR_OPTIONS.map(v => (
                <Select.Option key={v} value={v}>{v}</Select.Option>
              ))}
            </Select>
          </Form.Item>

          <div style={{ display: 'flex', gap: 12 }}>
            <Form.Item field="context_length" label="上下文长度" style={{ flex: 1 }}>
              <InputNumber min={0} step={1000} placeholder="如 128000" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item field="stability" label="稳定性" style={{ flex: 1 }}>
              <Input placeholder="如 稳定、Beta、测试" />
            </Form.Item>
          </div>

          {priceMode === 'token' && (
            <>
              <div style={{ display: 'flex', gap: 12 }}>
                <Form.Item field="input_price" label="输入 (/1M USD)" rules={editing ? [] : [{ required: true }]} style={{ flex: 1 }}>
                  <InputNumber min={0} step={0.01} precision={6} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item field="output_price" label="输出 (/1M USD)" rules={editing ? [] : [{ required: true }]} style={{ flex: 1 }}>
                  <InputNumber min={0} step={0.01} precision={6} style={{ width: '100%' }} />
                </Form.Item>
              </div>
              <div style={{ display: 'flex', gap: 12 }}>
                <Form.Item field="cache_read_price" label="缓存读 (/1M)" style={{ flex: 1 }}>
                  <InputNumber min={0} step={0.01} precision={6} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item field="cache_write_price" label="缓存写 (/1M)" style={{ flex: 1 }}>
                  <InputNumber min={0} step={0.01} precision={6} style={{ width: '100%' }} />
                </Form.Item>
              </div>
              <Form.Item field="extra_context_price" label="Extra Context (/1M，选填)">
                <InputNumber min={0} step={0.01} precision={6} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}

          {priceMode === 'request' && (
            <Form.Item field="request_price" label="每次请求单价 (USD)" rules={[{ required: true }]}>
              <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}

export default Prices
