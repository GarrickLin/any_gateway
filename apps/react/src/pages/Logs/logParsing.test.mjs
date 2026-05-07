import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { build } from 'esbuild'

const outdir = join(tmpdir(), 'any-gateway-log-parsing-tests')
await mkdir(outdir, { recursive: true })

const outfile = join(outdir, 'logParsing.mjs')
await build({
  entryPoints: [new URL('./logParsing.ts', import.meta.url).pathname],
  outfile,
  bundle: true,
  platform: 'node',
  format: 'esm',
})

const {
  parseResponseContent,
  parseResponseParts,
  parseMessages,
  parseRequestMaxTokens,
} = await import(pathToFileURL(outfile))

const openAiJson = JSON.stringify({
  choices: [{
    finish_reason: 'length',
    message: {
      role: 'assistant',
      content: '',
      reasoning_content: '分析过程 <tool_call>{"a":1}</tool_call>',
    },
  }],
})
assert.match(parseResponseContent(openAiJson), /分析过程/)
const jsonParts = parseResponseParts(openAiJson)
assert.equal(jsonParts.reasoning, '分析过程 <tool_call>{"a":1}</tool_call>')
assert.equal(jsonParts.content, '')
assert.equal(jsonParts.finishReason, 'length')
assert.match(jsonParts.warnings[0], /finish_reason=length/)

const openAiSse = [
  'data: {"choices":[{"delta":{"reasoning_content":"思考 <step>"}}]}',
  'data: {"choices":[{"delta":{"reasoning_content":"完整 </step>"}}]}',
  'data: {"choices":[{"delta":{"content":"答案"}}]}',
  'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"search","arguments":"{\\"q\\":"}}]}}]}',
  'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"AI\\"}"}}]}}]}',
  'data: {"choices":[{"finish_reason":"stop","delta":{}}]}',
  'data: [DONE]',
].join('\n\n')
const sseText = parseResponseContent(openAiSse)
assert.match(sseText, /思考/)
assert.match(sseText, /答案/)
assert.match(sseText, /search/)
assert.match(sseText, /"q": "AI"/)
const sseParts = parseResponseParts(openAiSse)
assert.equal(sseParts.reasoning, '思考 <step>完整 </step>')
assert.equal(sseParts.content, '答案')
assert.equal(sseParts.finishReason, 'stop')

const messages = parseMessages(JSON.stringify({
  messages: [{
    role: 'assistant',
    content: '',
    reasoning_content: '请求侧思考',
    tool_calls: [{
      id: 'call_1',
      type: 'function',
      function: { name: 'browser_navigate', arguments: '{"url":"https://example.com"}' },
    }],
  }, {
    role: 'tool',
    tool_call_id: 'call_1',
    content: '{"ok":true}',
  }],
}))
assert.equal(messages[0].reasoning_content, '请求侧思考')
assert.equal(messages[0].tool_calls[0].function.name, 'browser_navigate')
assert.equal(messages[1].tool_call_id, 'call_1')
assert.equal(parseRequestMaxTokens(JSON.stringify({ max_tokens: 30 })), 30)
assert.equal(parseRequestMaxTokens(JSON.stringify({ model: 'x' })), undefined)

const toolCallOnly = JSON.stringify({
  choices: [{
    finish_reason: 'tool_calls',
    message: {
      role: 'assistant',
      content: '',
      reasoning_content: '需要调用工具',
      tool_calls: [{
        id: 'call_2',
        type: 'function',
        function: { name: 'get_stock_fundamentals_unified', arguments: '{"ticker":"688256"}' },
      }],
    },
  }],
})
const toolCallParts = parseResponseParts(toolCallOnly)
assert.equal(toolCallParts.content, '')
assert.equal(toolCallParts.finishReason, 'tool_calls')
assert.match(toolCallParts.toolCalls, /get_stock_fundamentals_unified/)
assert.match(toolCallParts.warnings[0], /工具调用/)

await writeFile(join(outdir, 'logParsing.test.ok'), 'ok')
