import { FormEvent, useEffect, useRef, useState } from 'react'
import { BookOpen, Link2, Loader2, MessageSquare, Send } from 'lucide-react'

import {
  ChatCitation,
  KBInfo,
  createKB,
  chatStream,
  extractErrorMessage,
  isUnauthorizedError,
  listKBs,
  login,
} from '../api'

const TOKEN_KEY = 'llm_wiki_jwt'
const EMAIL_DEFAULT = 'owner@local'
const PWD_DEFAULT = 'change-me'
const DEFAULT_KB_NAME = 'Chat Lab'

interface Message {
  role: 'user' | 'assistant'
  content: string
  citations?: ChatCitation[]
  error?: string
  streaming?: boolean
}

/** RAG 智能问答联调页：选 KB -> 提问 -> SSE 流式答案 + 引用卡片。 */
export default function ChatPage() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '')
  const [kbs, setKbs] = useState<KBInfo[]>([])
  const [kbId, setKbId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [bootstrapping, setBootstrapping] = useState(true)
  const [error, setError] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  /** 自动登录 + 加载 KB 列表（与 Documents 页同模式）。 */
  useEffect(() => {
    async function bootstrap() {
      setBootstrapping(true)
      setError('')
      try {
        let activeToken = token
        if (!activeToken) {
          const response = await login(EMAIL_DEFAULT, PWD_DEFAULT)
          activeToken = response.access_token
          localStorage.setItem(TOKEN_KEY, activeToken)
          setToken(activeToken)
        }
        try {
          const kbList = await listKBs(activeToken)
          setKbs(kbList)
          setKbId((previous) => previous ?? kbList[0]?.id ?? null)
        } catch (listError) {
          if (isUnauthorizedError(listError)) {
            localStorage.removeItem(TOKEN_KEY)
            const response = await login(EMAIL_DEFAULT, PWD_DEFAULT)
            activeToken = response.access_token
            localStorage.setItem(TOKEN_KEY, activeToken)
            setToken(activeToken)
            const kbList = await listKBs(activeToken)
            setKbs(kbList)
            setKbId(kbList[0]?.id ?? null)
          } else {
            throw listError
          }
        }
      } catch (bootstrapError) {
        setError(extractErrorMessage(bootstrapError, '初始化失败'))
      } finally {
        setBootstrapping(false)
      }
    }
    void bootstrap()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** 空状态：一键创建默认 KB。 */
  async function handleCreateKb() {
    setError('')
    try {
      const kb = await createKB(token, DEFAULT_KB_NAME)
      setKbs((previous) => [...previous, kb])
      setKbId(kb.id)
    } catch (createError) {
      setError(extractErrorMessage(createError, '创建知识库失败'))
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend(event: FormEvent) {
    event.preventDefault()
    const query = input.trim()
    if (!query || sending || kbId === null) return
    setInput('')
    setSending(true)
    setError('')
    setMessages((previous) => [
      ...previous,
      { role: 'user', content: query },
      { role: 'assistant', content: '', streaming: true },
    ])
    try {
      let answer = ''
      let citations: ChatCitation[] = []
      for await (const eventData of chatStream(token, kbId, query, 5)) {
        if (eventData.type === 'token') {
          answer += eventData.text
          setMessages((previous) => {
            const next = [...previous]
            next[next.length - 1] = { role: 'assistant', content: answer, streaming: true }
            return next
          })
        } else if (eventData.type === 'done') {
          answer = eventData.answer
          citations = eventData.citations
        } else if (eventData.type === 'error') {
          setMessages((previous) => {
            const next = [...previous]
            next[next.length - 1] = {
              role: 'assistant',
              content: answer,
              error: eventData.message,
            }
            return next
          })
        }
      }
      setMessages((previous) => {
        const next = [...previous]
        next[next.length - 1] = {
          role: 'assistant',
          content: answer || '（无答案）',
          citations: citations.length > 0 ? citations : undefined,
        }
        return next
      })
    } catch (streamError) {
      setMessages((previous) => {
        const next = [...previous]
        const last = next[next.length - 1]
        if (last && last.role === 'assistant') {
          next[next.length - 1] = {
            ...last,
            error: extractErrorMessage(streamError, '问答请求失败'),
          }
        }
        return next
      })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="chat-page">
      <div className="chat-toolbar">
        <select
          className="chat-kb-select"
          value={kbId ?? ''}
          onChange={(event) => setKbId(Number(event.target.value))}
          disabled={bootstrapping || kbs.length === 0}
        >
          {kbs.length === 0 && <option value="">暂无知识库</option>}
          {kbs.map((kb) => (
            <option key={kb.id} value={kb.id}>
              {kb.name}（#{kb.id}）
            </option>
          ))}
        </select>
        {!bootstrapping && kbs.length === 0 && (
          <button className="chat-create-btn" type="button" onClick={() => void handleCreateKb()}>
            <BookOpen size={14} aria-hidden="true" />
            创建知识库
          </button>
        )}
        {bootstrapping && <Loader2 size={16} className="spin" aria-hidden="true" />}
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <MessageSquare size={32} aria-hidden="true" />
            <p>向知识库提问，答案将基于检索内容并带引用标注</p>
            <p className="chat-empty-hint">
              示例：embedding 服务不可用时怎么办？
            </p>
          </div>
        )}
        {messages.map((message, index) => (
          <div key={index} className={`chat-message is-${message.role}`}>
            <div className="chat-bubble">
              {message.error && (
                <div className="chat-error">⚠ {message.error}</div>
              )}
              {message.content || (message.streaming ? <span className="chat-cursor" /> : '')}
              {message.citations && message.citations.length > 0 && (
                <div className="chat-citations">
                  <div className="chat-citations-title">
                    <Link2 size={12} aria-hidden="true" /> 引用来源
                  </div>
                  {message.citations.map((citation) => (
                    <div key={citation.id} className="chat-citation">
                      [{citation.id}] {citation.title}
                      <span className="chat-citation-meta">
                        {citation.source} · chunk #{citation.chunk_id}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <form className="chat-input-bar" onSubmit={(event) => void handleSend(event)}>
        <input
          className="chat-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={kbId === null ? '请先创建或选择知识库' : '输入问题，回车发送'}
          disabled={sending || kbId === null}
        />
        <button
          className="chat-send-btn"
          type="submit"
          disabled={sending || kbId === null || input.trim() === ''}
        >
          {sending ? (
            <Loader2 size={16} className="spin" aria-hidden="true" />
          ) : (
            <Send size={16} aria-hidden="true" />
          )}
        </button>
      </form>
      {error && <div className="chat-page-error">{error}</div>}
    </div>
  )
}
