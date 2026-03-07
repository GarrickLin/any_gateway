import React, { useState, useEffect, useCallback } from 'react'
import {
  Table,
  Button,
  Drawer,
  Form,
  Input,
  Select,
  Switch,
  InputNumber,
  Tag,
  Message,
  Space,
  Popconfirm,
  Typography,
  Grid,
  Modal,
} from '@arco-design/web-react'
import { IconPlus, IconDelete, IconRefresh } from '@arco-design/web-react/icon'
import type { ColumnProps } from '@arco-design/web-react/es/Table'
import {
  getChannels,
  createChannel,
  updateChannel,
  deleteChannel,
  fetchChannelModels,
  type Channel,
} from '../../api/channels'

const { Row, Col } = Grid
const FormItem = Form.Item

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'arcoblue',
  anthropic: 'purple',
  gemini: 'green',
}

const PROVIDER_OPTIONS = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'Gemini', value: 'gemini' },
]

interface Mapping {
  from: string
  to: string
}

function parseModelsCount(models: string | null): number {
  try {
    return JSON.parse(models || '[]').length
  } catch {
    return 0
  }
}

function parseModelIds(models: string | null): string[] {
  try {
    const list = JSON.parse(models || '[]')
    // 支持对象数组（{id: ...}）和字符串数组两种格式
    return list.map((m: unknown) =>
      m && typeof m === 'object' && 'id' in m ? String((m as { id: unknown }).id) : String(m)
    )
  } catch {
    return []
  }
}

function parseMappings(model_mapping: string | null): Mapping[] {
  try {
    const obj = JSON.parse(model_mapping || '{}')
    return Object.entries(obj).map(([from, to]) => ({ from, to: to as string }))
  } catch {
    return []
  }
}

