// 知识库：官方 18 条历史工单浏览（BM25 检索的底料，评委可查验数据来源）
import { useRef, useState } from 'react'
import useSWR from 'swr'
import { BarChart3, BookOpen, FileUp, Library, Loader2, Search, Trash2 } from 'lucide-react'
import { api } from '../lib/api'
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Spinner } from '../ui'

export function KnowledgePage() {
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const { data: cats } = useSWR(['cats'], () => api.listOrders().then((r) => {
    const set = new Map<string, number>()
    r.orders.forEach((o) => set.set(o.category, (set.get(o.category) ?? 0) + 1))
    return Array.from(set.entries())
  }))
  const { data, isLoading } = useSWR(
    ['kb', q, category],
    () => api.listOrders(q, category),
  )
  const { data: stats } = useSWR(['stats'], () => api.stats())

  return (
    <div className="max-w-[1080px] mx-auto p-5">
      <header className="mb-5">
        <div className="flex items-center gap-2">
          <BookOpen className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold">知识库 · 官方历史工单</h1>
        </div>
        <p className="text-sm text-muted mt-1">
          赛题数据集清洗后的 {data?.total ?? '…'} 条标准化工单——智能体分类、转派、答复的检索底料。
        </p>
      </header>

      {/* 过滤栏 */}
      <div className="flex flex-wrap gap-2 mb-4">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-light" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜索标题 / 诉求 / 答复…"
            className="w-full h-9 text-sm rounded-md border border-border bg-surface-elevated pl-8 pr-3 focus:outline-none focus:border-primary"
          />
        </div>
        <button
          onClick={() => setCategory('')}
          className={'h-9 px-3 rounded-md text-xs font-medium border transition-colors ' +
            (!category ? 'bg-primary text-white border-transparent' : 'bg-surface-elevated border-border text-muted hover:border-primary')}
        >
          全部
        </button>
        {(cats ?? []).map(([name, count]) => (
          <button
            key={name}
            onClick={() => setCategory(name === category ? '' : name)}
            className={'h-9 px-3 rounded-md text-xs font-medium border transition-colors whitespace-nowrap ' +
              (name === category ? 'bg-primary text-white border-transparent' : 'bg-surface-elevated border-border text-muted hover:border-primary')}
          >
            {name} <span className="opacity-60">{count}</span>
          </button>
        ))}
      </div>

      {/* 热点统计 */}
      {stats && <StatsPanel stats={stats} />}

      {/* 政策依据库 */}
      <PolicyPanel />

      {/* 列表 */}
      {isLoading && (
        <div className="flex items-center gap-2 text-muted text-sm py-10 justify-center">
          <Spinner /> 加载…
        </div>
      )}
      <div className="space-y-3">
        {data?.orders.map((o) => (
          <Card key={o.source_id}>
            <CardBody className="space-y-2.5">
              <div className="flex items-start gap-2">
                <Badge tone="primary" className="shrink-0 mt-0.5">{o.category}</Badge>
                <span className="text-sm font-semibold leading-snug flex-1">{o.title}</span>
                <span className="text-[10px] font-mono text-muted-light shrink-0">{o.source_id}</span>
              </div>
              <div className="flex flex-wrap gap-1.5 text-[11px] text-muted">
                {o.region && <span className="bg-surface-hover rounded px-1.5 py-0.5">{o.region}</span>}
                {o.source_channel && <span className="bg-surface-hover rounded px-1.5 py-0.5">{o.source_channel}</span>}
                {o.handling_departments.map((d) => (
                  <span key={d} className="bg-info-subtle text-info rounded px-1.5 py-0.5">{d}</span>
                ))}
              </div>
              <Expandable label="群众诉求" text={o.request_content} />
              <Expandable label="官方答复" text={o.reply_content} />
            </CardBody>
          </Card>
        ))}
        {data && data.orders.length === 0 && (
          <div className="text-sm text-muted text-center py-10">无匹配记录</div>
        )}
      </div>
    </div>
  )
}

