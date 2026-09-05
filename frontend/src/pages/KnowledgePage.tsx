// 知识库：官方 18 条历史工单浏览 + 部门职能目录 + 工单流转总览
import { useRef, useState } from 'react'
import useSWR from 'swr'
import { ChevronRight, FileUp, Loader2, Search, Trash2 } from 'lucide-react'
import { api, type DepartmentInfo } from '../lib/api'
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
      <header className="mb-5 pb-3 border-b border-border">
        <h1 className="text-base font-semibold tracking-tight">知识库 · 数据、职能与流转</h1>
        <p className="text-xs text-muted mt-1">
          工单流转总览、部门职能目录、政策依据库与 {data?.total ?? '…'} 条官方历史工单——智能体分类、转派、答复的全部数据底料，可现场查验。
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

      {/* 工单流转总览 */}
      <FlowPanel />

      {/* 部门职能目录 */}
      <DeptPanel />

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

// ---------- 工单流转总览 ----------
const FLOW_STEPS: { title: string; sub: string; tag?: 'agent' | 'human' | 'dept' }[] = [
  { title: '市民来电', sub: '电话 / 录音 / 文本' },
  { title: '智能受理', sub: '理解→工单→分类→转派→答复', tag: 'agent' },
  { title: '坐席审核', sub: '四节确认 / 修改 / 补充重跑', tag: 'human' },
  { title: '派单主办', sub: '主办单位 + 协办单位', tag: 'dept' },
  { title: '部门办理', sub: '限时办结 · 进度反馈', tag: 'dept' },
  { title: '答复回访', sub: '统一答复 / 满意度回访', tag: 'human' },
  { title: '归档沉淀', sub: '知识库 / 苗头预警分析', tag: 'agent' },
]

const TAG_META = {
  agent: { label: '智能体', cls: 'bg-primary-subtle text-primary border-primary/30' },
  human: { label: '人工', cls: 'bg-warning-subtle text-warning border-warning/30' },
  dept: { label: '职能部门', cls: 'bg-info-subtle text-info border-info/30' },
} as const

