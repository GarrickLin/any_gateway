import React, { useEffect, useState, useCallback } from 'react'
import {
  Table, Button, Input, Select, DatePicker,
  Typography, Tag, Grid, Spin, Collapse, Message
} from '@arco-design/web-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import dayjs from 'dayjs'
import { getLogs, getMyLogs, getLogMessages, getMyLogMessages } from '../../api/logs'
import { useAuthStore } from '../../store/auth'

const { Row, Col } = Grid
const { RangePicker } = DatePicker

const today = dayjs().format('YYYY-MM-DD')

interface ContentBlock {
  type: string
  text?: string          // text block
  thinking?: string      // thinking block
  name?: string          // tool_use
  input?: unknown        // tool_use
  id?: string            // tool_use id
  tool_use_id?: string   // tool_result
  content?: string | ContentBlock[]  // tool_result
}

interface MessageEntry {
  role: string
  content: string | ContentBlock[]
}

interface MessagesCache {
  loading: boolean
  data?: { request_url?: string; request_body?: string; response_body?: string }
  error?: string
}

const parseMessages = (bodyStr?: string): MessageEntry[] => {
  if (!bodyStr) return []
  try {
    const parsed = JSON.parse(bodyStr)
    return Array.isArray(parsed?.messages) ? parsed.messages : []
  } catch {
    return []
  }
}

/** 从单个 SSE JSON 对象中提取文本增量（返回 null 表示无内容） */
const extractDeltaText = (obj: Record<string, unknown>): string | null => {
  // 错误响应: {"error":{"code":"...","message":"..."}}
  const error = obj.error as Record<string, unknown> | undefined
  if (error) {
    const code = error.code != null ? `[${error.code}] ` : ''
    const message = typeof error.message === 'string' ? error.message : JSON.stringify(error)
    return `${code}${message}`
  }
  // OpenAI / 兼容协议: choices[0].delta.content 或 choices[0].message.content
  const choices = obj.choices as Array<Record<string, unknown>> | undefined
  if (Array.isArray(choices) && choices.length > 0) {
    const delta = choices[0].delta as Record<string, unknown> | undefined
    const message = choices[0].message as Record<string, unknown> | undefined
    const text = (delta?.content ?? message?.content) as string | undefined
    if (typeof text === 'string') return text
  }
  // Anthropic streaming: content_block_delta event
  if (obj.type === 'content_block_delta') {
    const d = obj.delta as Record<string, unknown> | undefined
    if (typeof d?.text === 'string') return d.text
  }
  // Anthropic non-streaming: content[0].text
  const content = obj.content as Array<Record<string, unknown>> | undefined
  if (Array.isArray(content) && content.length > 0 && typeof content[0].text === 'string') {
    return content[0].text
  }
  // Gemini streaming/non-streaming: candidates[0].content.parts[0].text
  const candidates = obj.candidates as Array<Record<string, unknown>> | undefined
  if (Array.isArray(candidates) && candidates.length > 0) {
    const parts = (candidates[0].content as Record<string, unknown> | undefined)
      ?.parts as Array<Record<string, unknown>> | undefined
    if (Array.isArray(parts) && typeof parts[0]?.text === 'string') return parts[0].text
  }
  return null
}

