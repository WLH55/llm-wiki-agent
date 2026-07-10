import { Routes, Route, Navigate } from 'react-router-dom'
import SearchPage from './pages/Search'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/search" replace />} />
      <Route path="/search" element={<SearchPage />} />
    </Routes>
  )
}
