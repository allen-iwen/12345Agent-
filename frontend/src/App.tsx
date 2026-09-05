// 应用外壳：顶栏路由 + 全局布局
import { useEffect, useState } from 'react'
import { HashRouter, Link, useLocation } from 'react-router-dom'
import { Activity, BookOpen, LayoutDashboard } from 'lucide-react'
import useSWR from 'swr'
import { api } from './lib/api'
import { cn } from './lib/utils'
import { Workbench } from './pages/Workbench'
import { KnowledgePage } from './pages/KnowledgePage'

export default function App() {
  return (
    <HashRouter>
      <Shell />
    </HashRouter>
  )
}

function Shell() {
  const loc = useLocation()
  return (
    <div className="h-full flex flex-col">
      <TopBar route={loc.pathname} />
      <div className="flex-1 min-h-0">
        {loc.pathname.startsWith('/knowledge') ? <KnowledgePage /> : <Workbench />}
      </div>
    </div>
  )
}

function TopBar({ route }: { route: string }) {
  const { data: health } = useSWR(['health'], () => api.health(), { refreshInterval: 10000 })
  const [up, setUp] = useState(true)
  useEffect(() => {
    setUp(health?.status === 'ok')
  }, [health])

  const tabs = [
    { to: '/', label: '工作台', icon: LayoutDashboard },
    { to: '/knowledge', label: '知识库', icon: BookOpen },
  ]

  return (
    <header className="h-12 shrink-0 border-b border-border bg-surface-elevated flex items-center gap-4 px-4">
      <Link to="/" className="flex items-center gap-2.5 group">
        <span className="h-7 w-7 rounded-lg bg-primary text-white text-[11px] font-bold flex items-center justify-center shadow-sm">
          12345
        </span>
        <span className="text-sm font-semibold group-hover:text-primary transition-colors">热线工单智能体</span>
      </Link>

      <nav className="flex items-center gap-1 ml-4">
        {tabs.map((t) => {
          const active = t.to === '/' ? !route.startsWith('/knowledge') : route.startsWith(t.to)
          return (
            <Link
              key={t.to}
              to={t.to}
              className={cn(
                'inline-flex items-center gap-1.5 h-8 px-3 rounded-md text-[13px] font-medium transition-colors',
                active ? 'bg-primary-subtle text-primary-dark' : 'text-muted hover:bg-surface-hover hover:text-text',
              )}
            >
              <t.icon className="h-3.5 w-3.5" />
              {t.label}
            </Link>
          )
        })}
      </nav>

      <div className="ml-auto flex items-center gap-2 text-xs text-muted">
        <Activity className={'h-3.5 w-3.5 ' + (up ? 'text-success' : 'text-danger')} />
        <span className="font-mono">{up ? 'API 正常' : 'API 离线'}</span>
      </div>
    </header>
  )
}
