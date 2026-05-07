export interface OpenAIToolCall {
  index?: number
  id?: string
  type?: string
  function?: {
    name?: string
    arguments?: string
  }
}

export interface ContentBlock {
  type: string
  text?: string
  thinking?: string
  name?: string
  input?: unknown
  id?: string
  tool_use_id?: string
  content?: string | ContentBlock[]
}

export interface MessageEntry {
  role: string
  content?: string | ContentBlock[]
  reasoning_content?: string
  tool_calls?: OpenAIToolCall[]
  tool_call_id?: string
}

export interface ParsedResponseContent {
  reasoning: string
  content: string
  toolCalls: string
  errors: string
  finishReason?: string
  warnings: string[]
}

const formatJson = (value: unknown): string => {
  if (typeof value === 'string') {
    try { return JSON.stringify(JSON.parse(value), null, 2) } catch { return value }
  }
  try { return JSON.stringify(value, null, 2) } catch { return String(value) }
}

export const formatOpenAIToolCalls = (toolCalls?: OpenAIToolCall[]): string => {
  if (!Array.isArray(toolCalls) || toolCalls.length === 0) return ''
  return toolCalls.map((call, i) => {
    const name = call.function?.name ?? call.id ?? `tool_${i + 1}`
    const args = formatJson(call.function?.arguments ?? {})
    return `**${name}**\n\`\`\`json\n${args}\n\`\`\``
  }).join('\n\n')
}

const appendOpenAIToolCalls = (
  toolCalls: Map<number, OpenAIToolCall>,
  deltas: OpenAIToolCall[] | undefined,
) => {
  if (!Array.isArray(deltas)) return
  for (const delta of deltas) {
    const idx = delta.index ?? 0
    const current = toolCalls.get(idx) ?? { index: idx, function: { arguments: '' } }
    current.id = current.id ?? delta.id
    current.type = current.type ?? delta.type
    current.function = {
      name: current.function?.name ?? delta.function?.name,
      arguments: `${current.function?.arguments ?? ''}${delta.function?.arguments ?? ''}`,
    }
    toolCalls.set(idx, current)
  }
}

export const stringifyParsedResponse = (parts: ParsedResponseContent): string => {
  const output: string[] = []
  if (parts.warnings.length > 0) output.push(parts.warnings.join('\n\n'))
  if (parts.reasoning) output.push(`**Reasoning**\n\n${parts.reasoning}`)
  if (parts.content) output.push(parts.content)
  if (parts.toolCalls) output.push(parts.toolCalls)
  if (parts.errors) output.push(parts.errors)
  return output.join('\n\n')
}

export const parseMessages = (bodyStr?: string): MessageEntry[] => {
  if (!bodyStr) return []
  try {
    const parsed = JSON.parse(bodyStr)
    return Array.isArray(parsed?.messages) ? parsed.messages : []
  } catch {
    return []
  }
}

export const parseRequestMaxTokens = (bodyStr?: string): number | undefined => {
  if (!bodyStr) return undefined
  try {
    const parsed = JSON.parse(bodyStr)
    const value = parsed?.max_tokens
    return typeof value === 'number' && Number.isFinite(value) ? value : undefined
  } catch {
    return undefined
  }
}

export const extractDeltaText = (obj: Record<string, unknown>): string | null => {
  const error = obj.error as Record<string, unknown> | undefined
  if (error) {
    const code = error.code != null ? `[${error.code}] ` : ''
    const message = typeof error.message === 'string' ? error.message : JSON.stringify(error)
    return `${code}${message}`
  }

  const choices = obj.choices as Array<Record<string, unknown>> | undefined
  if (Array.isArray(choices) && choices.length > 0) {
    const delta = choices[0].delta as Record<string, unknown> | undefined
    const message = choices[0].message as Record<string, unknown> | undefined
    const text = (delta?.content ?? message?.content) as string | undefined
    if (typeof text === 'string') return text
  }

  if (obj.type === 'content_block_delta') {
    const d = obj.delta as Record<string, unknown> | undefined
    if (typeof d?.text === 'string') return d.text
  }

  const content = obj.content as Array<Record<string, unknown>> | undefined
  if (Array.isArray(content) && content.length > 0 && typeof content[0].text === 'string') {
    return content[0].text
  }

  const candidates = obj.candidates as Array<Record<string, unknown>> | undefined
  if (Array.isArray(candidates) && candidates.length > 0) {
    const parts = (candidates[0].content as Record<string, unknown> | undefined)
      ?.parts as Array<Record<string, unknown>> | undefined
    if (Array.isArray(parts) && typeof parts[0]?.text === 'string') return parts[0].text
  }
  return null
}

