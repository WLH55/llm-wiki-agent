import { FormEvent, useEffect, useRef, useState } from 'react'
import { AlertCircle, FileUp, Loader2, Plus, Upload } from 'lucide-react'

import {
  DocumentStatusResponse,
  DocumentUploadResponse,
  KBInfo,
  ParserEngine,
  ParserEngineInfo,
  createKB,
  extractErrorMessage,
  getDocumentStatus,
  listKBs,
  listParserEngines,
  login,
  uploadDocument,
} from '../api'

const TOKEN_KEY = 'llm_wiki_jwt'
const EMAIL_DEFAULT = 'owner@local'
const PWD_DEFAULT = 'change-me'
const DEFAULT_KB_NAME = 'Parser Lab'
const POLL_INTERVAL_MS = 1500
const POLL_MAX_ATTEMPTS = 80

/** 文档真实上传联调页：上传后轮询处理状态。 */
export default function DocumentsPage() {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || '')
  const [kbs, setKbs] = useState<KBInfo[]>([])
  const [kbId, setKbId] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [engines, setEngines] = useState<ParserEngineInfo[]>([])
  const [uploadableFileTypes, setUploadableFileTypes] = useState<string[]>([])
  const [engine, setEngine] = useState<ParserEngine>('builtin')
  const [upload, setUpload] = useState<DocumentUploadResponse | null>(null)
  const [status, setStatus] = useState<DocumentStatusResponse | null>(null)
  const [bootstrapping, setBootstrapping] = useState(true)
  const [creatingKb, setCreatingKb] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const pollTokenRef = useRef(0)

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
        const results = await Promise.allSettled([
          listKBs(activeToken),
          listParserEngines(activeToken),
        ])
        const [kbResult, engineResult] = results
        if (kbResult.status === 'fulfilled') {
          setKbs(kbResult.value)
          setKbId(kbResult.value[0]?.id ?? null)
        }
        if (engineResult.status === 'fulfilled') {
          setEngines(engineResult.value.engines)
          setUploadableFileTypes(engineResult.value.uploadable_file_types)
        }
        const failed = results.find((result) => result.status === 'rejected') as
          | PromiseRejectedResult
          | undefined
        if (failed) {
          setError(extractErrorMessage(failed.reason, '初始化失败'))
        }
      } catch (requestError) {
        setError(extractErrorMessage(requestError, '初始化失败'))
      } finally {
        setBootstrapping(false)
      }
    }
    void bootstrap()
    // 仅首屏初始化
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (engines.length === 0) return
    const current = engines.find((candidate) => candidate.name === engine)
    if (current && current.available) return
    const fallback =
      engines.find((candidate) => candidate.name === 'builtin' && candidate.available) ??
      engines.find((candidate) => candidate.available)
    if (fallback) {
      setEngine(fallback.name)
    }
  }, [engines, engine])

  useEffect(() => {
    return () => {
      pollTokenRef.current += 1
    }
  }, [])

  /** 空状态下创建默认测试知识库。 */
  async function handleCreateKb() {
    if (!token) return
    setCreatingKb(true)
    setError('')
    try {
      const created = await createKB(token, DEFAULT_KB_NAME)
      const nextList = [created, ...kbs]
      setKbs(nextList)
      setKbId(created.id)
    } catch (requestError) {
      setError(extractErrorMessage(requestError, '创建知识库失败'))
    } finally {
      setCreatingKb(false)
    }
  }

  /** 轮询文档状态直到终态或超时。 */
  async function pollDocumentStatus(
    activeToken: string,
    activeKbId: number,
    docId: string,
    pollToken: number,
  ): Promise<DocumentStatusResponse> {
    let last: DocumentStatusResponse | null = null
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt += 1) {
      if (pollToken !== pollTokenRef.current) {
        throw new Error('轮询已取消')
      }
      last = await getDocumentStatus(activeToken, activeKbId, docId)
      setStatus(last)
      if (last.status === 'processed' || last.status === 'failed') {
        return last
      }
      await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
    }
    throw new Error(
      last
        ? `处理超时，最后状态: ${last.status}`
        : '处理超时，未能获取文档状态',
    )
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!token || kbId === null || file === null) return
    const pollToken = pollTokenRef.current + 1
    pollTokenRef.current = pollToken
    setLoading(true)
    setError('')
    setUpload(null)
    setStatus(null)
    try {
      const uploaded = await uploadDocument(token, kbId, file, engine)
      setUpload(uploaded)
      setStatus({
        doc_id: uploaded.doc_id,
        status: uploaded.status,
        original_filename: uploaded.original_filename,
        error_message: '',
        error_code: null,
        parser_engine: uploaded.parser_engine,
        parse_metadata: {},
        warnings: [],
        processed_at: null,
      })
      await pollDocumentStatus(token, kbId, uploaded.doc_id, pollToken)
    } catch (requestError) {
      if (pollToken === pollTokenRef.current) {
        setError(extractErrorMessage(requestError, '上传或处理失败'))
      }
    } finally {
      if (pollToken === pollTokenRef.current) {
        setLoading(false)
      }
    }
  }

  const selectedEngineInfo = engines.find((candidate) => candidate.name === engine)
  const hasAvailableEngine = engines.some((candidate) => candidate.available)
  const engineHint = bootstrapping
    ? '正在加载支持格式…'
    : selectedEngineInfo
      ? `当前引擎支持: ${selectedEngineInfo.file_types.join(', ') || '无'}`
      : '暂无可用解析引擎'
  const canSubmit = !loading && !bootstrapping && !!file && kbId !== null && hasAvailableEngine
  const display = status
  const statusClass =
    display?.status === 'processed'
      ? 'is-success'
      : display?.status === 'failed'
        ? 'is-danger'
        : 'is-pending'

  return (
    <main className="page-panel">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Document Upload</p>
          <h1>文档上传联调</h1>
          <p className="page-desc">
            调用正式上传接口：写 MinIO、创建 Document、入队 Worker 异步解析。
          </p>
        </div>
        <div className="hero-badge">
          <Upload size={16} aria-hidden="true" />
          真实上传链路
        </div>
      </section>

      <section className="workbench-grid">
        <form className="card stack-form" onSubmit={handleSubmit}>
          <div className="card-header">
            <h2>请求参数</h2>
            <p>选择知识库、本地文件与解析引擎后发起上传。</p>
          </div>

          <label className="field">
            <span>知识库</span>
            {kbs.length > 0 ? (
              <select
                value={kbId ?? ''}
                onChange={(event) => setKbId(Number(event.target.value))}
                disabled={bootstrapping || loading}
              >
                {kbs.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}
                  </option>
                ))}
              </select>
            ) : (
              <div className="empty-inline">
                <p>{bootstrapping ? '正在加载知识库…' : '还没有知识库，先创建一个测试库。'}</p>
                <button
                  type="button"
                  className="btn btn-secondary"
                  data-testid="create-kb-button"
                  onClick={() => void handleCreateKb()}
                  disabled={bootstrapping || creatingKb || !token}
                >
                  {creatingKb ? (
                    <Loader2 className="spin" size={16} aria-hidden="true" />
                  ) : (
                    <Plus size={16} aria-hidden="true" />
                  )}
                  {creatingKb ? '创建中' : `创建 ${DEFAULT_KB_NAME}`}
                </button>
              </div>
            )}
          </label>

          <label className="field">
            <span>选择文档</span>
            <input
              type="file"
              aria-label="选择文档"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              disabled={loading}
            />
            <small className="field-hint">
              {file ? `${file.name} · ${(file.size / 1024).toFixed(1)} KB` : engineHint}
            </small>
            {uploadableFileTypes.length > 0 && (
              <small className="field-hint muted">
                全站可上传: {uploadableFileTypes.join(', ')}
              </small>
            )}
          </label>

          <label className="field">
            <span>解析引擎</span>
            <select
              value={engine}
              onChange={(event) => setEngine(event.target.value as ParserEngine)}
              disabled={loading || bootstrapping || engines.length === 0}
              aria-label="解析引擎"
            >
              {engines.map((item) => (
                <option key={item.name} value={item.name} disabled={!item.available}>
                  {(item.description || item.name) + (item.available ? '' : '（不可用）')}
                </option>
              ))}
            </select>
            {selectedEngineInfo && !selectedEngineInfo.available && (
              <small className="field-hint">{selectedEngineInfo.unavailable_reason}</small>
            )}
          </label>

          <button type="submit" className="btn btn-primary" disabled={!canSubmit}>
            {loading ? (
              <Loader2 className="spin" size={16} aria-hidden="true" />
            ) : (
              <FileUp size={16} aria-hidden="true" />
            )}
            {loading ? '处理中' : '开始上传'}
          </button>
        </form>

        <section className="card result-card">
          <div className="card-header">
            <h2>处理结果</h2>
            <p>上传回执、处理状态与 parse metadata。</p>
          </div>

          {error && (
            <div className="alert alert-error" role="alert">
              <AlertCircle size={16} aria-hidden="true" />
              <span>{error}</span>
            </div>
          )}

          {!error && !display && (
            <div className="empty-state">
              <FileUp size={28} aria-hidden="true" />
              <p>选择文件并开始上传后，这里会显示 doc_id 与处理状态。</p>
            </div>
          )}

          {display && (
            <div className="result-stack">
              <div className={`status-pill ${statusClass}`} data-testid="document-status">
                {display.status}
              </div>

              <dl className="meta-grid">
                <div>
                  <dt>doc_id</dt>
                  <dd>{display.doc_id}</dd>
                </div>
                <div>
                  <dt>文件名</dt>
                  <dd>{display.original_filename}</dd>
                </div>
                <div>
                  <dt>引擎</dt>
                  <dd>{display.parser_engine}</dd>
                </div>
                <div>
                  <dt>状态</dt>
                  <dd>{display.status}</dd>
                </div>
                <div>
                  <dt>错误码</dt>
                  <dd>{display.error_code || '-'}</dd>
                </div>
                <div>
                  <dt>错误信息</dt>
                  <dd>{display.error_message || '-'}</dd>
                </div>
                <div>
                  <dt>processed_at</dt>
                  <dd>{display.processed_at || '-'}</dd>
                </div>
                <div>
                  <dt>上传回执</dt>
                  <dd>{upload?.status || '-'}</dd>
                </div>
              </dl>

              {display.warnings.length > 0 && (
                <div className="alert alert-warn">
                  <strong>warnings</strong>
                  <ul>
                    {display.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <h3>parse metadata</h3>
                {Object.keys(display.parse_metadata || {}).length === 0 ? (
                  <p className="muted">无 metadata</p>
                ) : (
                  <dl className="meta-grid">
                    {Object.entries(display.parse_metadata).map(([key, value]) => (
                      <div key={key}>
                        <dt>{key}</dt>
                        <dd>{formatMetaValue(value)}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </div>
            </div>
          )}
        </section>
      </section>
    </main>
  )
}

/** 将 metadata 值格式化为可读字符串。 */
function formatMetaValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}
