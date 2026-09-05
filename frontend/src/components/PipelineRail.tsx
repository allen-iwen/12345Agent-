// 流水线轨道：5 个节点状态一目了然，点击任一节点打开轨迹抽屉（白盒）
import { Check, Loader2, PencilLine, HelpCircle } from 'lucide-react'
import { cn } from '../lib/utils'
import type { CaseView, SectionStatus } from '../lib/api'
import { useApp } from '../store'

const NODES: { key: string; label: string }[] = [
  { key: 'understand', label: '诉求理解' },
  { key: 'work_order', label: '标准化工单' },
  { key: 'classify', label: '事项分类' },
  { key: 'route', label: '承办单位' },
  { key: 'reply', label: '答复草拟' },
]

type NodeState = 'pending' | 'running' | 'done' | 'approved' | 'modified'

function computeState(nodeKey: string, c: CaseView | null): NodeState {
  if (!c) return 'pending'
  const reviewKey =
    nodeKey === 'work_order' ? 'work_order'
    : nodeKey === 'classify' ? 'classification'
    : nodeKey === 'route' ? 'routing'
    : nodeKey === 'reply' ? 'reply'
    : null
  const artifact =
    nodeKey === 'understand' ? c.understanding
    : nodeKey === 'work_order' ? c.work_order
    : nodeKey === 'classify' ? c.classification
    : nodeKey === 'route' ? c.routing
    : nodeKey === 'reply' ? c.reply_draft
    : null
  if (!artifact) return c.status === 'processing' ? 'running' : 'pending'
  if (reviewKey) {
    const rs: SectionStatus | undefined = c.review?.[reviewKey]
    if (rs === 'approved') return 'approved'
    if (rs === 'modified') return 'modified'
  }
  return 'done'
}

const STATE_VISUAL: Record<NodeState, { ring: string; fill: string; label: string }> = {
  pending: { ring: 'border-border-strong', fill: 'bg-transparent', label: 'text-muted' },
  running: { ring: 'border-primary-light', fill: 'bg-primary-light/20', label: 'text-primary' },
  done: { ring: 'border-primary', fill: 'bg-primary', label: 'text-primary-dark' },
  approved: { ring: 'border-success', fill: 'bg-success', label: 'text-success' },
  modified: { ring: 'border-info', fill: 'bg-info', label: 'text-info' },
}

export function PipelineRail({ caseData, compact = false }: { caseData: CaseView | null; compact?: boolean }) {
  const openTrace = useApp((s) => s.openTrace)

  return (
    <div className={cn('flex items-start w-full select-none', compact ? 'gap-0' : 'gap-0 px-2')}>
      {NODES.map((n, i) => {
        const st = computeState(n.key, caseData)
        const v = STATE_VISUAL[st]
        return (
          <div key={n.key} className="flex-1 flex">
            <button
              onClick={(e) => {
                e.stopPropagation()
                openTrace(n.key)
              }}
              className="group flex flex-col items-center gap-1.5 w-full pt-1 pb-0.5 rounded-md hover:bg-surface-hover transition-colors focus-visible:outline-2 focus-visible:outline-primary"
              title={`${n.label} · 点击查看该节点轨迹`}
            >
              <div className="flex items-center w-full">
                {/* 左连线 */}
                <div
                  className={cn(
                    'flex-1 h-px mx-1',
                    i === 0 && 'invisible',
                    st !== 'pending' ? 'bg-primary/40' : 'bg-border',
                  )}
                />
                <span
                  className={cn(
                    'relative flex items-center justify-center rounded-full border-2 transition-colors',
                    compact ? 'h-6 w-6' : 'h-7 w-7',
                    v.ring,
                    v.fill,
                    st === 'running' && 'animate-pulse-dot',
                  )}
                >
                  {st === 'running' && <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />}
                  {st === 'pending' && <span className={cn('text-[10px] font-semibold', 'text-muted-light')}>{i + 1}</span>}
                  {st === 'done' && <Check className={cn(compact ? 'h-3 w-3' : 'h-4 w-4', 'text-white')} strokeWidth={3} />}
                  {st === 'approved' && <Check className={cn(compact ? 'h-3 w-3' : 'h-4 w-4', 'text-white')} strokeWidth={3.5} />}
                  {st === 'modified' && <PencilLine className={cn(compact ? 'h-3 w-3' : 'h-3.5 w-3.5', 'text-white')} strokeWidth={2.5} />}
                </span>
                {/* 右连线 */}
                <div
                  className={cn(
                    'flex-1 h-px mx-1',
                    i === NODES.length - 1 && 'invisible',
                    computeState(NODES[i + 1]?.key ?? '', caseData) !== 'pending' ? 'bg-primary/40' : 'bg-border',
                  )}
                />
              </div>
              <span className={cn('text-[11px] font-medium leading-none whitespace-nowrap', v.label, compact && 'text-[10px]')}>
                {n.label}
              </span>
            </button>
          </div>
        )
      })}
    </div>
  )
}

// 案件卡片用的迷你轨道（无理解节点的审核态，仅展示产物完成度）
export function MiniRail({ caseData }: { caseData: CaseView }) {
  return <PipelineRail caseData={caseData} compact />
}

export { computeState }
export { HelpCircle }