export const parseResponseParts = (bodyStr?: string): ParsedResponseContent => {
  const empty: ParsedResponseContent = { reasoning: '', content: '', toolCalls: '', errors: '', warnings: [] }
  if (!bodyStr) return empty

  const trimmed = bodyStr.trimStart()

  if (trimmed.startsWith('data:') || trimmed.includes('\ndata:')) {
    const textParts: string[] = []
    const reasoningParts: string[] = []
    const openAIToolCalls = new Map<number, OpenAIToolCall>()
    const toolBlocks = new Map<number, { name: string; partialJson: string }>()
    const errors: string[] = []
    const finishReasons: string[] = []

    for (const line of bodyStr.split('\n')) {
      const s = line.trim()
      if (!s.startsWith('data:')) continue
      const payload = s.slice(5).trim()
      if (payload === '[DONE]') continue
      try {
        const obj = JSON.parse(payload) as Record<string, unknown>
        const error = obj.error as Record<string, unknown> | undefined
        if (error) {
          const code = error.code != null ? `[${error.code}] ` : ''
          const message = typeof error.message === 'string' ? error.message : JSON.stringify(error)
          errors.push(`${code}${message}`)
          continue
        }

        if (obj.type === 'content_block_start') {
          const block = obj.content_block as Record<string, unknown> | undefined
          const idx = obj.index as number | undefined
          if (block?.type === 'tool_use' && idx !== undefined) {
            toolBlocks.set(idx, { name: (block.name as string) ?? 'unknown', partialJson: '' })
          }
        }

        const choices = obj.choices as Array<Record<string, unknown>> | undefined
        if (Array.isArray(choices)) {
          for (const choice of choices) {
            if (typeof choice.finish_reason === 'string') finishReasons.push(choice.finish_reason)
            const delta = choice.delta as Record<string, unknown> | undefined
            if (typeof delta?.reasoning_content === 'string') reasoningParts.push(delta.reasoning_content)
            appendOpenAIToolCalls(openAIToolCalls, delta?.tool_calls as OpenAIToolCall[] | undefined)
          }
        }

        const text = extractDeltaText(obj)
        if (text) {
          textParts.push(text)
        } else if (obj.type === 'content_block_delta') {
          const d = obj.delta as Record<string, unknown> | undefined
          const idx = obj.index as number | undefined
          if (d?.type === 'input_json_delta' && typeof d.partial_json === 'string' && idx !== undefined) {
            const block = toolBlocks.get(idx)
            if (block) block.partialJson += d.partial_json
          }
        }
      } catch { /* ignore invalid line */ }
    }

    const toolParts: string[] = []
    const openAIToolText = formatOpenAIToolCalls(Array.from(openAIToolCalls.values()))
    if (openAIToolText) toolParts.push(openAIToolText)
    if (toolBlocks.size > 0) {
      toolParts.push(Array.from(toolBlocks.values()).map(({ name, partialJson }) => {
        let input = partialJson
        try { input = JSON.stringify(JSON.parse(partialJson), null, 2) } catch { /* keep raw */ }
        return `**${name}**\n\`\`\`json\n${input}\n\`\`\``
      }).join('\n\n'))
    }
    const finishReason = finishReasons.find(reason => reason === 'length') ?? finishReasons[finishReasons.length - 1]
    return {
      reasoning: reasoningParts.join(''),
      content: textParts.join(''),
      toolCalls: toolParts.join('\n\n'),
      errors: errors.join('\n\n'),
      finishReason,
      warnings: buildResponseWarnings(finishReason, reasoningParts.length > 0, textParts.length > 0, toolParts.length > 0),
    }
  }

  try {
    const obj = JSON.parse(bodyStr) as Record<string, unknown>

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
      if (parts.length > 0) return { ...empty, content: parts.join('\n\n') }
    }

    const choices = obj.choices as Array<Record<string, unknown>> | undefined
    if (Array.isArray(choices) && choices.length > 0) {
      const finishReason = typeof choices[0].finish_reason === 'string' ? choices[0].finish_reason : undefined
      const message = choices[0].message as Record<string, unknown> | undefined
      if (message) {
        const reasoning = typeof message.reasoning_content === 'string' ? message.reasoning_content : ''
        const content = typeof message.content === 'string' ? message.content : ''
        return {
          reasoning,
          content,
          toolCalls: formatOpenAIToolCalls(message.tool_calls as OpenAIToolCall[] | undefined),
          errors: '',
          finishReason,
          warnings: buildResponseWarnings(
            finishReason,
            Boolean(reasoning),
            Boolean(content),
            Boolean(message.tool_calls),
          ),
        }
      }
    }

    return { ...empty, content: extractDeltaText(obj) ?? JSON.stringify(obj, null, 2) }
  } catch {
    return { ...empty, content: bodyStr }
  }
}

export const parseResponseContent = (bodyStr?: string): string => stringifyParsedResponse(parseResponseParts(bodyStr))

const buildResponseWarnings = (
  finishReason: string | undefined,
  hasReasoning: boolean,
  hasContent: boolean,
  hasToolCalls: boolean,
): string[] => {
  const warnings: string[] = []
  if (finishReason === 'length') {
    warnings.push('响应被长度限制截断（finish_reason=length）。如果只有 Reasoning 没有正文，通常是 max_tokens 太低，模型在思考阶段耗尽了输出 token。')
  }
  if (finishReason === 'tool_calls' && hasToolCalls && !hasContent) {
    warnings.push('模型返回了工具调用（finish_reason=tool_calls），因此正文 content 为空。')
  } else if (hasReasoning && !hasContent && finishReason !== 'length') {
    warnings.push('响应包含 Reasoning，但没有正文 content。')
  }
  return warnings
}
