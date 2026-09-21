// 应用外壳：顶栏路由 + 全局布局
import { useEffect, useState } from 'react'
import { HashRouter, Link, useLocation } from 'react-router-dom'
import useSWR from 'swr'
import { api } from './lib/api'
import { cn } from './lib/utils'
import { Workbench } from './pages/Workbench'
import { KnowledgePage } from './pages/KnowledgePage'
import { BoardPage } from './pages/BoardPage'

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
        {loc.pathname.startsWith('/knowledge') ? (
          <KnowledgePage />
        ) : loc.pathname.startsWith('/board') ? (
          <BoardPage />
        ) : (
          <Workbench />
        )}
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
    { to: '/', label: '工作台' },
    { to: '/board', label: '流转看板' },
    { to: '/knowledge', label: '知识库' },
  ]

  return (
    <header className="h-12 shrink-0 border-b border-border bg-surface-elevated flex items-stretch px-5">
      <Link to="/" className="flex items-center gap-2.5 pr-6 mr-2 border-r border-border group">
        <span className="font-mono text-[16px] font-semibold tracking-tight text-text group-hover:text-primary-dark transition-colors leading-none">
          12345
        </span>
        <span className="flex flex-col leading-none">
          <span className="text-[13px] font-semibold">热线工单智能体</span>
          <span className="text-[10px] text-muted-light mt-1">芜湖 · 政务服务便民热线</span>
        </span>
      </Link>

      <nav className="flex items-stretch -mb-px">
        {tabs.map((t) => {
          const active = t.to === '/'
            ? !route.startsWith('/knowledge') && !route.startsWith('/board')
            : route.startsWith(t.to)
          return (
            <Link
              key={t.to}
              to={t.to}
              className={cn(
                'inline-flex items-center px-4 text-[13px] border-b-2 transition-colors',
                active
                  ? 'border-primary text-text font-semibold'
                  : 'border-transparent text-muted hover:text-text-secondary hover:border-border-strong',
              )}
            >
              {t.label}
            </Link>
          )
        })}
      </nav>

      <div className="ml-auto flex items-center gap-1.5 text-xs text-muted">
        <span className={'h-1.5 w-1.5 rounded-full ' + (up ? 'bg-success' : 'bg-danger animate-pulse-dot')} />
        <span className="text-[11px]">{up ? '服务正常' : '服务中断'}</span>
      </div>
    </header>
  )
}
