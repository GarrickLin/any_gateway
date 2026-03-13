import React, { useState, useEffect, useCallback } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber,
  Radio, Popconfirm, Message, Space, Typography, Tag,
} from '@arco-design/web-react'
import { IconPlus } from '@arco-design/web-react/icon'
import { getPrices, createPrice, updatePrice, deletePrice } from '../../api/prices'

const UNIT_LABELS: Record<string, string> = {
  input_token: 'Input Token / 1M',
  output_token: 'Output Token / 1M',
  cache_read_token: 'Cache Read Token / 1M',
  cache_write_token: 'Cache Write Token / 1M',
  extra_context_token: 'Extra Context Token / 1M',
  request: '每次请求',
}

const Prices: React.FC = () => {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const [editing, setEditing] = useState<any>(null)
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

  const handleOpen = (record?: any) => {
    setEditing(record || null)
    if (record) {
      setPriceMode(record.unit === 'request' ? 'request' : 'token')
      form.setFieldsValue({ price_per_unit: record.price_per_unit })
    } else {
      setPriceMode('token')
      form.resetFields()
    }
    setVisible(true)
  }

  const handleSubmit = async (values: any) => {
    try {
      if (editing) {
        await updatePrice(editing.id, { price_per_unit: values.price_per_unit })
        Message.success('已更新')
        setVisible(false)
        fetchData()
      } else {
        if (priceMode === 'request') {
          await createPrice({
            model_name: values.model_name,
            unit: 'request',
            price_per_unit: values.request_price,
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
            }))
          )
        }
        Message.success('已创建')
        setVisible(false)
        fetchData()
      }
    } catch {
      Message.error('操作失败')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deletePrice(id)
      Message.success('已删除')
      fetchData()
    } catch {
      Message.error('删除失败')
    }
  }

  const filtered = searchText
    ? data.filter(d => d.model_name?.toLowerCase().includes(searchText.toLowerCase()))
    : data

  const columns = [
    { title: '模型名称', dataIndex: 'model_name' },
    {
      title: '计价单位',
      dataIndex: 'unit',
      render: (v: string) => <Tag>{UNIT_LABELS[v] ?? v}</Tag>,
    },
    {
      title: '单价 (USD)',
      dataIndex: 'price_per_unit',
      render: (v: number) => v.toFixed(6),
    },
    {
      title: '操作',
      render: (_: any, row: any) => (
        <Space>
          <Button size="mini" type="text" onClick={() => handleOpen(row)}>编辑</Button>
          <Popconfirm title="确认删除？" onOk={() => handleDelete(row.id)}>
            <Button size="mini" type="text" status="danger">删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Typography.Title heading={5} style={{ margin: 0 }}>价格管理</Typography.Title>
        <Space>
          <Input
            placeholder="搜索模型名"
            value={searchText}
            onChange={setSearchText}
            allowClear
            style={{ width: 200 }}
          />
          <Button type="primary" icon={<IconPlus />} onClick={() => handleOpen()}>新增价格</Button>
        </Space>
      </div>

      <Table columns={columns} data={filtered} loading={loading} rowKey="id" />

      <Modal
        title={editing ? '编辑价格' : '新增价格'}
        visible={visible}
        onCancel={() => setVisible(false)}
        onOk={() => form.submit()}
        unmountOnExit
      >
        <Form form={form} onSubmit={handleSubmit} layout="vertical">
          {!editing && (
            <>
              <Form.Item label="计价模式">
                <Radio.Group
                  value={priceMode}
                  onChange={(v) => { setPriceMode(v); form.resetFields(['unit']) }}
                >
                  <Radio value="token">按 Token</Radio>
                  <Radio value="request">按请求次数</Radio>
                </Radio.Group>
              </Form.Item>
              <Form.Item
                field="model_name"
                label="模型名称"
                rules={[{ required: true }]}
                extra='含空格支持模糊匹配，如 "gpt 3.5 turbo"'
              >
                <Input placeholder="如 gpt-4 或 gpt 4 turbo" />
              </Form.Item>
            </>
          )}

          {!editing && priceMode === 'token' && (
            <>
              <Form.Item field="input_price" label="Input 单价 (/1M USD)" rules={[{ required: true }]}>
                <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item field="output_price" label="Output 单价 (/1M USD)" rules={[{ required: true }]}>
                <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item field="cache_read_price" label="Cache Read 单价（选填）">
                <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item field="cache_write_price" label="Cache Write 单价（选填）">
                <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item field="extra_context_price" label="Extra Context 单价（选填）">
                <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}

          {!editing && priceMode === 'request' && (
            <Form.Item field="request_price" label="每次请求单价 (USD)" rules={[{ required: true }]}>
              <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} />
            </Form.Item>
          )}

          {editing && (
            <Form.Item field="price_per_unit" label="单价 (USD)" rules={[{ required: true }]}>
              <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}

export default Prices
