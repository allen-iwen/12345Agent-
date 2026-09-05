// 应用外壳：顶栏路由 + 全局布局
import { useEffect, useState } from 'react'
import { HashRouter, Link, useLocation } from 'react-router-dom'
import { BookOpen, LayoutDashboard } from 'lucide-react'
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
    <header className="h-12 shrink-0 border-b border-border bg-surface-elevated flex items-stretch gap-0 px-4">
      <Link to="/" className="flex items-center gap-2.5 group pr-5">
        <span className="h-6 px-1.5 rounded-sm bg-primary text-white text-[10px] font-semibold flex items-center justify-center tracking-tight">
          12345
        </span>
        <span className="flex flex-col leading-none">
          <span className="text-[13px] font-semibold group-hover:text-primary transition-colors">热线工单智能体</span>
          <span className="text-[10px] text-muted-light mt-1">芜湖 · 政务服务便民热线</span>
        </span>
      </Link>

      <nav className="flex items-stretch -mb-px">
        {tabs.map((t) => {
          const active = t.to === '/' ? !route.startsWith('/knowledge') : route.startsWith(t.to)
          return (
            <Link
              key={t.to}
              to={t.to}
              className={cn(
                'inline-flex items-center gap-1.5 px-4 text-[13px] font-medium border-b-2 transition-colors',
                active
                  ? 'border-primary text-primary-dark'
                  : 'border-transparent text-muted hover:text-text hover:border-border-strong',
              )}
            >
              <t.icon className="h-3.5 w-3.5" />
              {t.label}
            </Link>
          )
        })}
      </nav>

      <div className="ml-auto flex items-center gap-2 text-xs text-muted">
        <span className={'h-1.5 w-1.5 rounded-full ' + (up ? 'bg-success' : 'bg-danger animate-pulse-dot')} />
        <span className="font-mono text-[11px]">{up ? 'SERVICE ONLINE' : 'SERVICE OFFLINE'}</span>
      </div>
    </header>
  )
}
