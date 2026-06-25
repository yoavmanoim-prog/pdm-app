import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './context/AuthContext'
import './index.css'   // dark theme: design tokens + base element styles

// Entry point — mounts the React app into the <div id="root"> in index.html.
// AuthProvider wraps everything so every page knows who is logged in.
ReactDOM.createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <AuthProvider>
      <App />
    </AuthProvider>
  </BrowserRouter>
)
