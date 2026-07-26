import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { FileText, Search } from 'lucide-react'

import DocumentsPage from './pages/Documents'
import SearchPage from './pages/Search'

/** 应用壳：主导航 + 页面路由。 */
export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-brand">
          <span className="app-brand-mark">LW</span>
          <div>
            <p className="app-brand-title">LLM Wiki 3.0</p>
            <p className="app-brand-subtitle">文档上传联调</p>
          </div>
        </div>
        <nav className="app-nav" aria-label="主导航">
          <NavLink
            to="/documents"
            className={({ isActive }) => `app-nav-link${isActive ? ' is-active' : ''}`}
          >
            <FileText size={16} aria-hidden="true" />
            文档解析
          </NavLink>
          <NavLink
            to="/search"
            className={({ isActive }) => `app-nav-link${isActive ? ' is-active' : ''}`}
          >
            <Search size={16} aria-hidden="true" />
            知识检索
          </NavLink>
        </nav>
      </header>
      <div className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/documents" replace />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/search" element={<SearchPage />} />
        </Routes>
      </div>
    </div>
  )
}
