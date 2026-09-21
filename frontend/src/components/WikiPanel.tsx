// 知识词条（wiki）：口径层维护 —— 列表 / 编辑 / 版本 / 发布
import { useEffect, useState } from 'react'
import useSWR from 'swr'
import { Check, FileText, Loader2, Plus, Search } from 'lucide-react'
import { api, type WikiEntry } from '../lib/api'
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Spinner } from '../ui'
import { cn, fmtTime } from '../lib/utils'

const EMPTY: WikiEntry = {
  slug: '', title: '', category: '办事指南', body_md: '', tags: [], version: 0,
  status: 'draft', author: '', reviewer: '', source_case_id: '', created_at: '', updated_at: '',
}

export function WikiPanel() {
  const [category, setCategory] = useState<string>('')
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState<string>('')
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<WikiEntry>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const { data: list, mutate: mutateList, isLoading } = useSWR(
    ['wiki', category, q],
    () => api.wikiList({ category: category || undefined, q: q || undefined }),
  )
  const { data: entry, mutate: mutateEntry } = useSWR(
    selected ? ['wiki-entry', selected] : null,
    () => api.wikiGet(selected),
  )

  useEffect(() => {
    if (entry && !editing) setDraft(entry)
  }, [entry, editing])

  const refresh = async () => {
    await mutateList()
    if (selected) await mutateEntry()
  }

  const startNew = () => {
    setSelected('')
    setDraft({ ...EMPTY, slug: `entry-${Date.now().toString(36)}` })
    setEditing(true)
    setMsg('')
    setErr('')
  }

  const save = async () => {
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      const r = await api.wikiSave({
        slug: draft.slug, title: draft.title, body_md: draft.body_md,
        category: draft.category, tags: draft.tags, note: draft.version ? '人工修订' : '新建词条',
      })
      setMsg(`已保存（v${r.version}）`)
      setSelected(r.slug)
      setEditing(false)
      await refresh()
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const publish = async (slug: string) => {
    setBusy(true)
    setErr('')
    try {
      await api.wikiPublish(slug, '口径确认发布')
      setMsg('已发布（口径对外生效前需有人把关）')
      await refresh()
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const unpublish = async (slug: string) => {
    setBusy(true)
    try {
      await api.wikiUnpublish(slug)
      await refresh()
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">
      {/* 左：列表 */}
      <Card className="self-start">
        <CardHeader>
          <CardTitle>知识词条</CardTitle>
          <span className="text-[11px] text-muted ml-auto">
            共 {list?.counts.total ?? 0}｜已发布 {list?.counts.by_status?.published ?? 0}
          </span>
        </CardHeader>
        <CardBody className="space-y-2">
          <div className="flex gap-1.5">
            <div className="relative flex-1">
              <Search className="h-3.5 w-3.5 absolute left-2 top-2 text-muted-light" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜索词条…"
                className="w-full text-xs rounded-md border border-border bg-surface pl-7 pr-2 h-7 focus:outline-none focus:border-primary"
              />
            </div>
            <Button size="sm" onClick={startNew} title="新建词条">
              <Plus className="h-3.5 w-3.5" />
              新建
            </Button>
          </div>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full text-xs rounded-md border border-border bg-surface px-2 h-7 focus:outline-none focus:border-primary"
          >
            <option value="">全部分类</option>
            {(list?.categories ?? []).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          <div className="mt-1 space-y-1.5 max-h-[520px] overflow-y-auto">
            {isLoading && <div className="text-xs text-muted flex items-center gap-1.5"><Spinner />加载中…</div>}
            {!isLoading && (list?.items ?? []).length === 0 && (
              <div className="text-[11px] text-muted leading-relaxed border border-dashed border-border rounded-md p-2.5">
                暂无词条。可点「新建」沉淀办理口径，或在案件详情里用「沉淀为词条」由案件自动生成草稿。
              </div>
            )}
            {(list?.items ?? []).map((it) => (
              <button
                key={it.slug}
                onClick={() => {
                  setSelected(it.slug)
                  setEditing(false)
                  setMsg('')
                  setErr('')
                }}
                className={cn(
                  'w-full text-left rounded-md border px-2.5 py-2 transition-colors',
                  selected === it.slug ? 'border-primary/40 bg-primary-subtle/30' : 'border-border hover:border-border-strong',
                )}
              >
                <div className="flex items-center gap-1.5">
                  <span className="text-[12px] font-medium leading-snug line-clamp-2">{it.title}</span>
                </div>
                <div className="flex items-center gap-1.5 mt-1 text-[10px] text-muted-light">
                  <span className="rounded-[2px] border border-border px-1">{it.category}</span>
                  <span className="font-mono">v{it.version}</span>
                  {it.status === 'published' ? <Badge tone="success">已发布</Badge> : <Badge>草稿</Badge>}
                </div>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      {/* 右：详情 / 编辑 */}
      <Card className="self-start">
        <CardHeader>
          <FileText className="h-3.5 w-3.5 text-muted-light" />
          <CardTitle>{editing ? (draft.version ? '修订词条' : '新建词条') : (entry?.title ?? '选择或新建词条')}</CardTitle>
          {!editing && entry && (
            <div className="ml-auto flex items-center gap-1.5">
              {entry.status === 'published' ? (
                <Button size="sm" onClick={() => unpublish(entry.slug)} disabled={busy}>下架</Button>
              ) : (
                <Button size="sm" variant="primary" onClick={() => publish(entry.slug)} disabled={busy}>
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                  发布
                </Button>
              )}
              <Button size="sm" onClick={() => { setDraft(entry); setEditing(true) }}>修订</Button>
            </div>
          )}
          {editing && (
            <div className="ml-auto flex items-center gap-1.5">
              <Button size="sm" variant="primary" onClick={save} disabled={busy || !draft.title.trim()}>
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                保存（新版本）
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setDraft(entry ?? EMPTY) }}>取消</Button>
            </div>
          )}
        </CardHeader>
        <CardBody>
          {msg && <div className="mb-2 text-[11px] text-success">{msg}</div>}
          {err && <div className="mb-2 text-[11px] text-danger">{err}</div>}

          {!editing && !entry && (
            <div className="text-xs text-muted leading-relaxed">
              词条是「口径层」：人可维护的办理经验、答话口径、案例复盘与政策解读。
              与政策库/职责规则（依据层）分工明确——依据决定判断，口径统一表达。
            </div>
          )}

          {!editing && entry && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                <Badge>{entry.category}</Badge>
                <span className="font-mono">v{entry.version}</span>
                {entry.status === 'published'
                  ? <Badge tone="success">已发布{entry.reviewer ? `（${entry.reviewer}）` : ''}</Badge>
                  : <Badge tone="warning">草稿（未生效）</Badge>}
                <span>更新于 {fmtTime(entry.updated_at)}</span>
                {entry.source_case_id && <span className="text-muted-light">来源案件 {entry.source_case_id.slice(0, 8)}</span>}
              </div>
              <pre className="text-[13px] leading-relaxed whitespace-pre-wrap font-sans bg-surface border border-border rounded-md p-3.5">
                {entry.body_md}
              </pre>
              {(entry.revisions ?? []).length > 0 && (
                <details className="text-[11px] border border-border rounded-md">
                  <summary className="cursor-pointer px-2.5 py-1.5 text-text-secondary select-none">
                    修订历史（{entry.revisions?.length} 版）
                  </summary>
                  <div className="px-2.5 pb-2 pt-1 border-t border-border space-y-1">
                    {(entry.revisions ?? []).map((r) => (
                      <div key={r.id} className="flex items-baseline gap-2">
                        <span className="font-mono text-muted-light">v{r.version}</span>
                        <span className="text-text-secondary">{r.note || '（无说明）'}</span>
                        <span className="text-muted-light ml-auto">{r.editor || '—'}｜{fmtTime(r.created_at)}</span>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </div>
          )}

          {editing && (
            <div className="space-y-2">
              <div className="grid grid-cols-[1fr_140px] gap-2">
                <input
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  placeholder="词条标题"
                  className="text-sm rounded-md border border-border bg-surface px-2.5 h-8 focus:outline-none focus:border-primary"
                />
                <select
                  value={draft.category}
                  onChange={(e) => setDraft({ ...draft, category: e.target.value })}
                  className="text-xs rounded-md border border-border bg-surface px-2 h-8 focus:outline-none focus:border-primary"
                >
                  {['政策解读', '部门职责', '办事指南', '案例经验', '口径话术'].map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
              <input
                value={draft.slug}
                onChange={(e) => setDraft({ ...draft, slug: e.target.value })}
                placeholder="slug（小写字母/数字/连字符）"
                className="w-full text-xs font-mono rounded-md border border-border bg-surface px-2.5 h-7 focus:outline-none focus:border-primary"
              />
              <textarea
                value={draft.body_md}
                onChange={(e) => setDraft({ ...draft, body_md: e.target.value })}
                rows={16}
                placeholder="正文（Markdown）——建议包含：适用情形 / 办理要点 / 答复口径 / 政策依据 / 注意事项"
                className="w-full text-[13px] font-mono rounded-md border border-border bg-surface px-3 py-2.5 resize-y focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}
