import { Routes, Route, Link } from 'react-router-dom'
import List from './pages/List'
import Upload from './pages/Upload'

// App is the root component — handles navigation between pages
export default function App() {
  return (
    <div style={{ fontFamily: 'sans-serif', maxWidth: '900px', margin: '0 auto', padding: '20px' }}>
      {/* Top navigation bar */}
      <nav style={{ display: 'flex', gap: '20px', marginBottom: '30px', borderBottom: '1px solid #ccc', paddingBottom: '10px' }}>
        <strong>PDM — Mechanic Schematics</strong>
        <Link to="/">Browse</Link>
        <Link to="/upload">Upload</Link>
      </nav>

      {/* Routes define which page to show based on the URL */}
      <Routes>
        <Route path="/" element={<List />} />
        <Route path="/upload" element={<Upload />} />
      </Routes>
    </div>
  )
}