function PolicyPanel() {
  const { data, mutate, isLoading } = useSWR(['policies'], () => api.listPolicies())
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const upload = async (f: File) => {
    setBusy(true); setMsg(''); setErr('')
    try {
      const defaultName = f.name.replace(/\.[^.]+$/, '')
      const sourceName = (prompt('政策文件正式名称（引用时显示）', defaultName) || '').trim()
      if (!sourceName) { setBusy(false); return }
      const publisher = (prompt('发布单位', '芜湖市人民政府') || '').trim()
      const r = await api.uploadPolicy(f, sourceName, publisher, '综合')
      setMsg(`✓ 已入库「${r.source_name}」，切分 ${r.chunks} 块并完成向量索引`)
      mutate()
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const del = async (id: string, name: string) => {
    if (!confirm(`删除「${name}」及其全部向量？`)) return
    try { await api.deletePolicy(id); mutate() } catch (e) { setErr(String(e)) }
  }

  const docs = data?.documents ?? []
  return (
    <Card className="mb-4">
      <CardHeader>
        <Library className="h-4 w-4 text-primary" />
        <CardTitle>政策依据库（RAG）</CardTitle>
        <span className="text-[11px] text-muted ml-auto">8 份精选法规 + 上传文档，语义检索进答复引用</span>
      </CardHeader>
      <CardBody className="space-y-2.5">
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.txt,.md,.json"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) upload(f) }}
          />
          <Button size="sm" onClick={() => fileRef.current?.click()} disabled={busy}>
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileUp className="h-3.5 w-3.5" />}
            上传政策文件
          </Button>
          <span className="text-[11px] text-muted">PDF / DOCX / TXT / MD / JSON，≤20MB，自动切分 + 向量入库</span>
        </div>
        {msg && <div className="text-xs text-success">{msg}</div>}
        {err && <div className="text-xs text-danger bg-danger-subtle rounded p-2">{err}</div>}
        {isLoading ? <Spinner /> : docs.length === 0 ? (
          <div className="text-xs text-muted">暂无上传文档；内置 8 份国家层面公开法规已就绪。</div>
        ) : (
          <div className="divide-y divide-border rounded-md border border-border">
            {docs.map((d) => (
              <div key={d.upload_id} className="flex items-center gap-2 px-3 py-2">
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-medium text-text-primary truncate" title={d.source_name}>{d.source_name}</div>
                  <div className="text-[10px] text-muted">
                    {d.publisher} · {d.category_name} · {d.chunks} 块 / {d.chars} 字 · {d.indexed_at}
                  </div>
                </div>
                <button onClick={() => del(d.upload_id, d.source_name)} className="text-muted hover:text-danger transition-colors shrink-0" title="删除">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

function StatsPanel({ stats }: { stats: import('../lib/api').StatsView }) {
  const all = new Set([...Object.keys(stats.official_by_category), ...Object.keys(stats.demo_by_category)])
  const maxOfficial = Math.max(1, ...Object.values(stats.official_by_category))
  const maxDemo = Math.max(1, ...Object.values(stats.demo_by_category))
  return (
    <Card className="mb-4">
      <CardHeader>
        <BarChart3 className="h-4 w-4 text-primary" />
        <CardTitle>热点问题统计</CardTitle>
        <span className="text-[11px] text-muted ml-auto">
          官方样例 {stats.official_total} 条 · 本系统受理 {stats.demo_total} 件（紧急 {stats.demo_urgent} / 重复 {stats.demo_repeat} / 已归档 {stats.demo_completed}）
        </span>
      </CardHeader>
      <CardBody className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-1">
        {Array.from(all).map((cat) => {
          const o = stats.official_by_category[cat] ?? 0
          const d = stats.demo_by_category[cat] ?? 0
          return (
            <div key={cat} className="flex items-center gap-2 py-0.5">
              <span className="text-xs text-text-secondary w-24 shrink-0 truncate" title={cat}>{cat}</span>
              <div className="flex-1 h-3.5 bg-surface rounded overflow-hidden flex" title={`官方 ${o} / 受理 ${d}`}>
                <div className="h-full bg-primary/70" style={{ width: `${(o / maxOfficial) * 100}%` }} />
                <div className="h-full bg-warning/70" style={{ width: `${(d / maxDemo) * 100}%` }} />
              </div>
              <span className="text-[10px] font-mono text-muted w-10 text-right shrink-0">{o}/{d}</span>
            </div>
          )
        })}
        <div className="col-span-full flex gap-4 text-[10px] text-muted mt-1.5">
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-primary/70" />官方样例分布</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-warning/70" />本系统受理分布</span>
        </div>
      </CardBody>
    </Card>
  )
}

function Expandable({ label, text }: { label: string; text: string }) {
  const [open, setOpen] = useState(false)
  if (!text) return null
  return (
    <div>
      <button onClick={() => setOpen(!open)} className="text-[11px] font-medium text-primary hover:underline">
        {open ? '收起' : '展开'}{label}
      </button>
      {open && <p className="text-xs text-text-secondary leading-relaxed mt-1.5 whitespace-pre-wrap">{text}</p>}
    </div>
  )
}
