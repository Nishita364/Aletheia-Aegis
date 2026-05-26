import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

// Keep the Render backend alive by pinging it every 14 minutes.
// Render free tier sleeps after 15 minutes of inactivity.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
function keepAlive() {
  fetch(`${API_BASE}/api/v1/health`).catch(() => {})
}
keepAlive() // ping immediately on load
setInterval(keepAlive, 14 * 60 * 1000) // then every 14 minutes

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
