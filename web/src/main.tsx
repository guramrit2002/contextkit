import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { loadConfig } from './config'

// Render once the runtime config has settled (at most 3 seconds), so App's synchronous
// isConfigured() checks, including the return from GitHub, see the final settings.
void loadConfig().then(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
