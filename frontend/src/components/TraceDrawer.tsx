// 轨迹抽屉：白盒展示每个 Agent 节点的输入/输出/耗时（评委可现场点开看）
import useSWR from 'swr'
import { X, Clock, ArrowDown, ArrowUp, AlertTriangle, FileSearch } from 'lucide-react'
import { api } from '../lib/api'
import { NODE_META } from '../lib/utils'
import { useApp } from '../store'
import { Badge, Spinner } from '../ui'

export function TraceDrawer({ caseId }: { caseId: string }) {
  const { traceNode, closeTrace } = useApp()
  const { data, isLoading } = useSWR(
    traceNode ? ['runs', caseId] : null,
    () => api.listRuns(caseId),
    { refreshInterval: 0 },
  )

  if (!traceNode) return null
  const runs = (data?.runs ?? []).filter((r) => r.node === traceNode)
  const meta = NODE_META[traceNode] ?? { label: traceNode, short: traceNode }

  return (
    <>
      {/* 遮罩 */}
      <div className="fixed inset-0 bg-black/20 z-40 animate-fade-in" onClick={closeTrace} />
      {/* 抽屉 */}
      <aside className="fixed right-0 top-0 bottom-0 w-[440px] max-w-[90vw] bg-surface-elevated border-l border-border shadow-xl z-50 flex flex-col animate-fade-in">
        <header className="flex items-center gap-2 px-4 h-12 border-b border-border shrink-0">
          <FileSearch className="h-4 w-4 text-primary" />
          <span className="text-sm font-semibold">{meta.label} · 节点轨迹</span>
          <span className="text-[11px] text-muted font-mono ml-auto">{caseId.slice(0, 8)}</span>
          <button onClick={closeTrace} className="p-1 rounded hover:bg-surface-hover text-muted">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {isLoading && (
            <div className="flex items-center gap-2 text-muted text-sm py-8 justify-center">
              <Spinner /> 加载轨迹…
            </div>
          )}
          {!isLoading && runs.length === 0 && (
            <div className="text-sm text-muted text-center py-12 leading-relaxed">
              该节点暂无轨迹记录
              <br />
              <span className="text-xs">（可能是重跑后使用了新 thread）</span>
            </div>
          )}
          {runs.map((r, idx) => (
            <div key={r.id} className="border border-border rounded-lg overflow-hidden">
              <div className="flex items-center gap-2 px-3 py-2 bg-surface-hover/50 border-b border-border">
                <span className="text-xs font-semibold">第 {idx + 1} 次执行</span>
                {r.status === 'ok' && <Badge tone="success">成功</Badge>}
                {r.status === 'failed' && (
                  <Badge tone="danger">
                    <AlertTriangle className="h-3 w-3" /> 失败
                  </Badge>
                )}
                {r.status === 'running' && <Badge tone="info">进行中</Badge>}
                {r.duration_ms != null && (
                  <span className="inline-flex items-center gap-1 text-[11px] text-muted ml-auto font-mono">
                    <Clock className="h-3 w-3" />
                    {r.duration_ms >= 1000 ? `${(r.duration_ms / 1000).toFixed(1)}s` : `${r.duration_ms}ms`}
                  </span>
                )}
              </div>
              <div className="p-3 space-y-3">
                <section>
                  <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted mb-1.5">
                    <ArrowDown className="h-3 w-3" /> 输入
                  </div>
                  <JsonBlock obj={r.input_json} />
                </section>
                <section>
                  <div className="flex items-center gap-1.5 text-[11px] font-medium text-muted mb-1.5">
                    <ArrowUp className="h-3 w-3" /> 输出
                  </div>
                  {r.error ? (
                    <div className="text-xs text-danger bg-danger-subtle rounded-md p-2.5 font-mono break-all">
                      {r.error}
                    </div>
                  ) : (
                    <JsonBlock obj={r.output_json} />
                  )}
                </section>
              </div>
            </div>
          ))}
        </div>
      </aside>
    </>
  )
}

function JsonBlock({ obj }: { obj: unknown }) {
  if (obj == null) return <div className="text-xs text-muted-light">（无）</div>
  return (
    <pre className="text-[11px] leading-relaxed font-mono bg-[#0F172A] text-[#CBD5E1] rounded-md p-3 overflow-x-auto max-h-72 overflow-y-auto whitespace-pre-wrap break-all">
      {typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2)}
    </pre>
  )
}
