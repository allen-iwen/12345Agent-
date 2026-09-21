// 工单流转看板：按流转状态分组，支持就地迁移（受角色守卫）与临期/超期督办
import { useState } from 'react'
import useSWR from 'swr'
import { AlertTriangle, ArrowRight, Loader2, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { Badge, Button, Card, CardBody, Spinner } from '../ui'
import { cn } from '../lib/utils'

const ROLE_LABEL: Record<string, string> = {
  agent: '坐席',
  dispatcher: '派单员',
  reviewer: '审核员',
  dept: '部门用户',
  admin: '管理员',
  supervisor: '监督员',
}

// 主线 8 态 + 旁路 2 态（与后端 workflow_state 对齐，仅用于列宽与配色）
const COLUMN_HINT: Record<string, string> = {
  received: '智能体链路处理中；链路完成后由系统自动进入「已分类」',
  triaged: '分类与转派建议已就绪，等待人工审核派单',
  dispatched: '已派单，等待承办单位签收',
  accepted: '承办单位已签收，即将进入办理',
  processing: '承办单位办理中',
  replied: '已回执，等待热线审核答复',
  reviewed: '审核通过，等待归档',
  closed: '已归档，进入历史库供相似检索',
  returned: '被退回，需重新确认承办单位',
  suspended: '承诺办理挂起（复杂事项，最长 9 个月）',
}

export function BoardPage() {
  const { data, isLoading, mutate } = useSWR(['board'], () => api.board(), { refreshInterval: 15000 })
  const [role, setRole] = useState<string>('dispatcher')
  const [actor, setActor] = useState<string>('派单员（演示）')
  const [busy, setBusy] = useState<string>('')
  const [error, setError] = useState<string>('')

  const doTransition = async (caseId: string, to: string, action: string, expectedFrom: string) => {
    setBusy(caseId + to)
    setError('')
    try {
      await api.transition(caseId, to, { role, actor, expectedFrom, note: `${action}（看板操作）` })
      await mutate()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy('')
    }
  }

  const total = data?.total_cases ?? 0
  const overdue = (data?.groups ?? []).flatMap((g) => g.items).filter((i) => i.deadline_state === '超期').length

  return (
    <div className="h-full min-h-0 flex flex-col">
      <header className="shrink-0 border-b border-border bg-surface-elevated px-5 py-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <div>
            <h1 className="text-base font-semibold tracking-tight">工单流转看板</h1>
            <p className="text-[11px] text-muted mt-0.5">
              共 {total} 件｜按业务流程状态分组，就地流转（受角色守卫），临期与超期自动标记
            </p>
          </div>
          <div className="ml-auto flex items-center gap-2 text-xs">
            <span className="text-muted">操作身份</span>
            <select
              value={role}
              onChange={(e) => {
                setRole(e.target.value)
                setActor(`${ROLE_LABEL[e.target.value] ?? e.target.value}（演示）`)
              }}
              className="text-xs rounded-md border border-border bg-surface px-2 h-7 focus:outline-none focus:border-primary"
            >
              {Object.entries(ROLE_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <span className="font-mono text-[11px] text-muted-light">{actor}</span>
            <Button size="sm" onClick={() => mutate()} title="刷新看板">
              <RefreshCw className="h-3.5 w-3.5" />
              刷新
            </Button>
          </div>
        </div>
        {overdue > 0 && (
          <div className="mt-2 flex items-center gap-1.5 text-[11px] text-danger">
            <AlertTriangle className="h-3.5 w-3.5" />
            {overdue} 件已超期，建议按规范启动督办（群众多次反映、办理不到位的可联合督查机构专项督办）
          </div>
        )}
        {error && <div className="mt-2 text-[11px] text-danger">{error}</div>}
      </header>

      <div className="flex-1 min-h-0 overflow-x-auto overflow-y-hidden bg-surface">
        {isLoading && !data ? (
          <div className="h-full flex items-center justify-center gap-2 text-muted text-sm">
            <Spinner /> 加载看板…
          </div>
        ) : (
          <div className="flex gap-3 p-4 h-full items-stretch">
            {(data?.groups ?? []).map((g) => (
              <section key={g.state} className="w-[268px] shrink-0 flex flex-col min-h-0">
                <div className="flex items-center gap-2 px-1 pb-2">
                  <span className="text-[13px] font-semibold">{g.label}</span>
                  <span className="text-[11px] text-muted font-mono">{g.count}</span>
                  {g.state === 'returned' && g.count > 0 && <Badge tone="warning">需重派</Badge>}
                  {g.state === 'suspended' && g.count > 0 && <Badge tone="info">挂起</Badge>}
                </div>
                <div className="text-[10px] text-muted-light px-1 pb-2 leading-snug h-8">{COLUMN_HINT[g.state]}</div>
                <div className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-0.5">
                  {g.count === 0 && (
                    <div className="text-[11px] text-muted-light border border-dashed border-border rounded-md px-2.5 py-3 text-center">
                      暂无
                    </div>
                  )}
                  {g.items.map((it) => (
                    <Card key={it.case_id} className="hover:border-border-strong transition-colors">
                      <CardBody className="p-2.5 space-y-1.5">
                        <div className="flex items-start gap-1.5">
                          {it.urgency_level === '特急' && (
                            <span className="shrink-0 mt-px rounded-[2px] bg-danger text-white text-[10px] font-semibold px-1 leading-4">特急</span>
                          )}
                          {it.urgency_level === '紧急' && (
                            <span className="shrink-0 mt-px rounded-[2px] border border-warning text-warning text-[10px] font-semibold px-1 leading-4">紧急</span>
                          )}
                          <span className="text-[12px] leading-snug line-clamp-2">{it.title}</span>
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                          {it.deadline_state === '超期' && <Badge tone="danger">超期</Badge>}
                          {it.deadline_state === '临期' && <Badge tone="warning">临期</Badge>}
                          {it.deadline_state === '正常' && (
                            <span className="text-muted-light font-mono">剩 {Math.max(0, it.remaining_hours).toFixed(0)}h</span>
                          )}
                          <span className="text-muted-light font-mono ml-auto">{it.updated_at.slice(5, 16).replace('T', ' ')}</span>
                        </div>
                        <div className="flex flex-wrap gap-1 pt-0.5">
                          {nextActionsFor(g.state).map((na) => (
                            <button
                              key={na.to}
                              disabled={busy === it.case_id + na.to}
                              onClick={() => doTransition(it.case_id, na.to, na.action, g.state)}
                              title={`${na.description}（需要：${na.required_roles.map((r) => ROLE_LABEL[r] ?? r).join('/')}）`}
                              className={cn(
                                'inline-flex items-center gap-1 text-[10px] rounded-[3px] border px-1.5 py-0.5 transition-colors',
                                'border-border text-text-secondary hover:border-primary hover:text-primary',
                                busy === it.case_id + na.to && 'opacity-60 pointer-events-none',
                              )}
                            >
                              {busy === it.case_id + na.to ? <Loader2 className="h-2.5 w-2.5 animate-spin" /> : <ArrowRight className="h-2.5 w-2.5" />}
                              {na.action}
                            </button>
                          ))}
                        </div>
                      </CardBody>
                    </Card>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// 看板上的快捷动作：只暴露主线常用迁移，完整可用动作以 /api/cases/{id}/flow 为准
function nextActionsFor(state: string): { to: string; action: string; description: string; required_roles: string[] }[] {
  const map: Record<string, { to: string; action: string; description: string; required_roles: string[] }[]> = {
    // received → triaged 由系统在链路完成时自动推进，不提供手工按钮（管理员可在详情页强制）
    received: [],
    triaged: [
      { to: 'dispatched', action: '确认派单', description: '确认承办单位后派单', required_roles: ['dispatcher', 'admin'] },
      { to: 'returned', action: '退回重派', description: '分类或承办单位不可用', required_roles: ['reviewer', 'dispatcher', 'admin'] },
    ],
    dispatched: [
      { to: 'accepted', action: '部门签收', description: '承办单位签收工单', required_roles: ['dept', 'admin'] },
      { to: 'returned', action: '部门退回', description: '职责不符需重派', required_roles: ['dept', 'admin'] },
    ],
    accepted: [
      { to: 'processing', action: '开始办理', description: '承办单位开始办理', required_roles: ['dept', 'admin'] },
      { to: 'suspended', action: '承诺办理', description: '复杂事项挂起', required_roles: ['dept', 'admin'] },
    ],
    processing: [
      { to: 'replied', action: '提交回执', description: '提交办理结果与答复', required_roles: ['dept', 'admin'] },
      { to: 'suspended', action: '承诺办理', description: '办理中申请承诺办理', required_roles: ['dept', 'admin'] },
    ],
    replied: [
      { to: 'reviewed', action: '审核通过', description: '答复与结果审核通过', required_roles: ['reviewer', 'admin'] },
      { to: 'returned', action: '答复退回', description: '答复不规范，退回重办', required_roles: ['reviewer', 'admin'] },
    ],
    reviewed: [{ to: 'closed', action: '归档', description: '工单归档', required_roles: ['reviewer', 'admin'] }],
    returned: [{ to: 'triaged', action: '重新分派', description: '重新确认承办单位', required_roles: ['dispatcher', 'admin'] }],
    suspended: [{ to: 'processing', action: '恢复办理', description: '承诺办理恢复', required_roles: ['dept', 'admin'] }],
    closed: [],
  }
  return map[state] ?? []
}
