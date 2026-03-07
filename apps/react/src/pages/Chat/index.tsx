import React, { useState, useEffect, useRef } from 'react'
import {
  Select, Button, Input, Typography, Space, Message
} from '@arco-design/web-react'
import { getTokens } from '../../api/tokens'

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const Chat: React.FC = () => {
  const [keys, setKeys] = useState<any[]>([])
  const [models, setModels] = useState<string[]>([])
  const [selectedKey, setSelectedKey] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [history, setHistory] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadKeys()
    loadModels()
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history])

  const loadKeys = async () => {
    try {
      const res = await getTokens()
      const raw = res.data?.data ?? res.data
      setKeys(Array.isArray(raw) ? raw.filter((k: any) => !k.frozen) : [])
    } catch {}
  }

  const loadModels = async () => {
    try {
      const res = await fetch('/v1/models')
      const json = await res.json()
      const data: any[] = json.data ?? []
      setModels(data.map((m: any) => m.id).filter(Boolean))
    } catch {}
  }

  const curlCommand = selectedKey && selectedModel
    ? `curl http://localhost:8003/v1/chat/completions \\\n  -H "Authorization: Bearer ${selectedKey}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"model": "${selectedModel}", "messages": [{"role": "user", "content": "你好"}], "stream": true}'`
    : '# 请先选择 API Key 和模型'

  const handleSend = async () => {
    if (!input.trim() || !selectedKey || !selectedModel) {
      Message.warning('请先选择 API Key 和模型，并输入消息')
      return
    }
    const content = input.trim()
    setInput('')
    setSending(true)

    try {
      const userMsg: ChatMessage = { role: 'user', content }
      const messages = [...history, userMsg]
      setHistory([...messages, { role: 'assistant', content: '' }])

      const response = await fetch('/v1/chat/completions', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${selectedKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ model: selectedModel, messages, stream: true }),
      })

      if (!response.ok) {
        Message.error(`请求失败：${response.status} ${response.statusText}`)
        setHistory(prev => prev.slice(0, -1))
        return
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = decoder.decode(value)
        const lines = chunk.split('\n').filter(l => l.startsWith('data: '))
        for (const line of lines) {
          const data = line.slice(6)
          if (data === '[DONE]') continue
          try {
            const json = JSON.parse(data)
            const delta = json.choices?.[0]?.delta?.content || ''
            assistantContent += delta
            setHistory(prev => {
              const updated = [...prev]
              updated[updated.length - 1] = { role: 'assistant', content: assistantContent }
              return updated
            })
          } catch {}
        }
      }
    } catch (err) {
      Message.error('请求出错，请检查网络和配置')
      setHistory(prev => {
        const updated = [...prev]
        if (updated.length > 0 && updated[updated.length - 1].role === 'assistant' && updated[updated.length - 1].content === '') {
          return updated.slice(0, -1)
        }
        return updated
      })
    } finally {
      setSending(false)
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
            onChange={(v) => {
              setSelectedKey(v)
            }}
            style={{ width: 200 }}
          />
          <Select
            placeholder="选择模型"
            options={models.map(m => ({ label: m, value: m }))}
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
          <Typography.Text style={{ color: '#fff' }}>curl 命令</Typography.Text>
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
