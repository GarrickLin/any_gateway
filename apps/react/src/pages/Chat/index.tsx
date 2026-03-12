import React, { useState, useEffect, useRef } from 'react'
import {
  Select, Button, Input, Typography, Space, Message
} from '@arco-design/web-react'
import { getTokens } from '../../api/tokens'
import { useAuthStore } from '../../store/auth'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const ANTHROPIC_VERSION = '2023-06-01'
const ANTHROPIC_MAX_TOKENS = 4096

const Chat: React.FC = () => {
  const [keys, setKeys] = useState<{ name: string; key: string }[]>([])
  const [allModels, setAllModels] = useState<string[]>([])
  const [providers, setProviders] = useState<string[]>([])
  const [providerModelMap, setProviderModelMap] = useState<Record<string, string[]>>({})
  const [selectedKey, setSelectedKey] = useState('')
  const [selectedProvider, setSelectedProvider] = useState<string | undefined>(undefined)
  const [selectedModel, setSelectedModel] = useState('')
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const isAnthropic = selectedProvider?.toLowerCase() === 'anthropic'
  const jwtToken = useAuthStore(s => s.token)

  useEffect(() => {
    loadKeys()
    loadModels()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jwtToken])

  useEffect(() => {
    if (selectedKey) {
      setSelectedProvider(undefined)
      setSelectedModel('')
      loadModels(selectedKey)
    } else {
      loadModels()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  const loadKeys = async () => {
    try {
      const res = await getTokens()
      const raw = res.data?.data ?? res.data
      setKeys(Array.isArray(raw) ? raw.filter((k: { frozen?: boolean }) => !k.frozen) : [])
    } catch {
      // noop
    }
  }

  const loadModels = async (apiKey?: string) => {
    try {
      const headers: Record<string, string> = {}
      if (apiKey) {
        headers['x-api-key'] = apiKey
      } else if (jwtToken) {
        headers['Authorization'] = `Bearer ${jwtToken}`
      }
      const res = await fetch('/v1/models', { headers })
      if (!res.ok) {
        setAllModels([])
        setProviderModelMap({})
        setProviders([])
        return
      }
      const json = await res.json()
      const data: { id?: string; owned_by?: string }[] = json.data ?? []
      const models = data.map(m => m.id).filter(Boolean) as string[]
      setAllModels(models)

      // 从 owned_by 字段构建 provider→model 映射，无需访问 admin 端点
      const map: Record<string, Set<string>> = {}
      for (const m of data) {
        if (!m.id || !m.owned_by) continue
        if (!map[m.owned_by]) map[m.owned_by] = new Set()
        map[m.owned_by].add(m.id)
      }
      const result: Record<string, string[]> = {}
      for (const [p, set] of Object.entries(map)) {
        result[p] = Array.from(set)
      }
      setProviderModelMap(result)
      setProviders(Object.keys(result).sort())
    } catch {
      // noop
    }
  }

  const filteredModels = selectedProvider
    ? (providerModelMap[selectedProvider] ?? [])
    : allModels

  const curlCommand = selectedKey && selectedModel
    ? isAnthropic
      ? `curl http://localhost:8003/v1/messages \\\n  -H "x-api-key: ${selectedKey}" \\\n  -H "Content-Type: application/json" \\\n  -H "anthropic-version: ${ANTHROPIC_VERSION}" \\\n  -d '{"model": "${selectedModel}", "messages": [{"role": "user", "content": "你好"}], "max_tokens": ${ANTHROPIC_MAX_TOKENS}, "stream": true}'`
      : `curl http://localhost:8003/v1/chat/completions \\\n  -H "Authorization: Bearer ${selectedKey}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "${selectedModel}", "messages": [{"role": "user", "content": "你好"}], "stream": true}'`
    : '# 请先选择 API Key 和模型'

  const updateLastAssistant = (content: string) => {
    setHistory(prev => {
      const updated = [...prev]
      updated[updated.length - 1] = { role: 'assistant', content }
      return updated
    })
  }

  const removeEmptyLastAssistant = () => {
    setHistory(prev => {
      if (prev.length > 0 && prev[prev.length - 1].role === 'assistant' && prev[prev.length - 1].content === '') {
        return prev.slice(0, -1)
      }
      return prev
    })
  }

  const handleSend = async () => {
    if (!input.trim() || !selectedKey || !selectedModel) {
      Message.warning('请先选择 API Key 和模型，并输入消息')
      return
    }
    const content = input.trim()
    setInput('')
    setSending(true)

    const userMsg: ChatMessage = { role: 'user', content }
    const messages = [...history, userMsg]
    setHistory([...messages, { role: 'assistant', content: '' }])

    try {
      if (isAnthropic) {
        await sendAnthropic(messages)
      } else {
        await sendOpenAI(messages)
      }
    } catch {
      Message.error('请求出错，请检查网络和配置')
      removeEmptyLastAssistant()
    } finally {
      setSending(false)
    }
  }

  const sendOpenAI = async (messages: ChatMessage[]) => {
    const response = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${selectedKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ model: selectedModel, messages, stream: true }),
    })
    if (!response.ok) {
      let errMsg = `${response.status}`
      try {
        const body = await response.json()
        errMsg = body?.error ?? errMsg
      } catch { /* noop */ }
      Message.error(`请求失败：${errMsg}`)
      setHistory(prev => prev.slice(0, -1))
      return
    }
    let assistantContent = ''
    await readSSE(response, (line) => {
      if (!line.startsWith('data: ')) return
      const data = line.slice(6)
      if (data === '[DONE]') return
      try {
        const json = JSON.parse(data)
        if (json.error) {
          const err = json.error
          const rawMsg = typeof err === 'string' ? err : (err.message ?? JSON.stringify(err))
          const code = typeof err === 'object' && err.code != null ? err.code : ''
          const label = code ? `[${code}] ` : ''
          // toast 截断到 120 字符避免 Arco Message 渲染失败
          const toastMsg = rawMsg.length > 120 ? rawMsg.slice(0, 120) + '…' : rawMsg
          Message.error(`请求失败：${label}${toastMsg}`)
          // 将错误写入 assistant 气泡，方便用户看到完整信息
          setHistory(prev => {
            const last = prev[prev.length - 1]
            if (last?.role === 'assistant' && !last.content) {
              return [...prev.slice(0, -1), { role: 'assistant', content: `❌ 请求失败 ${label}${rawMsg}` }]
            }
            return prev
          })
          return
        }
        assistantContent += json.choices?.[0]?.delta?.content ?? ''
        updateLastAssistant(assistantContent)
      } catch {
        // noop
      }
    })
  }

  const sendAnthropic = async (messages: ChatMessage[]) => {
    const response = await fetch('/v1/messages', {
      method: 'POST',
      headers: {
        'x-api-key': selectedKey,
        'Content-Type': 'application/json',
        'anthropic-version': ANTHROPIC_VERSION,
      },
      body: JSON.stringify({
        model: selectedModel,
        messages,
        max_tokens: ANTHROPIC_MAX_TOKENS,
        stream: true,
      }),
    })
    if (!response.ok) {
      let errMsg = `${response.status}`
      try {
        const body = await response.json()
        errMsg = body?.error ?? errMsg
      } catch { /* noop */ }
      Message.error(`请求失败：${errMsg}`)
      setHistory(prev => prev.slice(0, -1))
      return
    }
    let assistantContent = ''
    await readSSE(response, (line) => {
      if (!line.startsWith('data: ')) return
      const data = line.slice(6)
      try {
        const json = JSON.parse(data)
        if (json.error) {
          const err = json.error
          const rawMsg = typeof err === 'string' ? err : (err.message ?? JSON.stringify(err))
          const code = typeof err === 'object' && err.code != null ? err.code : ''
          const label = code ? `[${code}] ` : ''
          const toastMsg = rawMsg.length > 120 ? rawMsg.slice(0, 120) + '…' : rawMsg
          Message.error(`请求失败：${label}${toastMsg}`)
          setHistory(prev => {
            const last = prev[prev.length - 1]
            if (last?.role === 'assistant' && !last.content) {
              return [...prev.slice(0, -1), { role: 'assistant', content: `❌ 请求失败 ${label}${rawMsg}` }]
            }
            return prev
          })
          return
        }
        if (json.type === 'content_block_delta' && json.delta?.type === 'text_delta') {
          assistantContent += json.delta.text ?? ''
          updateLastAssistant(assistantContent)
        }
      } catch {
        // noop
      }
    })
  }

  const readSSE = async (response: Response, onLine: (line: string) => void) => {
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) {
        // 处理末尾没有换行的残余内容
        if (buffer.trim()) onLine(buffer)
        break
      }
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // 最后一段可能不完整，留在 buffer 等待下一个 chunk
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.trim()) onLine(line)
      }
    }
  }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 120px)', gap: 16 }}>
      {/* 左侧对话区 */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* 工具栏 */}
        <Space style={{ marginBottom: 12 }}>
          <Select
            placeholder="选择 API Key"
            options={keys.map(k => ({ label: k.name, value: k.key }))}
            onChange={(v) => setSelectedKey(v)}
            style={{ width: 200 }}
          />
          <Select
            placeholder="按 Provider 筛选"
            allowClear
            options={providers.map(p => ({ label: p, value: p }))}
            onChange={(v) => {
              setSelectedProvider(v)
              setSelectedModel('')
            }}
            style={{ width: 160 }}
          />
          <Select
            placeholder="选择模型"
            value={selectedModel || undefined}
            options={filteredModels.map(m => ({ label: m, value: m }))}
            onChange={setSelectedModel}
            showSearch
            style={{ width: 240 }}
          />
        </Space>

        {/* 对话历史 */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px' }}>
          {history.map((msg, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                marginBottom: 12,
              }}
            >
              <div
                style={{
                  maxWidth: '70%',
                  padding: '8px 12px',
                  borderRadius: 8,
                  background: msg.role === 'user' ? '#165dff' : '#f2f3f5',
                  color: msg.role === 'user' ? '#fff' : '#1d2129',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {msg.content || (msg.role === 'assistant' && sending ? '▌' : '')}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* 输入框 */}
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          <Input.TextArea
            value={input}
            onChange={setInput}
            placeholder="输入消息，Enter 发送（Shift+Enter 换行）"
            autoSize={{ minRows: 1, maxRows: 4 }}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            style={{ flex: 1 }}
          />
          <Button type="primary" loading={sending} onClick={handleSend}>发送</Button>
        </div>
      </div>

      {/* 右侧 curl 面板 */}
      <div style={{ width: 360, background: '#1e1e1e', borderRadius: 8, padding: 16, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
          <Typography.Text style={{ color: '#fff' }}>
            {isAnthropic ? 'curl（Anthropic Messages）' : 'curl（OpenAI Chat）'}
          </Typography.Text>
          <Button
            size="mini"
            onClick={() => {
              navigator.clipboard.writeText(curlCommand)
              Message.success('已复制')
            }}
          >
            复制
          </Button>
        </div>
        <pre style={{ flex: 1, color: '#a9dc76', fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-all', overflowY: 'auto', margin: 0 }}>
          {curlCommand}
        </pre>
      </div>
    </div>
  )
}

export default Chat