const Channels: React.FC = () => {
  const [data, setData] = useState<Channel[]>([])
  const [loading, setLoading] = useState(false)
  const [drawerVisible, setDrawerVisible] = useState(false)
  const [editingChannel, setEditingChannel] = useState<Channel | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [fetchingModels, setFetchingModels] = useState<string | null>(null)
  const [mappings, setMappings] = useState<Mapping[]>([])
  const [viewModelsChannel, setViewModelsChannel] = useState<Channel | null>(null)

  const [form] = Form.useForm()

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getChannels()
      setData(res.data?.data ?? res.data ?? [])
    } catch {
      Message.error('获取 Channel 列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const openCreate = () => {
    setEditingChannel(null)
    setMappings([])
    form.resetFields()
    form.setFieldsValue({ weight: 1, enabled: true, provider: 'openai' })
    setDrawerVisible(true)
  }

  const openEdit = (channel: Channel) => {
    setEditingChannel(channel)
    setMappings(parseMappings(channel.model_mapping))
    form.resetFields()
    form.setFieldsValue({
      name: channel.name,
      provider: channel.provider,
      base_url: channel.base_url,
      api_key: '',
      weight: channel.weight,
      enabled: channel.enabled,
    })
    setDrawerVisible(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validate()
      setSubmitting(true)

      // 构建 model_mapping JSON
      const mappingObj: Record<string, string> = {}
      mappings.forEach((m) => {
        if (m.from) mappingObj[m.from] = m.to
      })
      const model_mapping = JSON.stringify(mappingObj)

      if (editingChannel) {
        const payload: Record<string, unknown> = {
          name: values.name,
          provider: values.provider,
          base_url: values.base_url,
          weight: values.weight,
          enabled: values.enabled,
          model_mapping,
        }
        // 仅当用户填写了新 API Key 才更新
        if (values.api_key) {
          payload.api_key = values.api_key
        }
        await updateChannel(editingChannel.id, payload)
        Message.success('Channel 更新成功')
      } else {
        await createChannel({
          name: values.name,
          provider: values.provider,
          base_url: values.base_url,
          api_key: values.api_key,
          weight: values.weight,
          enabled: values.enabled,
          model_mapping,
        })
        Message.success('Channel 创建成功')
      }

      setDrawerVisible(false)
      fetchData()
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'errors' in err) {
        // Form validation error — already shown by Arco
        return
      }
      Message.error('操作失败，请重试')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteChannel(id)
      Message.success('删除成功')
      fetchData()
    } catch {
      Message.error('删除失败')
    }
  }

  const handleFetchModels = async (id: string) => {
    setFetchingModels(id)
    try {
      await fetchChannelModels(id)
      Message.success('模型列表已更新')
      fetchData()
    } catch {
      Message.error('获取模型失败')
    } finally {
      setFetchingModels(null)
    }
  }

  const addMapping = () => {
    setMappings((prev) => [...prev, { from: '', to: '' }])
  }

  const updateMapping = (index: number, field: 'from' | 'to', value: string) => {
    setMappings((prev) => {
      const next = [...prev]
      next[index] = { ...next[index], [field]: value }
      return next
    })
  }

  const removeMapping = (index: number) => {
    setMappings((prev) => prev.filter((_, i) => i !== index))
  }

  const columns: ColumnProps<Channel>[] = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 160,
    },
    {
      title: 'Provider',
      dataIndex: 'provider',
      key: 'provider',
      width: 120,
      render: (provider: string) => (
        <Tag color={PROVIDER_COLORS[provider] ?? 'gray'}>{provider}</Tag>
      ),
    },
    {
      title: 'Base URL',
      dataIndex: 'base_url',
      key: 'base_url',
      width: 240,
      ellipsis: true,
    },
    {
      title: 'Weight',
      dataIndex: 'weight',
      key: 'weight',
      width: 80,
      align: 'center',
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      key: 'enabled',
      width: 90,
      align: 'center',
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'gray'}>{enabled ? 'Enabled' : 'Disabled'}</Tag>
      ),
    },
    {
      title: '模型数',
      dataIndex: 'models',
      key: 'models',
      width: 80,
      align: 'center',
      render: (models: string | null, record: Channel) => {
        const count = parseModelsCount(models)
        if (count === 0) return <span style={{ color: '#999' }}>0</span>
        return (
          <Typography.Text
            style={{ color: 'rgb(var(--arcoblue-6))', cursor: 'pointer' }}
            onClick={() => setViewModelsChannel(record)}
          >
            {count}
          </Typography.Text>
        )
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_: unknown, record: Channel) => (
        <Space>
          <Button size="small" type="text" onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Button
            size="small"
            type="text"
            icon={<IconRefresh />}
            loading={fetchingModels === record.id}
            onClick={() => handleFetchModels(record.id)}
          >
            获取模型
          </Button>
          <Popconfirm
            title="确定要删除此 Channel 吗？"
            onOk={() => handleDelete(record.id)}
            okText="删除"
            cancelText="取消"
          >
            <Button size="small" type="text" status="danger">
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Typography.Title heading={5} style={{ margin: 0 }}>
          Channel 管理
        </Typography.Title>
        <Button type="primary" icon={<IconPlus />} onClick={openCreate}>
          新建 Channel
        </Button>
      </div>

      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        data={data}
        pagination={{ pageSize: 20, showTotal: true }}
        scroll={{ x: true }}
      />

      {/* 模型列表查看 Modal */}
      <Modal
        title={`${viewModelsChannel?.name ?? ''} — 模型列表`}
        visible={!!viewModelsChannel}
        onCancel={() => setViewModelsChannel(null)}
        footer={
          <Button onClick={() => setViewModelsChannel(null)}>关闭</Button>
        }
        style={{ maxWidth: 480 }}
      >
        <div
          style={{
            maxHeight: 400,
            overflowY: 'auto',
            display: 'flex',
            flexWrap: 'wrap',
            gap: 8,
            padding: '4px 0',
          }}
        >
          {parseModelIds(viewModelsChannel?.models ?? null).map((id) => (
            <Tag key={id} color="arcoblue" style={{ marginBottom: 0 }}>
              {id}
            </Tag>
          ))}
        </div>
      </Modal>

      <Drawer
        title={editingChannel ? '编辑 Channel' : '新建 Channel'}
        visible={drawerVisible}
        width={520}
        onCancel={() => setDrawerVisible(false)}
        footer={
          <div style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setDrawerVisible(false)}>取消</Button>
              <Button type="primary" loading={submitting} onClick={handleSubmit}>
                保存
              </Button>
            </Space>
          </div>
        }
        unmountOnExit
      >
        <Form form={form} layout="vertical" autoComplete="off">
          <FormItem
            label="名称"
            field="name"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="Channel 名称" />
          </FormItem>

          <FormItem
            label="Provider"
            field="provider"
            rules={[{ required: true, message: '请选择 Provider' }]}
          >
            <Select options={PROVIDER_OPTIONS} placeholder="选择 Provider" />
          </FormItem>

          <FormItem
            label="Base URL"
            field="base_url"
            rules={[{ required: true, message: '请输入 Base URL' }]}
          >
            <Input placeholder="https://api.openai.com/v1" />
          </FormItem>

          <FormItem
            label="API Key"
            field="api_key"
            rules={
              editingChannel
                ? []
                : [{ required: true, message: '请输入 API Key' }]
            }
            extra={editingChannel ? '留空则保留原有 API Key' : undefined}
          >
            <Input.Password
              placeholder={editingChannel ? '（留空保持不变）' : '请输入 API Key'}
            />
          </FormItem>

          <Row gutter={16}>
            <Col span={12}>
              <FormItem label="Weight" field="weight">
                <InputNumber min={0} step={1} style={{ width: '100%' }} />
              </FormItem>
            </Col>
            <Col span={12}>
              <FormItem label="启用" field="enabled" triggerPropName="checked">
                <Switch />
              </FormItem>
            </Col>
          </Row>

          {/* model_mapping 编辑器 */}
          <div style={{ marginBottom: 8 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <Typography.Text style={{ fontWeight: 500 }}>Model Mapping</Typography.Text>
              <Button
                size="small"
                type="dashed"
                icon={<IconPlus />}
                onClick={addMapping}
              >
                添加映射
              </Button>
            </div>

            {mappings.length === 0 && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                无映射规则，点击"添加映射"来配置模型名称转换
              </Typography.Text>
            )}

            {mappings.map((mapping, index) => (
              <Row key={index} gutter={8} style={{ marginBottom: 8 }} align="center">
                <Col flex={1}>
                  <Input
                    placeholder="from（原模型名）"
                    value={mapping.from}
                    onChange={(v) => updateMapping(index, 'from', v)}
                  />
                </Col>
                <Col style={{ padding: '0 4px', color: '#999' }}>→</Col>
                <Col flex={1}>
                  <Input
                    placeholder="to（目标模型名）"
                    value={mapping.to}
                    onChange={(v) => updateMapping(index, 'to', v)}
                  />
                </Col>
                <Col>
                  <Button
                    size="small"
                    type="text"
                    status="danger"
                    icon={<IconDelete />}
                    onClick={() => removeMapping(index)}
                  />
                </Col>
              </Row>
            ))}
          </div>
        </Form>
      </Drawer>
    </div>
  )
}

export default Channels
