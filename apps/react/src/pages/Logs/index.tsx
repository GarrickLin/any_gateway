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
import {
  type ContentBlock,
  type MessageEntry,
  formatOpenAIToolCalls,
  parseMessages,
  parseRequestMaxTokens,
  parseResponseParts,
} from './logParsing'

const { Row, Col } = Grid
const { RangePicker } = DatePicker

const today = dayjs().format('YYYY-MM-DD')

interface MessagesCache {
  loading: boolean
  data?: { request_url?: string; request_body?: string; response_body?: string }
  error?: string
}

const preStyle: React.CSSProperties = {
  margin: 0, padding: '10px 12px',
  fontSize: 12, lineHeight: 1.6,
  whiteSpace: 'pre', wordBreak: 'normal',
  overflowWrap: 'normal', overflowX: 'auto',
}

const RenderBlock: React.FC<{ block: ContentBlock }> = ({ block }) => {
  switch (block.type) {
    case 'text':
      return <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{block.text ?? ''}</ReactMarkdown>

    case 'thinking':
      return (
        <details className="ag-log-reasoning">
          <summary>thinking</summary>
          <pre className="ag-log-pre ag-log-pre-muted" style={preStyle}>{block.thinking}</pre>
        </details>
      )

    case 'tool_use':
      return (
        <div className="ag-log-tool-block ag-log-tool-use">
          <div className="ag-log-tool-header">
            <span>tool_use</span>
            <span className="ag-log-tool-name">{block.name}</span>
          </div>
          <pre className="ag-log-pre" style={preStyle}>{JSON.stringify(block.input, null, 2)}</pre>
        </div>
      )

    case 'tool_result': {
      const c = block.content
      const text = typeof c === 'string' ? c
        : Array.isArray(c) ? c.map(b => b.text ?? '').join('\n')
        : ''
      return (
        <div className="ag-log-tool-block ag-log-tool-result">
          <div className="ag-log-tool-header">
            tool_result
          </div>
          <pre className="ag-log-pre" style={preStyle}>{text || '（空）'}</pre>
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

const RenderMessage: React.FC<{ msg: MessageEntry }> = ({ msg }) => {
  const toolCalls = formatOpenAIToolCalls(msg.tool_calls)
  return (
    <>
      {msg.reasoning_content && (
        <details className="ag-log-reasoning ag-log-message-reasoning">
          <summary>reasoning</summary>
          <pre className="ag-log-pre ag-log-pre-muted" style={preStyle}>{msg.reasoning_content}</pre>
        </details>
      )}
      <RenderContent content={msg.content} />
      {toolCalls && (
        <div className="ag-log-tool-markdown">
          <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{toolCalls}</ReactMarkdown>
        </div>
      )}
      {msg.tool_call_id && (
        <Typography.Text type="secondary" className="ag-log-tool-id">
          tool_call_id: {msg.tool_call_id}
        </Typography.Text>
      )}
    </>
  )
}

const RenderReasoning: React.FC<{ reasoning: string }> = ({ reasoning }) => {
  if (!reasoning) return null
  return (
    <details className="ag-log-reasoning ag-log-response-reasoning">
      <summary>Reasoning</summary>
      <div className="ag-log-reasoning-body">
        <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{reasoning}</ReactMarkdown>
      </div>
    </details>
  )
}

const RenderWarnings: React.FC<{ warnings: string[]; maxTokens?: number }> = ({ warnings, maxTokens }) => {
  if (warnings.length === 0) return null
  return (
    <div className="ag-log-warnings">
      {warnings.map((warning, index) => (
        <div key={index}>
          {warning}
          {maxTokens !== undefined ? ` 当前请求 max_tokens=${maxTokens}。` : ''}
        </div>
      ))}
    </div>
  )
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
    <div className="ag-md-table">
      <table>{children}</table>
    </div>
  ),
  th: ({ children }: React.HTMLAttributes<HTMLTableCellElement>) => (
    <th>{children}</th>
  ),
  td: ({ children }: React.HTMLAttributes<HTMLTableCellElement>) => (
    <td>{children}</td>
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

  const statusLabel = (status: number) => {
    if (!status) return '-'
    if (status === 200) return '200 OK'
    if (status === 429) return '429 Rate'
    if (status >= 500) return `${status} Error`
    if (status >= 400) return `${status} Fail`
    return String(status)
  }

  const columns = [
    {
      title: 'Request ID',
      dataIndex: 'id',
      render: (v: string) => <span className="ag-log-request-id">{v?.slice(0, 8)}...</span>,
      width: 118,
    },
    ...(isAdmin ? [{
      title: 'Username',
      dataIndex: 'username',
      render: (v: string) => <span className="ag-log-strong-cell">{v || '-'}</span>,
      width: 108,
    }] : []),
    {
      title: 'API Key',
      dataIndex: 'token_name',
      render: (v: string) => (
        <span className="ag-log-muted-mono">
          {v && v.length > 16 ? `${v.slice(0, 12)}...` : (v || '-')}
        </span>
      ),
      width: 92,
    },
    {
      title: 'Model',
      dataIndex: 'model',
      render: (v: string) => v ? <Tag color="arcoblue">{v}</Tag> : '-',
      width: 180,
    },
    {
      title: 'Tokens (I/O)',
      render: (_: unknown, row: any) => (
        <span className="ag-log-token-cell">
          <strong>{row.input_tokens ?? 0}</strong>
          <span> / {row.output_tokens ?? 0}</span>
        </span>
      ),
      align: 'right' as const,
    },
    {
      title: 'Cache 读取',
      dataIndex: 'cache_read_tokens',
      render: (v: number) => <span className="ag-log-mono-cell">{v > 0 ? v : '-'}</span>,
      align: 'right' as const,
    },
    {
      title: 'Cache 写入',
      dataIndex: 'cache_creation_tokens',
      render: (v: number) => <span className="ag-log-mono-cell">{v > 0 ? v : '-'}</span>,
      align: 'right' as const,
    },
    {
      title: 'Dur. (ms)',
      dataIndex: 'duration_ms',
      render: (v: number) => <span className="ag-log-mono-cell">{v?.toFixed(0) ?? '-'}</span>,
      align: 'right' as const,
    },
    {
      title: 'Cost (USD)',
      dataIndex: 'cost_usd',
      render: (v: number) => <span className="ag-log-cost-cell">{v > 0 ? `$${v.toFixed(6)}` : '-'}</span>,
      align: 'right' as const,
    },
    {
      title: 'Package',
      dataIndex: 'covered_by_package',
      render: (v: boolean) => v ? <Tag color="purple">套餐</Tag> : <Tag color="gray">计费</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      render: (v: number) => <Tag color={statusColor(v)}>{statusLabel(v)}</Tag>,
      align: 'center' as const,
    },
    {
      title: 'Time',
      dataIndex: 'created_at',
      render: (v: string) => <span className="ag-log-time-cell">{v ? dayjs(v).format('HH:mm:ss') : '-'}</span>,
    },
  ]

  return (
    <div className="ag-page ag-logs-page">
      <div className="ag-page-header">
        <div>
          <p className="ag-page-eyebrow">Audit Trail</p>
          <h1 className="ag-page-title">Request Logs</h1>
          <p className="ag-page-description">
            Review gateway traffic, token usage, upstream status, and captured request or response payloads for audit investigations.
          </p>
        </div>
      </div>

      <div className="ag-filter-panel ag-logs-filter">
        <Row gutter={16}>
          <Col xs={24} sm={24} md={12} lg={8}>
            <div className="ag-filter-field">
              <label>Date Range</label>
              <RangePicker
                style={{ width: '100%' }}
                defaultValue={[dayjs(), dayjs()]}
                onChange={(dateStrings) =>
                  setFilters((f: any) => ({ ...f, start_date: dateStrings?.[0] || undefined, end_date: dateStrings?.[1] || undefined }))
                }
              />
            </div>
          </Col>
          <Col xs={24} sm={12} md={6} lg={4}>
            <div className="ag-filter-field">
              <label>Model Name</label>
              <Input
                placeholder="Search model..."
                onChange={(v) => setFilters((f: any) => ({ ...f, model: v || undefined }))}
              />
            </div>
          </Col>
          <Col xs={24} sm={12} md={6} lg={4}>
            <div className="ag-filter-field">
              <label>Status Code</label>
              <Select
                placeholder="All Statuses"
                allowClear
                options={[
                  { label: '200 OK', value: 200 },
                  { label: '4xx Client Error', value: 400 },
                  { label: '5xx Server Error', value: 500 },
                ]}
                onChange={(v) => setFilters((f: any) => ({ ...f, status: v }))}
                style={{ width: '100%' }}
              />
            </div>
          </Col>
          {isAdmin && (
            <Col xs={24} sm={12} md={6} lg={4}>
              <div className="ag-filter-field">
                <label>Username</label>
                <Input
                  placeholder="Search user..."
                  onChange={(v) => setFilters((f: any) => ({ ...f, username: v || undefined }))}
                />
              </div>
            </Col>
          )}
          <Col xs={24} sm={12} md={6} lg={4}>
            <Button type="primary" onClick={handleSearch} className="ag-logs-search-button">查询</Button>
          </Col>
        </Row>
      </div>

      <div className="ag-data-panel ag-logs-data-panel">
        <Table
          columns={columns}
          data={data}
          loading={loading}
          rowKey="id"
          scroll={{ x: 1500 }}
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
                <div className="ag-log-expanded ag-log-expanded-state">
                  <Spin tip="加载消息内容..." />
                </div>
              )
            }
            if (cache.error) {
              return (
                <div className="ag-log-expanded ag-log-expanded-error">
                  {cache.error === '消息文件不存在' ? '（暂无消息记录）' : `错误：${cache.error}`}
                </div>
              )
            }
            const messages = parseMessages(cache.data?.request_body)
            const responseParts = parseResponseParts(cache.data?.response_body)
            const maxTokens = parseRequestMaxTokens(cache.data?.request_body)
            const requestUrl = cache.data?.request_url
            const rawRequestJson = (() => {
              if (!cache.data?.request_body) return ''
              try { return JSON.stringify(JSON.parse(cache.data.request_body), null, 2) } catch { return cache.data.request_body }
            })()
            return (
              <div className="ag-log-expanded">
                {isAdmin && requestUrl && (
                  <div className="ag-log-target">
                    <Typography.Text bold className="ag-log-target-label">目标 URL：</Typography.Text>
                    <Typography.Text className="ag-log-target-url">
                      {requestUrl}
                    </Typography.Text>
                  </div>
                )}
                <section className="ag-log-section ag-log-request-section">
                  <div className="ag-log-section-header">
                    <Typography.Text bold>请求消息</Typography.Text>
                  </div>
                  {messages.length > 0 ? (
                    <div className="ag-log-message-list">
                      {messages.map((msg, i) => (
                        <div key={i} className="ag-log-message-row">
                          <Tag color={roleColor[msg.role] ?? 'gray'} className="ag-log-role-tag">
                            {msg.role}
                          </Tag>
                          <div className="ag-log-message-body" style={{ background: roleBgColor[msg.role] ?? '#f7f8fa' }}>
                            <RenderMessage msg={msg} />
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <Typography.Text type="secondary">（无请求消息）</Typography.Text>
                  )}
                </section>
                {rawRequestJson && (
                  <Collapse className="ag-log-raw-collapse" bordered={false}>
                    <Collapse.Item
                      header={
                        <div className="ag-log-collapse-header">
                          <span>Raw Request JSON</span>
                          <Button
                            size="mini"
                            className="ag-log-copy-button"
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
                      className="ag-log-raw-item"
                    >
                      <pre className="ag-log-pre ag-log-raw-pre" style={preStyle}>
                        {rawRequestJson}
                      </pre>
                    </Collapse.Item>
                  </Collapse>
                )}
                {(responseParts.warnings.length > 0 || responseParts.reasoning || responseParts.content || responseParts.toolCalls || responseParts.errors) && (
                  <section className="ag-log-section ag-log-response-section">
                    <div className="ag-log-section-header">
                      <Typography.Text bold>响应内容</Typography.Text>
                    </div>
                    <div className="ag-log-response">
                      <RenderWarnings warnings={responseParts.warnings} maxTokens={maxTokens} />
                      <RenderReasoning reasoning={responseParts.reasoning} />
                      {responseParts.content && (
                        <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{responseParts.content}</ReactMarkdown>
                      )}
                      {responseParts.toolCalls && (
                        <div className={responseParts.content ? 'ag-log-response-tools ag-log-response-tools-spaced' : 'ag-log-response-tools'}>
                          <Typography.Text bold>工具调用</Typography.Text>
                          <ReactMarkdown remarkPlugins={mdPlugins} components={mdComponents}>{responseParts.toolCalls}</ReactMarkdown>
                        </div>
                      )}
                      {responseParts.errors && (
                        <pre className="ag-log-pre ag-log-error-pre" style={preStyle}>
                          {responseParts.errors}
                        </pre>
                      )}
                    </div>
                  </section>
                )}
              </div>
            )
          }}
        />
      </div>
    </div>
  )
}

export default Logs
