import axios from 'axios'

// 同源调用 FastAPI（开发模式由 vite proxy /api → backend:8000；生产模式由 FastAPI StaticFiles 托管，同源）
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in_hours: number
}

export interface KBInfo {
  id: number
  name: string
  embedding_model: string
  embedding_dim: number
}

export interface ChunkHit {
  chunk_id: number
  doc_id: string
  text: string
  score: number
  rank_source: string
}

export interface SearchResponse {
  query: string
  kb_id: number
  mode: string
  total: number
  hits: ChunkHit[]
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await api.post<ApiResponse<TokenResponse>>('/auth/login', { email, password })
  return res.data.data
}

export async function listKBs(token: string): Promise<KBInfo[]> {
  const res = await api.get<ApiResponse<KBInfo[]>>('/v1/kb', {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data.data
}

export async function search(
  token: string,
  kbId: number,
  query: string,
  mode: 'rag' | 'wiki' = 'rag',
  limit: number = 10,
): Promise<SearchResponse> {
  const res = await api.get<ApiResponse<SearchResponse>>(`/v1/kb/${kbId}/search`, {
    headers: { Authorization: `Bearer ${token}` },
    params: { q: query, mode, limit },
  })
  return res.data.data
}
