import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@arco-design/web-react/dist/css/arco.css'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