const parseResponseContent = (bodyStr?: string): string => {
  if (!bodyStr) return ''

  const trimmed = bodyStr.trimStart()

  // SSE 格式检测：包含 "data:" 前缀的行
  if (trimmed.startsWith('data:') || trimmed.includes('\ndata:')) {
    const textParts: string[] = []
    // 追踪 tool_use 块：index -> { name, partialJson }
    const toolBlocks = new Map<number, { name: string; partialJson: string }>()

    for (const line of bodyStr.split('\n')) {
      const s = line.trim()
      if (!s.startsWith('data:')) continue
      const payload = s.slice(5).trim()
      if (payload === '[DONE]') continue
      try {
        const obj = JSON.parse(payload) as Record<string, unknown>

        // 记录 tool_use 块的名称
        if (obj.type === 'content_block_start') {
          const block = obj.content_block as Record<string, unknown> | undefined
          const idx = obj.index as number | undefined
          if (block?.type === 'tool_use' && idx !== undefined) {
            toolBlocks.set(idx, { name: (block.name as string) ?? 'unknown', partialJson: '' })
          }
        }

        const text = extractDeltaText(obj)
        if (text) {
          textParts.push(text)
        } else if (obj.type === 'content_block_delta') {
          // 拼装 input_json_delta（tool_use 输入）
          const d = obj.delta as Record<string, unknown> | undefined
          const idx = obj.index as number | undefined
          if (d?.type === 'input_json_delta' && typeof d.partial_json === 'string' && idx !== undefined) {
            const block = toolBlocks.get(idx)
            if (block) block.partialJson += d.partial_json
          }
        }
      } catch { /* 忽略无效行 */ }
    }

    // 合并文本和工具调用（可能同时存在）
    const parts: string[] = []
    if (textParts.length > 0) parts.push(textParts.join(''))
    if (toolBlocks.size > 0) {
      parts.push(Array.from(toolBlocks.values()).map(({ name, partialJson }) => {
        let input = partialJson
        try { input = JSON.stringify(JSON.parse(partialJson), null, 2) } catch { /* keep raw */ }
        return `**${name}**\n\`\`\`json\n${input}\n\`\`\``
      }).join('\n\n'))
    }
    return parts.join('\n\n')
  }

  // 非流式：直接解析 JSON
  try {
    const obj = JSON.parse(bodyStr) as Record<string, unknown>

    // Anthropic 非流式：content 数组可能同时包含 text 和 tool_use 块
    const content = obj.content as Array<Record<string, unknown>> | undefined
    if (Array.isArray(content) && content.length > 0) {
      const parts: string[] = []
      for (const block of content) {
        if (typeof block.text === 'string') {
          parts.push(block.text)
        } else if (block.type === 'tool_use') {
          let input = ''
          try { input = JSON.stringify(block.input, null, 2) } catch { input = String(block.input) }
          parts.push(`**${block.name as string}**\n\`\`\`json\n${input}\n\`\`\``)
        }
      }
      if (parts.length > 0) return parts.join('\n\n')
    }

    return extractDeltaText(obj) ?? JSON.stringify(obj, null, 2)
  } catch {
    return bodyStr
  }
}

const preStyle: React.CSSProperties = {
  margin: 0, padding: '6px 10px',
  background: '#f0f0f0', borderRadius: 4,
  fontSize: 12, lineHeight: 1.6,
  whiteSpace: 'pre-wrap', wordBreak: 'break-all',
  overflowX: 'auto',
}

