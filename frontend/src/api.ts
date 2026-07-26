import axios, { AxiosError } from 'axios'

// 同源调用 FastAPI（开发模式由 vite proxy /api → backend:8000）
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

export type ParserEngine = string

export interface ParserEngineInfo {
  name: string
  description: string
  available: boolean
  unavailable_reason: string
  file_types: string[]
}

export interface ParserEnginesResponse {
  uploadable_file_types: string[]
  engines: ParserEngineInfo[]
}

export interface DocumentUploadResponse {
  doc_id: string
  status: string
  original_filename: string
  parser_engine: string
}

export interface DocumentStatusResponse {
  doc_id: string
  status: string
  original_filename: string
  error_message: string
  error_code: string | null
  parser_engine: string
  parse_metadata: Record<string, unknown>
  warnings: string[]
  processed_at: string | null
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

/** 从 axios/业务错误中提取可读消息。 */
export function extractErrorMessage(error: unknown, fallback = '请求失败'): string {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<ApiResponse<unknown>>
    const payload = axiosError.response?.data
    if (payload && typeof payload === 'object' && 'message' in payload && payload.message) {
      return String(payload.message)
    }
    if (axiosError.message) {
      return axiosError.message
    }
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
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

/** 创建默认配置知识库，供联调页空状态使用。 */
export async function createKB(token: string, name: string): Promise<KBInfo> {
  const res = await api.post<ApiResponse<KBInfo>>(
    '/v1/kb',
    { name },
    { headers: { Authorization: `Bearer ${token}` } },
  )
  return res.data.data
}

/** 查询各解析引擎可用性与可实际上传的文档格式。 */
export async function listParserEngines(token: string): Promise<ParserEnginesResponse> {
  const res = await api.get<ApiResponse<ParserEnginesResponse>>('/v1/parsers/engines', {
    headers: { Authorization: `Bearer ${token}` },
  })
  return res.data.data
}

/** 上传文档并入队异步解析。 */
export async function uploadDocument(
  token: string,
  kbId: number,
  file: File,
  parserEngine: ParserEngine,
): Promise<DocumentUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('parser_engine', parserEngine)
  const res = await api.post<ApiResponse<DocumentUploadResponse>>(
    `/v1/kb/${kbId}/documents`,
    formData,
    {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 120000,
    },
  )
  return res.data.data
}

/** 查询文档处理状态。 */
export async function getDocumentStatus(
  token: string,
  kbId: number,
  docId: string,
): Promise<DocumentStatusResponse> {
  const res = await api.get<ApiResponse<DocumentStatusResponse>>(
    `/v1/kb/${kbId}/documents/${docId}`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  )
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
