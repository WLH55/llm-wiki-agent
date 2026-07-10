import { useEffect, useState } from 'react'
import SearchBox from '../components/SearchBox'
import ResultList from '../components/ResultList'
import { ChunkHit, KBInfo, listKBs, login, search } from '../api'

const TOKEN_KEY = 'llm_wiki_jwt'
const EMAIL_DEFAULT = 'owner@local'
const PWD_DEFAULT = 'change-me'

export default function SearchPage() {
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) || '')
  const [kbs, setKBs] = useState<KBInfo[]>([])
  const [selectedKb, setSelectedKb] = useState<number | null>(null)
  const [results, setResults] = useState<ChunkHit[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')

  // 首次加载：登录 + 拉取 KB 列表
  useEffect(() => {
    async function bootstrap() {
      try {
        let t = token
        if (!t) {
          const r = await login(EMAIL_DEFAULT, PWD_DEFAULT)
          t = r.access_token
          localStorage.setItem(TOKEN_KEY, t)
          setToken(t)
        }
        const kbList = await listKBs(t)
        setKBs(kbList)
        if (kbList.length > 0 && selectedKb === null) {
          setSelectedKb(kbList[0].id)
        }
      } catch (e: any) {
        setError(`初始化失败: ${e.message}`)
      }
    }
    bootstrap()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleSearch(q: string) {
    if (!token || selectedKb === null) return
    setLoading(true)
    setError('')
    try {
      const res = await search(token, selectedKb, q)
      setResults(res.hits)
    } catch (e: any) {
      setError(`搜索失败: ${e.message}`)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-6">LLM Wiki 3.0 知识检索</h1>

        <div className="mb-4">
          <label className="block text-sm text-gray-600 mb-1">选择知识库</label>
          <select
            className="w-full p-2 border rounded"
            value={selectedKb ?? ''}
            onChange={(e) => setSelectedKb(Number(e.target.value))}
          >
            {kbs.map((kb) => (
              <option key={kb.id} value={kb.id}>
                {kb.name} ({kb.embedding_model})
              </option>
            ))}
          </select>
        </div>

        <SearchBox onSearch={handleSearch} loading={loading} />

        {error && <div className="mt-4 text-red-600">{error}</div>}

        <div className="mt-6">
          <ResultList results={results} />
        </div>
      </div>
    </div>
  )
}
