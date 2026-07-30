import { useEffect, useState } from 'react'
import { Search as SearchIcon } from 'lucide-react'

import SearchBox from '../components/SearchBox'
import ResultList from '../components/ResultList'
import {
  ChunkHit,
  KBInfo,
  extractErrorMessage,
  isUnauthorizedError,
  listKBs,
  login,
  search,
} from '../api'

const TOKEN_KEY = 'llm_wiki_jwt'
const EMAIL_DEFAULT = 'owner@local'
const PWD_DEFAULT = 'change-me'

/** 知识检索页：复用现有 search API，适配应用壳层布局。 */
export default function SearchPage() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) || '')
  const [kbs, setKBs] = useState<KBInfo[]>([])
  const [selectedKb, setSelectedKb] = useState<number | null>(null)
  const [results, setResults] = useState<ChunkHit[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  useEffect(() => {
    async function bootstrap() {
      try {
        let activeToken = token
        if (!activeToken) {
          const response = await login(EMAIL_DEFAULT, PWD_DEFAULT)
          activeToken = response.access_token
          localStorage.setItem(TOKEN_KEY, activeToken)
          setToken(activeToken)
        }
        let kbList: KBInfo[]
        try {
          kbList = await listKBs(activeToken)
        } catch (requestError) {
          if (!isUnauthorizedError(requestError)) throw requestError
          localStorage.removeItem(TOKEN_KEY)
          const response = await login(EMAIL_DEFAULT, PWD_DEFAULT)
          activeToken = response.access_token
          localStorage.setItem(TOKEN_KEY, activeToken)
          setToken(activeToken)
          kbList = await listKBs(activeToken)
        }
        setKBs(kbList)
        if (kbList.length > 0 && selectedKb === null) {
          setSelectedKb(kbList[0].id)
        }
      } catch (requestError) {
        setError(`初始化失败: ${extractErrorMessage(requestError)}`)
      }
    }
    void bootstrap()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSearch(query: string) {
    if (!token || selectedKb === null) return
    setLoading(true)
    setError('')
    try {
      const response = await search(token, selectedKb, query)
      setResults(response.hits)
    } catch (requestError) {
      setError(`搜索失败: ${extractErrorMessage(requestError)}`)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="page-panel">
      <section className="page-hero">
        <div>
          <p className="eyebrow">Knowledge Search</p>
          <h1>知识检索</h1>
          <p className="page-desc">基于已入库内容的检索联调入口，与解析预览链路隔离。</p>
        </div>
        <div className="hero-badge">
          <SearchIcon size={16} aria-hidden="true" />
          RAG / Wiki
        </div>
      </section>

      <section className="card stack-form">
        <label className="field">
          <span>选择知识库</span>
          <select
            value={selectedKb ?? ''}
            onChange={(event) => setSelectedKb(Number(event.target.value))}
            disabled={loading || kbs.length === 0}
          >
            {kbs.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name} ({kb.embedding_model})
              </option>
            ))}
          </select>
        </label>

        <SearchBox onSearch={handleSearch} loading={loading} />

        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        <div className="search-results">
          <ResultList results={results} />
        </div>
      </section>
    </main>
  )
}