const RenderBlock: React.FC<{ block: ContentBlock }> = ({ block }) => {
  switch (block.type) {
    case 'text':
      return <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{block.text ?? ''}</ReactMarkdown>

    case 'thinking':
      return (
        <details style={{ margin: '4px 0' }}>
          <summary style={{ cursor: 'pointer', color: '#8c8c8c', fontSize: 12 }}>thinking</summary>
          <pre style={{ ...preStyle, background: '#fafafa', color: '#595959', marginTop: 4 }}>{block.thinking}</pre>
        </details>
      )

    case 'tool_use':
      return (
        <div style={{ margin: '4px 0', border: '1px solid #d9d9d9', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{ padding: '3px 10px', background: '#e6f4ff', fontSize: 12, fontWeight: 600, color: '#1677ff', display: 'flex', gap: 6 }}>
            <span>tool_use</span>
            <span style={{ color: '#262626' }}>{block.name}</span>
          </div>
          <pre style={preStyle}>{JSON.stringify(block.input, null, 2)}</pre>
        </div>
      )

    case 'tool_result': {
      const c = block.content
      const text = typeof c === 'string' ? c
        : Array.isArray(c) ? c.map(b => b.text ?? '').join('\n')
        : ''
      return (
        <div style={{ margin: '4px 0', border: '1px solid #d9d9d9', borderRadius: 4, overflow: 'hidden' }}>
          <div style={{ padding: '3px 10px', background: '#f6ffed', fontSize: 12, fontWeight: 600, color: '#389e0d' }}>
            tool_result
          </div>
          <pre style={preStyle}>{text || '（空）'}</pre>
        </div>
      )
    }

    default:
      return <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{block.text ?? ''}</ReactMarkdown>
  }
}

const RenderContent: React.FC<{ content: MessageEntry['content'] }> = ({ content }) => {
  if (typeof content === 'string') {
    return <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{content || '（无内容）'}</ReactMarkdown>
  }
  if (Array.isArray(content) && content.length > 0) {
    return <>{content.map((b, i) => <RenderBlock key={i} block={b} />)}</>
  }
  return <span style={{ color: '#8c8c8c' }}>（无内容）</span>
}

const roleColor: Record<string, string> = {
  system: '#722ed1',
  user: '#1677ff',
  assistant: '#389e0d',
}

const roleBgColor: Record<string, string> = {
  system: '#f9f0ff',
  user: '#e8f4ff',
  assistant: '#f0f9eb',
}

const mdPlugins = [remarkGfm]

const mdComponents = {
  h1: ({ children }: React.HTMLAttributes<HTMLHeadingElement>) => <h3 style={{ fontSize: '1.1em', fontWeight: 600, margin: '8px 0 4px' }}>{children}</h3>,
  h2: ({ children }: React.HTMLAttributes<HTMLHeadingElement>) => <h4 style={{ fontSize: '1em', fontWeight: 600, margin: '6px 0 4px' }}>{children}</h4>,
  h3: ({ children }: React.HTMLAttributes<HTMLHeadingElement>) => <strong style={{ display: 'block', margin: '4px 0' }}>{children}</strong>,
  table: ({ children }: React.HTMLAttributes<HTMLTableElement>) => (
    <div style={{ overflowX: 'auto', margin: '8px 0' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }}>{children}</table>
    </div>
  ),
  th: ({ children }: React.HTMLAttributes<HTMLTableCellElement>) => (
    <th style={{ border: '1px solid #d9d9d9', padding: '4px 8px', background: '#f0f0f0', textAlign: 'left' }}>{children}</th>
  ),
  td: ({ children }: React.HTMLAttributes<HTMLTableCellElement>) => (
    <td style={{ border: '1px solid #d9d9d9', padding: '4px 8px' }}>{children}</td>
  ),
}

const Logs: React.FC = () => {
  const { role } = useAuthStore()
  const isAdmin = role === 'admin' || role === 'superadmin'
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState<any>({ start_date: today, end_date: today })
  const [messagesCache, setMessagesCache] = useState<Record<string, MessagesCache>>({})
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })

  const fetchLogs = async (params: any = {}) => {
    setLoading(true)
    try {
      const res = isAdmin ? await getLogs(params) : await getMyLogs(params)
      const raw = res.data?.data ?? res.data
      const total = res.data?.total ?? 0
      setData(Array.isArray(raw) ? raw : [])
      setPagination(prev => ({ ...prev, total, current: params.page ?? 1 }))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLogs({ start_date: today, end_date: today, page: 1, page_size: pagination.pageSize })
  }, [])

  const handleSearch = () => {
    const params = { ...filters, page: 1, page_size: pagination.pageSize }
    setPagination(prev => ({ ...prev, current: 1 }))
    fetchLogs(params)
  }

  const handlePageChange = (page: number, pageSize: number) => {
    fetchLogs({ ...filters, page, page_size: pageSize })
  }

  const handleExpand = useCallback(async (record: { id: string }, expanded: boolean) => {
    if (!expanded) return
    const id = record.id
    if (messagesCache[id]) return  // already fetched or loading

    setMessagesCache(prev => ({ ...prev, [id]: { loading: true } }))
    try {
      const res = isAdmin ? await getLogMessages(id) : await getMyLogMessages(id)
      setMessagesCache(prev => ({ ...prev, [id]: { loading: false, data: res.data } }))
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } } }
      const msg = e?.response?.data?.detail ?? '加载失败'
      setMessagesCache(prev => ({ ...prev, [id]: { loading: false, error: msg } }))
    }
  }, [messagesCache, isAdmin])

  const statusColor = (status: number) => {
    if (status >= 500) return 'red'
    if (status >= 400) return 'orange'
    return 'green'
  }

  const columns = [
    { title: 'Request ID', dataIndex: 'id', render: (v: string) => v?.slice(0, 8) + '...' },
    ...(isAdmin ? [{ title: '用户名', dataIndex: 'username', render: (v: string) => v || '-' }] : []),
    { title: 'API Key', dataIndex: 'token_name', render: (v: string) => v || '-' },
    { title: '模型', dataIndex: 'model' },
    { title: '输入 Token', dataIndex: 'input_tokens' },
    { title: '输出 Token', dataIndex: 'output_tokens' },
    {
      title: 'Cache 读取',
      dataIndex: 'cache_read_tokens',
      render: (v: number) => v > 0 ? v : '-',
    },
    {
      title: 'Cache 写入',
      dataIndex: 'cache_creation_tokens',
      render: (v: number) => v > 0 ? v : '-',
    },
    { title: '耗时(ms)', dataIndex: 'duration_ms', render: (v: number) => v?.toFixed(0) },
    {
      title: '状态码',
      dataIndex: 'status',
      render: (v: number) => <Tag color={statusColor(v)}>{v || '-'}</Tag>
    },
    { title: '时间', dataIndex: 'created_at', render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-' },
  ]

  return (
    <div>
      <Typography.Title heading={5} style={{ marginBottom: 16 }}>请求日志</Typography.Title>

      {/* 过滤区 */}
      <div style={{ background: '#fff', padding: 16, marginBottom: 16, borderRadius: 4 }}>
        <Row gutter={16}>
          <Col span={8}>
            <RangePicker
              style={{ width: '100%' }}
              defaultValue={[dayjs(), dayjs()]}
              onChange={(dateStrings) =>
                setFilters((f: any) => ({ ...f, start_date: dateStrings?.[0] || undefined, end_date: dateStrings?.[1] || undefined }))
              }
            />
          </Col>
          <Col span={4}>
            <Input
              placeholder="模型名称"
              onChange={(v) => setFilters((f: any) => ({ ...f, model: v || undefined }))}
            />
          </Col>
          <Col span={4}>
            <Select
              placeholder="状态码"
              allowClear
              options={[
                { label: '200 成功', value: 200 },
                { label: '4xx 客户端错误', value: 400 },
                { label: '5xx 服务端错误', value: 500 },
              ]}
              onChange={(v) => setFilters((f: any) => ({ ...f, status: v }))}
              style={{ width: '100%' }}
            />
          </Col>
          {isAdmin && (
            <Col span={4}>
              <Input
                placeholder="用户名"
                onChange={(v) => setFilters((f: any) => ({ ...f, username: v || undefined }))}
              />
            </Col>
          )}
          <Col span={4}>
            <Button type="primary" onClick={handleSearch}>查询</Button>
          </Col>
        </Row>
      </div>

      <Table
        columns={columns}
        data={data}
        loading={loading}
        rowKey="id"
        onExpand={handleExpand}
        pagination={{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          showTotal: true,
          onChange: handlePageChange,
        }}
        expandedRowRender={(record) => {
          const cache = messagesCache[record.id]
          if (!cache || cache.loading) {
            return (
              <div style={{ padding: 16, textAlign: 'center' }}>
                <Spin tip="加载消息内容..." />
              </div>
            )
          }
          if (cache.error) {
            return (
              <div style={{ padding: 8, color: '#f53f3f' }}>
                {cache.error === '消息文件不存在' ? '（暂无消息记录）' : `错误：${cache.error}`}
              </div>
            )
          }
          const messages = parseMessages(cache.data?.request_body)
          const responseText = parseResponseContent(cache.data?.response_body)
          const requestUrl = cache.data?.request_url
          const rawRequestJson = (() => {
            if (!cache.data?.request_body) return ''
            try { return JSON.stringify(JSON.parse(cache.data.request_body), null, 2) } catch { return cache.data.request_body }
          })()
          return (
            <div style={{ padding: '8px 16px' }}>
              {isAdmin && requestUrl && (
                <div style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <Typography.Text bold style={{ flexShrink: 0 }}>目标 URL：</Typography.Text>
                  <Typography.Text style={{ fontFamily: 'monospace', fontSize: 13, wordBreak: 'break-all' }}>
                    {requestUrl}
                  </Typography.Text>
                </div>
              )}
              {messages.length > 0 ? (
                <>
                  <Typography.Text bold style={{ display: 'block', marginBottom: 8 }}>请求消息</Typography.Text>
                  {messages.map((msg, i) => (
                    <div key={i} style={{ marginBottom: 8, display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                      <Tag color={roleColor[msg.role] ?? 'gray'} style={{ flexShrink: 0, marginTop: 2 }}>
                        {msg.role}
                      </Tag>
                      <div style={{
                        flex: 1, maxHeight: 400, overflow: 'auto',
                        background: roleBgColor[msg.role] ?? '#f7f8fa',
                        padding: '4px 10px', borderRadius: 4,
                        fontSize: 13, lineHeight: 1.6,
                      }}>
                        <RenderContent content={msg.content} />
                      </div>
                    </div>
                  ))}
                </>
              ) : (
                <Typography.Text type="secondary">（无请求消息）</Typography.Text>
              )}
              {rawRequestJson && (
                <Collapse style={{ marginTop: 12 }} bordered={false}>
                  <Collapse.Item
                    header={
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span>Raw Request JSON</span>
                        <Button
                          size="mini"
                          style={{ marginLeft: 8 }}
                          onClick={(e) => {
                            e.stopPropagation()
                            navigator.clipboard.writeText(rawRequestJson)
                              .then(() => Message.success('已复制'))
                              .catch(() => Message.error('复制失败'))
                          }}
                        >
                          复制
                        </Button>
                      </div>
                    }
                    name="raw"
                    style={{ background: '#fafafa', borderRadius: 4, fontSize: 13 }}
                  >
                    <pre style={{
                      margin: 0, padding: '8px 12px', maxHeight: 400, overflow: 'auto',
                      background: '#f7f8fa', borderRadius: 4,
                      fontSize: 12, lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                    }}>
                      {rawRequestJson}
                    </pre>
                  </Collapse.Item>
                </Collapse>
              )}
              {responseText && (
                <>
                  <Typography.Text bold style={{ display: 'block', margin: '12px 0 8px' }}>响应内容</Typography.Text>
                  <div style={{
                    maxHeight: 400, overflow: 'auto',
                    background: '#f0f9eb', padding: '6px 16px', borderRadius: 4,
                    fontSize: 13, lineHeight: 1.6,
                  }}>
                    <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{responseText}</ReactMarkdown>
                  </div>
                </>
              )}
            </div>
          )
        }}
      />
    </div>
  )
}

export default Logs