function FlowPanel() {
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>工单流转总览</CardTitle>
        <span className="text-[11px] text-muted ml-auto">从市民来电到办结归档：智能体、坐席、职能部门三方协同</span>
      </CardHeader>
      <CardBody>
        <div className="flex flex-wrap items-stretch gap-y-3">
          {FLOW_STEPS.map((s, i) => {
            const tag = s.tag ? TAG_META[s.tag] : null
            return (
              <div key={s.title} className="flex items-stretch">
                <div className="w-[8.5rem] rounded-md border border-border bg-surface-elevated px-2.5 py-2 flex flex-col gap-1">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[9px] font-mono text-muted-light">{String(i + 1).padStart(2, '0')}</span>
                    <span className="text-xs font-semibold text-text-primary leading-none">{s.title}</span>
                  </div>
                  <div className="text-[10px] text-muted leading-snug">{s.sub}</div>
                  {tag && (
                    <span className={'self-start text-[9px] px-1 py-px rounded-sm border font-medium ' + tag.cls}>{tag.label}</span>
                  )}
                </div>
                {i < FLOW_STEPS.length - 1 && (
                  <div className="flex items-center px-0.5">
                    <ChevronRight className="h-3.5 w-3.5 text-muted-light shrink-0" />
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <div className="flex flex-wrap gap-4 text-[10px] text-muted mt-3 pt-2.5 border-t border-border">
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-primary/70" />智能体执行</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-warning/70" />人工环节</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-sm bg-info/70" />部门环节</span>
          <span className="ml-auto">异常支线：要素缺失 → 澄清补录后重跑；职责交叉 → 人工裁断改派</span>
        </div>
      </CardBody>
    </Card>
  )
}

// ---------- 部门职能目录 ----------
function DeptPanel() {
  const { data, isLoading } = useSWR(['departments'], () => api.listDepartments())
  const [q, setQ] = useState('')
  const depts = data?.departments ?? []
  const filtered = q
    ? depts.filter((d) =>
        [d.name, d.responsibilities, ...d.categories, ...d.keywords, ...d.co_departments]
          .join('\n')
          .toLowerCase()
          .includes(q.toLowerCase()),
      )
    : depts
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>部门职能目录</CardTitle>
        <span className="text-[11px] text-muted ml-auto">
          {depts.length} 个承办单位 · 转派节点按此规则判定主办/协办
        </span>
      </CardHeader>
      <CardBody className="space-y-2.5">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-light" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜部门 / 职责 / 分类关键词，如「城管」「油烟」「医保」…"
            className="w-full h-9 text-sm rounded-md border border-border bg-surface-elevated pl-8 pr-3 focus:outline-none focus:border-primary"
          />
        </div>
        {isLoading ? (
          <Spinner />
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-2.5">
            {filtered.map((d) => (
              <DeptCard key={d.name} d={d} />
            ))}
          </div>
        )}
        {!isLoading && filtered.length === 0 && (
          <div className="text-sm text-muted text-center py-6">无匹配部门</div>
        )}
        {data?.notice && (
          <div className="text-[10px] text-muted-light pt-1 border-t border-border">{data.notice}</div>
        )}
      </CardBody>
    </Card>
  )
}

function DeptCard({ d }: { d: DepartmentInfo }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="rounded-md border border-border bg-surface-elevated p-3 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-text-primary leading-tight flex-1 min-w-0">{d.name}</span>
        <span className="text-[10px] font-mono text-muted-light shrink-0">{d.categories.length} 类</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {d.categories.map((c) => (
          <Badge key={c} tone="primary" className="text-[10px]">{c}</Badge>
        ))}
      </div>
      <p className={'text-xs text-text-secondary leading-relaxed ' + (open ? '' : 'line-clamp-2')}>
        {d.responsibilities}
      </p>
      {(d.co_departments.length > 0 || d.keywords.length > 0) && (
        <button onClick={() => setOpen(!open)} className="self-start text-[11px] font-medium text-primary hover:underline">
          {open ? '收起详情' : '协办与关键词'}
        </button>
      )}
      {open && (
        <div className="space-y-1.5 pt-1.5 border-t border-border">
          {d.co_departments.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-[10px] text-muted shrink-0">协办：</span>
              {d.co_departments.map((co) => (
                <span key={co} className="text-[10px] bg-info-subtle text-info rounded px-1.5 py-0.5">{co}</span>
              ))}
            </div>
          )}
          {d.keywords.length > 0 && (
            <div className="flex flex-wrap items-center gap-1">
              <span className="text-[10px] text-muted shrink-0">识别词：</span>
              {d.keywords.slice(0, 12).map((kw) => (
                <span key={kw} className="text-[10px] bg-surface-hover rounded px-1.5 py-0.5">{kw}</span>
              ))}
              {d.keywords.length > 12 && <span className="text-[10px] text-muted-light">等 {d.keywords.length} 个</span>}
            </div>
          )}
        </div>
      )}
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
      setMsg(`已入库「${r.source_name}」，切分 ${r.chunks} 块并完成向量索引`)
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
        <CardTitle>热点问题统计</CardTitle>
        <span className="text-[11px] text-muted ml-auto">
          官方样例 {stats.official_total} 条 · 本系统受理 {stats.demo_total} 件（紧急 {stats.demo_urgent} / 重复 {stats.demo_repeat} / 已归档 {stats.demo_completed}）
        </span>
      </CardHeader>
      <CardBody className="grid grid-cols-1 lg:grid-cols-2 gap-x-8 gap-y-1">
        {stats.efficiency && stats.efficiency.cases_measured > 0 && (
          <div className="col-span-full flex flex-wrap items-center gap-x-4 gap-y-1 mb-2 pb-2 border-b border-border text-xs text-muted">
            <span className="font-medium text-text-secondary shrink-0">基层减负账本</span>
            <span>已测 <b className="font-mono text-text-secondary">{stats.efficiency.cases_measured}</b> 件</span>
            <span>智能体累计 <b className="font-mono text-text-secondary">{stats.efficiency.agent_minutes_total}</b> 分钟</span>
            <span>人工基准估算 <b className="font-mono text-text-secondary">{stats.efficiency.human_minutes_estimated}</b> 分钟</span>
            <span className="text-success font-medium">
              累计约节省 <b className="font-mono">{stats.efficiency.minutes_saved_est}</b> 分钟
              （≈ {(stats.efficiency.minutes_saved_est / 60).toFixed(1)} 小时）
            </span>
          </div>
        )}
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
