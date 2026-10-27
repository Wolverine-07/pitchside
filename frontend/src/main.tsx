import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import OverlayFeed from './OverlayFeed.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {location.pathname === '/overlay' ? <OverlayFeed /> : <App />}
  </StrictMode>,
)
