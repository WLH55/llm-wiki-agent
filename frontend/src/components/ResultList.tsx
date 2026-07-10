import { ChunkHit } from '../api'

interface Props {
  results: ChunkHit[]
}

export default function ResultList({ results }: Props) {
  if (results.length === 0) {
    return <div className="text-gray-500 text-center py-8">暂无结果</div>
  }

  return (
    <div className="space-y-3">
      {results.map((hit, idx) => (
        <div key={hit.chunk_id} className="bg-white p-4 rounded shadow-sm border">
          <div className="flex justify-between items-center mb-2">
            <div className="text-sm text-gray-500">
              #{idx + 1} · 来源 doc_id: <code className="text-xs">{hit.doc_id}</code>
            </div>
            <div className="flex gap-2 text-xs">
              <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                score: {hit.score.toFixed(4)}
              </span>
              <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                {hit.rank_source}
              </span>
            </div>
          </div>
          <div className="text-gray-800 whitespace-pre-wrap">{hit.text}</div>
        </div>
      ))}
    </div>
  )
}
