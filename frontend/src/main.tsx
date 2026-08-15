import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <BrowserRouter>
    {/* P5-5: ErrorBoundary 挂载到路由层 — 此前从未挂载, 渲染错误直接白屏 */}
    <ErrorBoundary title="页面渲染失败">
      <App />
    </ErrorBoundary>
  </BrowserRouter>,
)
