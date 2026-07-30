import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

const apiMocks = vi.hoisted(() => ({
  listKBs: vi.fn(),
  login: vi.fn(),
  createKB: vi.fn(),
  uploadDocument: vi.fn(),
  getDocumentStatus: vi.fn(),
  listParserEngines: vi.fn(),
  isUnauthorizedError: vi.fn(),
}))

vi.mock('./api', () => ({
  listKBs: apiMocks.listKBs,
  login: apiMocks.login,
  createKB: apiMocks.createKB,
  uploadDocument: apiMocks.uploadDocument,
  getDocumentStatus: apiMocks.getDocumentStatus,
  listParserEngines: apiMocks.listParserEngines,
  isUnauthorizedError: apiMocks.isUnauthorizedError,
  extractErrorMessage: (error: unknown, fallback = '请求失败') =>
    error instanceof Error ? error.message : fallback,
}))

describe('App', () => {
  beforeEach(() => {
    localStorage.setItem('llm_wiki_jwt', 'token')
    apiMocks.listKBs.mockResolvedValue([
      { id: 7, name: 'Parser Lab', embedding_model: 'unused', embedding_dim: 1024 },
    ])
    apiMocks.uploadDocument.mockResolvedValue({
      doc_id: '11111111-1111-1111-1111-111111111111',
      status: 'pending',
      original_filename: 'notes.md',
      parser_engine: 'builtin',
    })
    apiMocks.getDocumentStatus.mockResolvedValue({
      doc_id: '11111111-1111-1111-1111-111111111111',
      status: 'processed',
      original_filename: 'notes.md',
      error_message: '',
      error_code: null,
      parser_engine: 'builtin',
      parse_metadata: { format: 'markdown' },
      warnings: [],
      processed_at: '2026-07-26T00:00:00Z',
    })
    apiMocks.listParserEngines.mockResolvedValue({
      uploadable_file_types: ['md', 'pdf'],
      engines: [
        {
          name: 'builtin',
          description: '内置解析引擎',
          available: true,
          unavailable_reason: '',
          file_types: ['md', 'pdf'],
        },
        {
          name: 'markitdown',
          description: 'MarkItDown',
          available: false,
          unavailable_reason: 'markitdown 未安装',
          file_types: ['pdf'],
        },
      ],
    })
  })

  afterEach(() => {
    cleanup()
    localStorage.clear()
    vi.resetAllMocks()
  })

  it('renders navigation and the document upload workspace at /documents', async () => {
    render(
      <MemoryRouter
        initialEntries={['/documents']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: '文档上传联调' })).toBeDefined()
    expect(screen.getByRole('link', { name: /文档解析/ })).toBeDefined()
    expect(screen.getByRole('link', { name: /知识检索/ })).toBeDefined()
    expect(await screen.findByRole('option', { name: 'Parser Lab' })).toBeDefined()
  })

  it('re-authenticates when the stored token is rejected', async () => {
    const unauthorized = new Error('Could not validate credentials')
    apiMocks.listKBs.mockRejectedValueOnce(unauthorized).mockResolvedValueOnce([
      { id: 8, name: 'Fresh KB', embedding_model: 'unused', embedding_dim: 1024 },
    ])
    apiMocks.listParserEngines.mockRejectedValueOnce(unauthorized).mockResolvedValueOnce({
      uploadable_file_types: [],
      engines: [],
    })
    apiMocks.isUnauthorizedError.mockReturnValue(true)
    apiMocks.login.mockResolvedValue({ access_token: 'fresh-token' })

    render(
      <MemoryRouter initialEntries={['/documents']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('option', { name: 'Fresh KB' })).toBeDefined()
    expect(apiMocks.login).toHaveBeenCalledWith('owner@local', 'change-me')
    expect(localStorage.getItem('llm_wiki_jwt')).toBe('fresh-token')
    expect(apiMocks.listKBs).toHaveBeenLastCalledWith('fresh-token')
  })

  it('uploads a document and renders the processed status', async () => {
    render(
      <MemoryRouter
        initialEntries={['/documents']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>,
    )
    await screen.findByRole('option', { name: 'Parser Lab' })
    const file = new File(['# source'], 'notes.md', { type: 'text/markdown' })
    fireEvent.change(screen.getByLabelText('选择文档'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: '开始上传' }))
    await waitFor(() => {
      expect(apiMocks.uploadDocument).toHaveBeenCalledWith('token', 7, file, 'builtin')
    })
    await waitFor(() => {
      expect(apiMocks.getDocumentStatus).toHaveBeenCalledWith(
        'token',
        7,
        '11111111-1111-1111-1111-111111111111',
      )
    })
    const statusNode = await screen.findByTestId('document-status')
    expect(statusNode.textContent).toBe('processed')
    expect(screen.getByText('markdown')).toBeDefined()
    expect(screen.getByText('11111111-1111-1111-1111-111111111111')).toBeDefined()
  })

  it('creates a default knowledge base when none exist', async () => {
    apiMocks.listKBs.mockReset()
    apiMocks.createKB.mockReset()
    apiMocks.listKBs.mockResolvedValue([])
    apiMocks.createKB.mockResolvedValue({
      id: 9,
      name: 'Parser Lab',
      embedding_model: 'BAAI/bge-m3',
      embedding_dim: 1024,
    })
    render(
      <MemoryRouter
        initialEntries={['/documents']}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByText('还没有知识库，先创建一个测试库。')).toBeDefined()
    fireEvent.click(screen.getByTestId('create-kb-button'))
    await waitFor(() => {
      expect(apiMocks.createKB).toHaveBeenCalledWith('token', 'Parser Lab')
    })
    expect(await screen.findByRole('option', { name: 'Parser Lab' })).toBeDefined()
  })
})
