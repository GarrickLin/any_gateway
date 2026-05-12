import React, { useState, useEffect, useCallback } from 'react'
import {
  Table, Button, Modal, Form, InputNumber, DatePicker,
  Popconfirm, Message, Typography, Tag,
} from '@arco-design/web-react'
import { IconPlus } from '@arco-design/web-react/icon'
import { getVouchers, createVoucher, deleteVoucher } from '../../api/vouchers'

const Vouchers: React.FC = () => {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [visible, setVisible] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getVouchers()
      const raw = res.data?.data ?? res.data
      setData(Array.isArray(raw) ? raw : [])
    } catch {
      Message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleSubmit = async (values: any) => {
    setSubmitting(true)
    try {
      const payload: any = {
        amount_usd: values.amount_usd,
        count: values.count ?? 1,
      }
      if (values.expires_at) {
        payload.expires_at = values.expires_at
      }
      const res = await createVoucher(payload)
      const data = res.data
      if (data?.vouchers) {
        // 批量创建
        Message.success(`已生成 ${data.count} 张消费券`)
      } else {
        const code = data?.code ?? data?.data?.code ?? '（查看列表）'
        Message.success(`创建成功！券码：${code}`)
      }
      setVisible(false)
      form.resetFields()
      fetchData()
    } catch {
      Message.error('创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteVoucher(id)
      Message.success('已删除')
      fetchData()
    } catch {
      Message.error('删除失败')
    }
  }

  const columns = [
    {
      title: '券码',
      dataIndex: 'code',
      render: (v: string) => (
        <Typography.Text copyable style={{ fontFamily: 'monospace', fontSize: 12, color: 'var(--ag-primary)', fontWeight: 600 }}>{v}</Typography.Text>
      ),
    },
    {
      title: '金额 (USD)',
      dataIndex: 'amount_usd',
      render: (v: number) => <strong style={{ fontFamily: 'monospace' }}>${v.toFixed(2)}</strong>,
    },
    {
      title: '过期时间',
      dataIndex: 'expires_at',
      render: (v: string) => v
        ? <span style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--ag-outline)' }}>{v.slice(0, 10)}</span>
        : <Tag color="gray">永不过期</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'used',
      render: (v: boolean) => (
        <Tag color={v ? 'gray' : 'green'}>{v ? '已使用' : '未使用'}</Tag>
      ),
    },
    {
      title: '使用人',
      dataIndex: 'used_by',
      render: (v: string) => v
        ? <span style={{ fontWeight: 700 }}>{v}</span>
        : <span style={{ color: 'var(--ag-outline)' }}>—</span>,
    },
    {
      title: '操作',
      render: (_: any, row: any) => (
        row.used ? null : (
          <Popconfirm title="确认删除此消费券？" onOk={() => handleDelete(row.id)}>
            <Button size="mini" type="text" status="danger">删除</Button>
          </Popconfirm>
        )
      ),
    },
  ]

  return (
    <div className="ag-page ag-workbench-page">
      <div className="ag-page-header">
        <div>
          <p className="ag-page-eyebrow">Credit Grants</p>
          <h1 className="ag-page-title">Vouchers</h1>
          <p className="ag-page-description">生成和管理消费券，用于为账号充值或发放额度。</p>
        </div>
        <div className="ag-header-actions">
          <Button type="primary" icon={<IconPlus />} onClick={() => { form.resetFields(); setVisible(true) }}>
            生成消费券
          </Button>
        </div>
      </div>

      <div className="ag-data-panel ag-workbench-panel ag-table-panel">
        <div className="ag-panel-header">
          <div>
            <h2 className="ag-panel-title">消费券列表</h2>
            <p className="ag-panel-subtitle">追踪额度发放、领取状态和过期时间</p>
          </div>
        </div>

        <Table columns={columns} data={data} loading={loading} rowKey="id" />
      </div>

      <Modal
        title="生成消费券"
        visible={visible}
        onCancel={() => setVisible(false)}
        onOk={() => form.submit()}
        confirmLoading={submitting}
        unmountOnExit
      >
        <Form form={form} onSubmit={handleSubmit} layout="vertical">
          <Form.Item field="amount_usd" label="金额 (USD)" rules={[{ required: true }]}>
            <InputNumber min={0.01} step={1} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item field="count" label="数量" initialValue={1} rules={[{ required: true }]}>
            <InputNumber min={1} max={100} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item field="expires_at" label="过期时间（选填）">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default Vouchers
