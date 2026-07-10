import { useState } from 'react'

interface Props {
  onSearch: (q: string) => void
  loading: boolean
}

export default function SearchBox({ onSearch, loading }: Props) {
  const [query, setQuery] = useState('')

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (query.trim()) {
      onSearch(query.trim())
    }
  }

  return (
    <form onSubmit={submit} className="flex gap-2">
      <input
        type="text"
        className="flex-1 p-3 border rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="输入查询（中文/英文/混合）"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={loading}
      />
      <button
        type="submit"
        className="px-6 py-3 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        disabled={loading || !query.trim()}
      >
        {loading ? '搜索中...' : '搜索'}
      </button>
    </form>
  )
}
