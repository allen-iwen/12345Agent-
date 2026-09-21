// 工作台：坐席员视角 —— 左侧录入/队列，右侧全链路审核
import { useRef, useState } from 'react'
import useSWR from 'swr'
import {
  AlertTriangle, AudioLines, Check, ChevronRight, Loader2, PenLine,
  PencilLine, Send, Square, Upload, X,
} from 'lucide-react'
import { api, type CaseView } from '../lib/api'
import { fmtTime, STATUS_META } from '../lib/utils'
import { useMicRecorder } from '../lib/useMicRecorder'
import { useApp } from '../store'
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Field, Spinner } from '../ui'
import { PipelineRail } from '../components/PipelineRail'
import { TraceDrawer } from '../components/TraceDrawer'
import { SimilarPanel } from '../components/SimilarPanel'

const CHANNELS = ['直接来电（呼入）', '网络信件', '领导批示', '媒体转办']

// 演示案例库：覆盖不同类别 / 紧急 / 职责交叉 / 信息缺失
const DEMO_CASES = [
  { tag: '常规', label: '公交线路', text: '市区一处公交站被社会车辆长期占用，公交车无法正常进站，群众出行受影响。' },
  { tag: '常规', label: '理发店证照', text: '南陵县某理发店没有公示服务价格，也没有在醒目位置悬挂营业执照，希望有关部门核查。' },
  { tag: '紧急', label: '燃气泄漏', text: '现在闻到楼道内有很重的燃气味，疑似发生泄漏，请立即处理！' },
  { tag: '交叉', label: '烧烤店扰民', text: '镜湖区某小区楼下烧烤店每天晚上占道经营到凌晨，噪音吵得睡不着，油烟也很呛人，多次反映没人管。' },
  { tag: '缺信息', label: '路灯不亮', text: '我们这边路灯好几天不亮了，晚上出门很危险。' },
  { tag: '欠薪', label: '工地欠薪', text: '在芜湖某工地干了几个月活，包工头一直拖欠工资不给，家里等着用钱。' },
]

export function Workbench() {
  const { selectedCaseId, select } = useApp()
  const { data: cases, mutate: mutateList } = useSWR(['cases'], () => api.listCases(), { refreshInterval: 5000 })
  const { data: detail, isLoading: loadingDetail, mutate: mutateDetail } = useSWR(
    selectedCaseId ? ['case', selectedCaseId] : null,
    () => (selectedCaseId ? api.getCase(selectedCaseId) : null),
  )

  return (
    <div className="flex h-full min-h-0">
      {/* ---------- 左栏 ---------- */}
      <aside className="w-[300px] shrink-0 border-r border-border bg-surface-elevated flex flex-col min-h-0">
        <IntakePanel
          onCreated={async (c) => {
            select(c.case_id)
            await mutateList()
          }}
        />
        <QueuePanel
          cases={cases ?? []}
          selectedId={selectedCaseId}
          onSelect={select}
          loading={!cases}
        />
      </aside>

      {/* ---------- 主区 ---------- */}
      <main className="flex-1 min-w-0 overflow-y-auto relative">
        {!selectedCaseId && <EmptyState />}
        {selectedCaseId && loadingDetail && !detail && (
          <div className="flex items-center justify-center gap-2 text-muted h-full">
            <Spinner /> 加载案件…
          </div>
        )}
        {selectedCaseId && detail && (
          <CaseDetail
            key={detail.case_id}
            data={detail}
            onChanged={async () => {
              await mutateDetail()
              await mutateList()
            }}
          />
        )}
      </main>

      {/* 轨迹抽屉 */}
      {selectedCaseId && <TraceDrawer caseId={selectedCaseId} />}
    </div>
  )
}

// ================= 录入面板 =================
function IntakePanel({ onCreated }: { onCreated: (c: CaseView) => void }) {
  const [text, setText] = useState('')
  const [channel, setChannel] = useState(CHANNELS[0])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [asrBusy, setAsrBusy] = useState(false)
  const [asrNote, setAsrNote] = useState('')
  const [asrRaw, setAsrRaw] = useState('')
  const [showRaw, setShowRaw] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const submit = async () => {
    if (!text.trim() || busy || rec === 'recording') return
    setBusy(true)
    setError('')
    try {
      const c = await api.createCase(text.trim(), channel)
      setText('')
      onCreated(c)
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const uploadAudio = async (f: File) => {
    setAsrBusy(true)
    setAsrNote(`云端转写并整理 ${f.name} 中…`)
    setError('')
    try {
      const r = await api.transcribeAudio(f)
      const fill = r.clean_applied && r.text_clean ? r.text_clean : r.text
      setText((prev) => (prev ? prev + '\n' : '') + fill)
      setAsrRaw(r.text)
      setShowRaw(false)
      const engine = r.source === 'xfyun' ? '讯飞云端' : '本地 SenseVoice'
      const dn = r.clean_applied ? ` · 降噪整理：${(r.clean_changes || []).slice(0, 2).join('、')}` : ''
      setAsrNote(
        `转写完成 · ${engine} · ${(r.latency_ms / 1000).toFixed(1)}s / ${r.segments || 1} 段 / ${r.text.length} 字`
          + (r.clean_note ? ` · ${r.clean_note}` : '') + dn
          + (r.fallback_note ? `（${r.fallback_note}，已自动降级）` : '')
      )
    } catch (e) {
      setError(String(e))
      setAsrNote('')
    } finally {
      setAsrBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const { rec, recSec, micError, start: startRec, stop: stopRec } = useMicRecorder(uploadAudio)

  return (
    <section className="p-3.5 border-b border-border">
      <div className="flex items-center gap-1.5 mb-2">
        <span className="text-xs font-semibold text-text-secondary">受理新诉求</span>
        <span className="text-[10px] text-muted-light">录音 / 文本 · Ctrl+Enter 提交</span>
      </div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submit()
        }}
        placeholder="粘贴来电转写或录入诉求…（Ctrl+Enter 提交）"
        rows={3}
        className="w-full text-sm rounded-md border border-border bg-surface px-2.5 py-2 resize-y placeholder:text-muted-light focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary transition"
      />
      <div className="flex gap-1.5 mt-2">
        <input
          ref={fileRef}
          type="file"
          accept=".mp3,.wav,.m4a,.amr,.aac,.ogg,.flac,.wma,.webm"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) uploadAudio(f)
          }}
        />
        {rec === 'recording' ? (
          <Button
            size="sm"
            onClick={stopRec}
            className="border-red-300 text-red-600 hover:bg-red-50 shrink-0"
            title="停止录音并转写"
          >
            <Square className="h-2.5 w-2.5 fill-current" />
            <span className="font-mono">{`${Math.floor(recSec / 60)}:${String(recSec % 60).padStart(2, '0')}`}</span>
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={startRec}
            disabled={asrBusy || busy}
            className="shrink-0"
            title="网页麦克风现场录音（免上传，停止后自动转写+降噪整理）"
          >
            {asrBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <AudioLines className="h-3.5 w-3.5" />}
            现场录音
          </Button>
        )}
        <Button
          size="sm"
          onClick={() => fileRef.current?.click()}
          disabled={asrBusy || busy || rec === 'recording'}
          className="shrink-0"
          title="上传录音文件，双引擎转写（讯飞云端优先，本地兜底）并降噪整理"
        >
          <Upload className="h-3.5 w-3.5" />
          录音文件
        </Button>
        <select
          value={channel}
          onChange={(e) => setChannel(e.target.value)}
          className="ml-auto text-xs rounded-md border border-border bg-surface px-2 h-7 min-w-0 max-w-[10rem] focus:outline-none focus:border-primary"
          title="来电源"
        >
          {CHANNELS.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </div>
      <Button
        variant="primary"
        size="md"
        onClick={submit}
        disabled={busy || !text.trim() || rec === 'recording'}
        className="w-full mt-1.5 justify-center"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <PenLine className="h-4 w-4" />}
        {busy ? '生成中…（约 1 分钟，五个节点依次执行）' : '生成工单'}
      </Button>
      {rec === 'recording' && (
        <div className="mt-2 text-[11px] flex items-center gap-1.5 text-red-600">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-pulse-dot" />
          正在录音… 再次点击红色按钮结束
        </div>
      )}
      {micError && rec !== 'recording' && (
        <div className="mt-1.5 text-[11px] text-danger">{micError}</div>
      )}
      {asrNote && (
        <div className={'mt-2 text-[11px] flex items-center gap-1.5 ' + (asrBusy ? 'text-primary' : 'text-success')}>
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-current animate-pulse-dot" />
          {asrNote}
        </div>
      )}
      {asrRaw && !asrBusy && (
        <div className="mt-1.5">
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="text-[11px] text-muted hover:text-primary underline underline-offset-2 decoration-border-strong"
          >
            {showRaw ? '收起原始转写（未整理，作证据留存）' : '查看原始转写（未整理，作证据留存）'}
          </button>
          {showRaw && (
            <pre className="mt-1.5 max-h-40 overflow-auto text-[11px] leading-relaxed text-muted whitespace-pre-wrap bg-surface border border-border rounded-md p-2.5">
              {asrRaw}
            </pre>
          )}
        </div>
      )}
      <div className="flex flex-wrap gap-1 mt-2.5">
        <span className="text-[10px] text-muted-light self-center mr-0.5">示例</span>
        {DEMO_CASES.map((d) => (
          <button
            key={d.label}
            onClick={() => setText(d.text)}
            title={d.text}
            className={
              'text-[11px] rounded-[3px] px-1.5 py-[2px] border transition-colors whitespace-nowrap ' +
              (d.tag === '紧急'
                ? 'border-border text-danger hover:border-danger/40'
                : d.tag === '交叉'
                  ? 'border-border text-warning hover:border-warning/40'
                  : d.tag === '缺信息'
                    ? 'border-border text-info hover:border-info/40'
                    : 'border-border text-muted hover:border-border-strong hover:text-text-secondary')
            }
          >
            {d.label}
          </button>
        ))}
      </div>
      {error && <div className="mt-2 text-xs text-danger bg-danger-subtle rounded p-2">{error}</div>}
      {busy && (
        <div className="mt-2 text-[11px] text-muted flex items-center gap-1.5">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary-light animate-pulse-dot" />
          5 节点链路执行中，约需 30-90 秒…
        </div>
      )}
    </section>
  )
}

// ================= 案件队列 =================
function QueuePanel({
  cases, selectedId, onSelect, loading,
}: { cases: CaseView[]; selectedId: string | null; onSelect: (id: string) => void; loading: boolean }) {
  const pending = cases.filter((c) => c.status === 'awaiting_review').length
  return (
    <section className="flex-1 min-h-0 flex flex-col">
      <div className="flex items-center gap-2 px-3.5 py-2 border-b border-border">
        <span className="text-xs font-semibold text-text-secondary">案件队列</span>
        <span className="text-[10px] text-muted">{cases.length} 条</span>
        {pending > 0 && <Badge tone="warning" className="ml-auto">{pending} 待审</Badge>}
      </div>
      <div className="flex-1 overflow-y-auto">
        {loading && <div className="p-4 text-xs text-muted">加载中…</div>}
        {!loading && cases.length === 0 && (
          <div className="p-4 text-xs text-muted leading-relaxed">
            暂无案件，从上方录入第一条诉求开始。
          </div>
        )}
        {cases.map((c) => {
          const sm = STATUS_META[c.status] ?? STATUS_META.processing
          return (
            <button
              key={c.case_id}
              onClick={() => onSelect(c.case_id)}
              className={
                'w-full text-left px-3.5 py-2.5 border-b border-border/60 border-l-2 transition-colors ' +
                (c.case_id === selectedId
                  ? 'bg-primary-subtle/40 border-l-primary'
                  : 'border-l-transparent hover:bg-surface-hover')
              }
            >
              <div className="flex items-center gap-1.5">
                {c.understanding?.urgent && (
                  <span className="h-4 min-w-4 px-0.5 rounded-[2px] bg-danger text-white text-[10px] font-semibold leading-none flex items-center justify-center shrink-0" title="紧急">急</span>
                )}
                {c.understanding?.repeat_request && (
                  <span className="h-4 min-w-4 px-0.5 rounded-[2px] border border-warning/40 text-warning text-[10px] font-semibold leading-none flex items-center justify-center shrink-0" title="重复诉求">重</span>
                )}
                {c.deadline?.state === '超期' && (
                  <span className="h-4 px-1 rounded-[2px] bg-danger text-white text-[10px] font-semibold leading-none flex items-center justify-center shrink-0" title={`已超期（到期 ${c.deadline.due_at}）`}>超期</span>
                )}
                {c.deadline?.state === '临期' && (
                  <span className="h-4 px-1 rounded-[2px] border border-warning text-warning text-[10px] font-semibold leading-none flex items-center justify-center shrink-0" title={`即将到期（到期 ${c.deadline.due_at}）`}>临期</span>
                )}
                <span className="text-[13px] font-medium leading-snug truncate flex-1">
                  {c.work_order?.title ?? c.raw_text.slice(0, 20) + '…'}
                </span>
              </div>
              <div className="flex items-center gap-2 mt-1.5">
                <span className={'text-[10px] rounded-[2px] border px-1.5 py-px font-medium ' + sm.cls}>{sm.label}</span>
                {c.deadline && c.deadline.state !== '已办结' && (
                  <span className="text-[10px] text-muted-light font-mono">
                    剩 {c.deadline.remaining_hours >= 0 ? c.deadline.remaining_hours.toFixed(0) : '-' + Math.abs(c.deadline.remaining_hours).toFixed(0)}h
                  </span>
                )}
                <span className="text-[10px] text-muted-light font-mono ml-auto">{fmtTime(c.created_at)}</span>
              </div>
            </button>
          )
        })}
      </div>
    </section>
  )
}

// ================= 空状态 =================
function EmptyState() {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-2.5 text-center p-8">
      <div className="font-mono text-[28px] font-semibold tracking-tight text-muted-light leading-none">12345</div>
      <div className="text-sm font-semibold mt-1">热线工单智能体 · 坐席工作台</div>
      <div className="text-xs text-muted max-w-md leading-relaxed">
        录入群众诉求，智能体依次完成 <b className="text-text-secondary">诉求理解 → 标准化工单 → 事项分类 → 承办单位 → 答复草拟</b>，
        每一步可审核、可修改、可追溯，最终由人工放行。
      </div>
      <div className="text-[11px] text-muted-light mt-1 border-t border-border pt-2">AI 结果仅为辅助建议 · 最终以工作人员审核为准</div>
    </div>
  )
}

// ================= 案件详情 =================
function CaseDetail({ data, onChanged }: { data: CaseView; onChanged: () => void }) {
  return (
    <div className="max-w-[1080px] mx-auto p-5 pb-24 animate-fade-in">
      {/* 案件头 */}
      <header className="flex items-start gap-3 mb-4">
        <div className="flex-1 min-w-0">
          <h1 className="text-lg font-semibold leading-snug">
            {data.work_order?.title ?? '（工单生成中）'}
          </h1>
          <div className="flex flex-wrap items-center gap-2 mt-1.5 text-xs text-muted">
            <span className="font-mono">{data.case_id.slice(0, 8)}</span>
            <span>·</span>
            <span>{data.source_channel}</span>
            <span>·</span>
            <span>{fmtTime(data.created_at)}</span>
            {data.understanding?.urgent && <Badge tone="danger">紧急</Badge>}
            {data.understanding?.repeat_request && <Badge tone="warning">重复投诉</Badge>}
          </div>
        </div>
        {(() => {
          const sm = STATUS_META[data.status] ?? STATUS_META.processing
          return <span className={'text-xs rounded-sm border px-2.5 py-1 font-semibold shrink-0 ' + sm.cls}>{sm.label}</span>
        })()}
      </header>

      {/* 流水线轨道 */}
      <Card className="mb-4 py-2">
        <PipelineRail caseData={data} />
      </Card>

      {/* 效率条 */}
      {data.agent_seconds != null && data.agent_seconds > 0 && (
        <EfficiencyStrip agentSeconds={data.agent_seconds} />
      )}

      {/* 紧急处置提示 */}
      {data.understanding?.manual_action && (
        <div className="mb-4 flex items-start gap-2.5 bg-danger-subtle border border-danger/30 rounded-lg p-3.5">
          <AlertTriangle className="h-4.5 w-4.5 text-danger shrink-0 mt-0.5" />
          <div className="text-sm">
            <div className="font-semibold text-danger">需人工紧急处置</div>
            <div className="text-text-secondary mt-0.5">{data.understanding.manual_action}</div>
          </div>
        </div>
      )}

      {/* 支柱二：急件分级与办理时限 */}
      {data.urgency && <UrgencyBanner urgency={data.urgency} />}

      {/* 支柱五：办理时限倒计时 */}
      {data.deadline && <DeadlineStrip deadline={data.deadline} />}

      {/* 未诉先办 · 苗头预警 */}
      {data.early_warning && <EarlyWarningBanner warning={data.early_warning} />}

      {/* 支柱三：诉求治理建议 */}
      {data.governance?.has_governance_alert && <GovernancePanel governance={data.governance} />}

      {/* 工单质量检查 */}
      {data.qc_checks?.length > 0 && <QcPanel checks={data.qc_checks} />}

      {/* 主体网格 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <div className="space-y-4">
          <RawTextCard data={data} onChanged={onChanged} />
          <SimilarPanel rawText={data.raw_text} />
        </div>
        <div className="space-y-4">
          <WorkOrderCard data={data} onChanged={onChanged} />
          <ClassificationCard data={data} onChanged={onChanged} />
          <RoutingCard data={data} onChanged={onChanged} />
          <ReplyCard data={data} onChanged={onChanged} />
        </div>
      </div>

      {/* 底部 sticky 审核栏 */}
      <ReviewBar data={data} onChanged={onChanged} />
    </div>
  )
}

// ---------- 原始诉求 + 市民追问 ----------
function RawTextCard({ data, onChanged }: { data: CaseView; onChanged: () => void }) {
  const [clarify, setClarify] = useState('')
  const [busy, setBusy] = useState(false)
  const u = data.understanding

  const submitClarify = async () => {
    if (!clarify.trim() || busy) return
    setBusy(true)
    try {
      await api.clarify(data.case_id, clarify.trim())
      setClarify('')
      onChanged()
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <span className="font-mono text-[11px] text-muted-light tabular-nums">01</span>
        <CardTitle>原始诉求</CardTitle>
        <span className="text-[10px] text-muted-light ml-auto">通话记录 · 逐字留存</span>
      </CardHeader>
      <CardBody className="space-y-3">
        <p className="text-sm leading-relaxed text-text">{data.raw_text}</p>

        {u && (
          <div className="border-t border-border pt-2">
            <Field k="摘要" v={u.summary} block />
            {Object.entries(u.elements)
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <Field key={k} k={k} v={v} />
              ))}
          </div>
        )}

        {u?.needs_clarification && u.missing_fields.length > 0 && (
          <div className="bg-info-subtle border border-info/25 rounded-md p-3">
            <div className="text-xs font-semibold text-info mb-1.5">待向市民核实</div>
            <ul className="space-y-0.5">
              {u.missing_fields.map((f, i) => (
                <li key={i} className="text-xs text-text-secondary flex gap-1.5">
                  <ChevronRight className="h-3 w-3 mt-0.5 shrink-0 text-info/60" />
                  {f}
                </li>
              ))}
            </ul>
          </div>
        )}

        {data.clarification_context.length > 0 && (
          <div className="text-xs text-muted space-y-1">
            <div className="font-medium">已补充信息：</div>
            {data.clarification_context.map((c, i) => (
              <div key={i} className="text-text-secondary">· {c}</div>
            ))}
          </div>
        )}

        {data.status !== 'completed' && (
          <div className="border-t border-border pt-3">
            <div className="text-[11px] text-muted font-medium mb-1.5">市民追问 / 回访补充</div>
            <textarea
              value={clarify}
              onChange={(e) => setClarify(e.target.value)}
              rows={2}
              placeholder="回访补充信息（如：具体是镜湖区中山北路…），或点左侧麦克风语音补充"
              className="w-full text-xs rounded-md border border-border bg-surface px-2.5 py-2 resize-none placeholder:text-muted-light focus:outline-none focus:border-primary"
            />
            <div className="flex justify-end mt-1.5">
              <Button size="sm" onClick={submitClarify} disabled={busy || !clarify.trim()}>
                {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                补充后重跑链路
              </Button>
            </div>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

// ---------- 可复用的审核卡片 ----------
function useSection(data: CaseView, onChanged: () => void) {
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')

  const approve = async (section: string) => {
    setBusy(true)
    setError('')
    try {
      await api.review(data.case_id, section as never, 'approve')
      onChanged()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const startEdit = (obj: object) => {
    setDraft(JSON.stringify(obj, null, 2))
    setEditing(true)
  }

  const submitModify = async (section: string) => {
    let payload: object
    try {
      payload = JSON.parse(draft)
    } catch (e) {
      setError('JSON 格式错误：' + String(e))
      return
    }
    setBusy(true)
    setError('')
    try {
      await api.review(data.case_id, section as never, 'modify', payload)
      setEditing(false)
      onChanged()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return { busy, editing, draft, setDraft, setEditing, error, setError, approve, startEdit, submitModify }
}

function ReviewActions({
  status, busy, editing, onApprove, onStartEdit, onCancel, onSubmit,
}: {
  status: 'pending' | 'approved' | 'modified'
  busy: boolean
  editing: boolean
  onApprove: () => void
  onStartEdit: () => void
  onCancel: () => void
  onSubmit: () => void
}) {
  return (
    <div className="flex items-center gap-1.5 ml-auto">
      {status === 'approved' && <Badge tone="success"><Check className="h-3 w-3" />已确认</Badge>}
      {status === 'modified' && <Badge tone="info"><PencilLine className="h-3 w-3" />已修改</Badge>}
      {!editing && (
        <>
          <Button size="sm" variant={status === 'pending' ? 'primary' : 'secondary'} onClick={onApprove} disabled={busy}>
            {busy ? <Spinner className="h-3 w-3" /> : <Check className="h-3.5 w-3.5" />}
            确认
          </Button>
          <Button size="sm" onClick={onStartEdit} disabled={busy}>
            <PencilLine className="h-3.5 w-3.5" />
            修改
          </Button>
        </>
      )}
      {editing && (
        <>
          <Button size="sm" variant="primary" onClick={onSubmit} disabled={busy}>
            {busy ? <Spinner className="h-3 w-3" /> : <Check className="h-3.5 w-3.5" />}
            提交修改
          </Button>
          <Button size="sm" variant="ghost" onClick={onCancel} disabled={busy}>
            <X className="h-3.5 w-3.5" />
            取消
          </Button>
        </>
      )}
    </div>
  )
}

function EditArea({ draft, setDraft }: { draft: string; setDraft: (s: string) => void }) {
  return (
    <textarea
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      rows={10}
      spellCheck={false}
      className="w-full text-[11px] font-mono rounded-md border border-border bg-[#0F172A] text-[#CBD5E1] px-3 py-2.5 resize-y focus:outline-none focus:ring-2 focus:ring-primary/40"
    />
  )
}

function SectionError({ error }: { error: string }) {
  if (!error) return null
  return <div className="mt-2 text-xs text-danger bg-danger-subtle rounded p-2">{error}</div>
}

// ---------- 标准化工单 ----------
function WorkOrderCard({ data, onChanged }: { data: CaseView; onChanged: () => void }) {
  const s = useSection(data, onChanged)
  const wo = data.work_order
  return (
    <Card>
      <CardHeader>
        <span className="font-mono text-[11px] text-muted-light tabular-nums">02</span>
        <CardTitle>标准化工单</CardTitle>
        <ReviewActions
          status={data.review?.work_order ?? 'pending'}
          busy={s.busy}
          editing={s.editing}
          onApprove={() => s.approve('work_order')}
          onStartEdit={() => wo && s.startEdit(wo)}
          onCancel={() => s.setEditing(false)}
          onSubmit={() => s.submitModify('work_order')}
        />
      </CardHeader>
      <CardBody>
        {!wo && <SkeletonText />}
        {wo && !s.editing && (
          <div className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
            <Field k="区域" v={wo.region} />
            <Field k="诉求人" v={wo.requester} />
            <Field k="联系方式" v={wo.contact} />
            <Field k="事发地点" v={wo.location} />
            <Field k="发生时间" v={wo.occurrence_time} />
            <div className="sm:col-span-2">
              <Field k="事件描述" v={wo.event_description} block />
              <Field k="诉求事项" v={wo.handling_request} block />
            </div>
          </div>
        )}
        {wo && s.editing && <EditArea draft={s.draft} setDraft={s.setDraft} />}
        <SectionError error={s.error} />
      </CardBody>
    </Card>
  )
}

// ---------- 事项分类 ----------
function ClassificationCard({ data, onChanged }: { data: CaseView; onChanged: () => void }) {
  const s = useSection(data, onChanged)
  const cls = data.classification
  return (
    <Card>
      <CardHeader>
        <span className="font-mono text-[11px] text-muted-light tabular-nums">03</span>
        <CardTitle>事项分类</CardTitle>
        <ReviewActions
          status={data.review?.classification ?? 'pending'}
          busy={s.busy}
          editing={s.editing}
          onApprove={() => s.approve('classification')}
          onStartEdit={() => cls && s.startEdit(cls)}
          onCancel={() => s.setEditing(false)}
          onSubmit={() => s.submitModify('classification')}
        />
      </CardHeader>
      <CardBody>
        {!cls && <SkeletonText />}
        {cls && !s.editing && (
          <>
            {cls.needs_human_judgment && (
              <div className="mb-2.5 flex items-start gap-2 bg-warning-subtle border border-warning/30 rounded-md p-2.5">
                <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
                <div className="text-xs">
                  <span className="font-semibold text-warning">需人工判断：</span>
                  <span className="text-text-secondary">{cls.judgment_note || '职责交叉或信息不足，请人工确认类别'}</span>
                </div>
              </div>
            )}
            <div className="flex items-center gap-2.5 flex-wrap">
              {cls.category_name ? (
                <Badge tone="primary" className="text-[13px] px-3 py-1">{cls.category_name}</Badge>
              ) : (
                <Badge tone="warning">无法确定</Badge>
              )}
              <div className="flex-1 min-w-[120px] h-1.5 bg-surface-hover rounded-full overflow-hidden">
                <div
                  className={'h-full rounded-full ' + (cls.confidence >= 0.7 ? 'bg-success' : cls.confidence >= 0.4 ? 'bg-warning' : 'bg-danger')}
                  style={{ width: `${Math.round(cls.confidence * 100)}%` }}
                />
              </div>
              <span className="text-xs font-mono text-muted">{Math.round(cls.confidence * 100)}%</span>
            </div>
            <div className="mt-2">
              <Field k="分类依据" v={cls.reason} block />
            </div>
            {cls.candidates.length > 0 && (
              <div className="mt-2 border-t border-border pt-2 space-y-1.5">
                <div className="text-[11px] text-muted font-medium">候选类别</div>
                {cls.candidates.map((c) => (
                  <div key={c.code} className="flex items-center gap-2 text-xs">
                    <span className="text-text-secondary font-medium w-16 shrink-0">{c.name}</span>
                    <div className="flex-1 h-1 bg-surface-hover rounded-full overflow-hidden">
                      <div className="h-full bg-muted-light rounded-full" style={{ width: `${Math.round(c.score * 100)}%` }} />
                    </div>
                    <span className="text-muted-light font-mono w-8 text-right">{Math.round(c.score * 100)}%</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
        {cls && s.editing && <EditArea draft={s.draft} setDraft={s.setDraft} />}
        <SectionError error={s.error} />
      </CardBody>
    </Card>
  )
}

// ---------- 承办单位 ----------
function RoutingCard({ data, onChanged }: { data: CaseView; onChanged: () => void }) {
  const s = useSection(data, onChanged)
  const rt = data.routing
  const { data: depts } = useSWR(['departments'], () => api.listDepartments())
  const duty = (() => {
    const p = rt?.primary
    if (!p || !depts?.departments) return ''
    const hit = depts.departments.find(
      (d) => d.name === p || d.name.includes(p) || p.includes(d.name.split('（')[0]),
    )
    return hit?.responsibilities ?? ''
  })()
  return (
    <Card>
      <CardHeader>
        <span className="font-mono text-[11px] text-muted-light tabular-nums">04</span>
        <CardTitle>承办单位</CardTitle>
        <ReviewActions
          status={data.review?.routing ?? 'pending'}
          busy={s.busy}
          editing={s.editing}
          onApprove={() => s.approve('routing')}
          onStartEdit={() => rt && s.startEdit(rt)}
          onCancel={() => s.setEditing(false)}
          onSubmit={() => s.submitModify('routing')}
        />
      </CardHeader>
      <CardBody>
        {!rt && <SkeletonText />}
        {rt && !s.editing && (
          <div className="space-y-2">
            {/* 支柱一：派单决策路径（规则锚定） */}
            {rt.dispatch_path && (
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-muted border-b border-border pb-2">
                <Badge tone="primary">派单决策 · {rt.dispatch_path}</Badge>
                {rt.primary_kind && <span>主办类型：{rt.primary_kind}</span>}
                {rt.rule_llm_agreement === false ? (
                  <span className="text-warning">⚠ 规则与模型结论不一致</span>
                ) : (
                  <span className="text-success">规则锚定 · 模型复核一致</span>
                )}
              </div>
            )}
            {rt.needs_human_judgment && (
              <div className="flex items-start gap-2 bg-warning-subtle border border-warning/30 rounded-md p-2.5">
                <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
                <div className="text-xs">
                  <span className="font-semibold text-warning">需人工判断：</span>
                  <span className="text-text-secondary">{rt.judgment_note || '职责交叉或无法明确主管部门，请人工裁断'}</span>
                </div>
              </div>
            )}
            {rt.departments.map((d, i) => (
              <div
                key={i}
                className={
                  'flex items-start gap-2.5 rounded-md border p-2.5 ' +
                  (d.name === rt.primary ? 'border-primary/40 bg-primary-subtle/30' : 'border-border bg-surface')
                }
              >
                {d.name === rt.primary ? (
                  <Badge tone="primary">主办</Badge>
                ) : (
                  <Badge>协办</Badge>
                )}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{d.name}</div>
                  <div className="text-xs text-muted mt-0.5">{d.reason}</div>
                </div>
              </div>
            ))}
            {rt.return_risk && rt.return_risk.indexOf('权责清晰') < 0 && (
              <div className="text-[11px] text-warning bg-warning-subtle/60 border border-warning/25 rounded-md px-2.5 py-1.5 leading-relaxed">
                <span className="font-medium">退回风险：</span>
                {rt.return_risk}
              </div>
            )}
            {duty && (
              <div className="text-[11px] text-muted bg-surface border-l-2 border-primary/30 rounded-r-md px-2.5 py-1.5 leading-relaxed">
                <span className="font-medium text-text-secondary">主办职责：</span>
                {duty}
              </div>
            )}
            {/* 支柱一：依据链（可展开，逐条可追溯） */}
            {rt.evidence_chain && rt.evidence_chain.length > 0 && (
              <details className="text-[11px] bg-surface border border-border rounded-md">
                <summary className="cursor-pointer px-2.5 py-1.5 text-text-secondary select-none">
                  派单依据链（{rt.evidence_chain.length} 条 · 可追溯）
                </summary>
                <div className="px-2.5 pb-2 space-y-1.5 border-t border-border pt-2">
                  {rt.evidence_chain.map((e, i) => (
                    <div key={i} className="flex gap-2">
                      <span className="shrink-0 rounded-[2px] border border-border bg-surface-hover text-muted text-[10px] px-1 py-px leading-4">
                        {e.type}
                      </span>
                      <div className="min-w-0">
                        <div className="text-muted-light">{e.source}</div>
                        <div className="text-text-secondary leading-relaxed">{e.detail}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </details>
            )}
            {rt.note && <div className="text-xs text-muted border-t border-border pt-2">{rt.note}</div>}
          </div>
        )}
        {rt && s.editing && <EditArea draft={s.draft} setDraft={s.setDraft} />}
        <SectionError error={s.error} />
      </CardBody>
    </Card>
  )
}

// ---------- 答复草拟 ----------
function ReplyCard({ data, onChanged }: { data: CaseView; onChanged: () => void }) {
  const s = useSection(data, onChanged)
  const rd = data.reply_draft
  return (
    <Card>
      <CardHeader>
        <span className="font-mono text-[11px] text-muted-light tabular-nums">05</span>
        <CardTitle>答复草拟</CardTitle>
        <ReviewActions
          status={data.review?.reply ?? 'pending'}
          busy={s.busy}
          editing={s.editing}
          onApprove={() => s.approve('reply')}
          onStartEdit={() => rd && s.startEdit(rd)}
          onCancel={() => s.setEditing(false)}
          onSubmit={() => s.submitModify('reply')}
        />
      </CardHeader>
      <CardBody>
        {!rd && <SkeletonText />}
        {rd && !s.editing && (
          <>
            <pre className="text-sm leading-relaxed whitespace-pre-wrap font-sans bg-surface rounded-md border border-border p-3.5">
              {rd.reply_text}
            </pre>
            {rd.followup_script && (
              <div className="mt-2.5 bg-info-subtle/60 border border-info/20 rounded-md p-3">
                <div className="text-[11px] font-semibold text-info mb-1.5">回访参考话术</div>
                <p className="text-xs text-text-secondary leading-relaxed whitespace-pre-wrap">{rd.followup_script}</p>
              </div>
            )}
            <div className="flex items-center gap-2 mt-2.5 text-[11px] text-muted flex-wrap">
              <Badge>语气：{rd.tone}</Badge>
              {rd.policy_refs?.map((p) => (
                <Badge key={p} tone="primary" className="max-w-full truncate" title={p}>
                  依据 {p.length > 30 ? p.slice(0, 30) + '…' : p}
                </Badge>
              ))}
              {(!rd.policy_refs || rd.policy_refs.length === 0) && rd.disclaimer && (
                <span className="flex-1 min-w-0">{rd.disclaimer}</span>
              )}
            </div>
            {/* 支柱四：答复合规审查（退回重办风险） */}
            {data.reply_audit && <ReplyAuditBlock audit={data.reply_audit} />}
          </>
        )}
        {rd && s.editing && <EditArea draft={s.draft} setDraft={s.setDraft} />}
        <SectionError error={s.error} />
      </CardBody>
    </Card>
  )
}

function EarlyWarningBanner({ warning }: { warning: NonNullable<CaseView['early_warning']> }) {
  return (
    <Card className="mb-4 border-primary/30 bg-primary-subtle/50">
      <CardBody className="py-3">
        <div className="flex items-start gap-2.5">
          <span className="shrink-0 mt-px rounded-[2px] bg-primary text-white text-[10px] font-semibold px-1.5 py-0.5 leading-4">
            {warning.kind}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-xs text-text-secondary leading-relaxed">{warning.message}</p>
            {warning.related.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {warning.related.map((r) => (
                  <span key={r.case_id} className="text-[10px] text-muted bg-surface-elevated border border-border rounded-[2px] px-1.5 py-px" title={`${r.case_id.slice(0, 8)} · ${r.status}${r.shared_place ? ' · 共同地点 ' + r.shared_place : ''}`}>
                    {r.created_at.slice(5, 10)} {r.title.length > 14 ? r.title.slice(0, 14) + '…' : r.title}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      </CardBody>
    </Card>
  )
}

// ---- 支柱二：急件分级与办理时限 ----
function UrgencyBanner({ urgency }: { urgency: NonNullable<CaseView['urgency']> }) {
  const tone =
    urgency.level === '特急'
      ? { wrap: 'border-danger/40 bg-danger-subtle', chip: 'bg-danger text-white', text: 'text-danger' }
      : urgency.level === '紧急'
        ? { wrap: 'border-warning/40 bg-warning-subtle', chip: 'bg-warning text-white', text: 'text-warning' }
        : { wrap: 'border-border bg-surface-elevated', chip: 'bg-surface-hover text-muted', text: 'text-muted' }
  return (
    <Card className={'mb-4 ' + tone.wrap}>
      <CardBody className="py-3">
        <div className="flex items-start gap-2.5">
          <span className={'shrink-0 mt-px rounded-[2px] text-[10px] font-semibold px-1.5 py-0.5 leading-4 ' + tone.chip}>
            {urgency.level}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className={'text-xs font-semibold ' + tone.text}>{urgency.label}</span>
              <span className="text-[11px] text-muted">{urgency.limit_hint}</span>
            </div>
            {urgency.signals.length > 0 && (
              <div className="mt-1 text-[11px] text-text-secondary">
                识别特征：{urgency.signals.join('、')}
                {urgency.escalated_by_understanding && '（经诉求理解节点紧急标记升级）'}
              </div>
            )}
            {urgency.level !== '一般' && urgency.actions.length > 0 && (
              <ul className="mt-1.5 space-y-0.5">
                {urgency.actions.map((a) => (
                  <li key={a} className="text-[11px] text-text-secondary flex gap-1.5">
                    <span className="text-muted-light">·</span>
                    {a}
                  </li>
                ))}
              </ul>
            )}
            {urgency.basis?.name && (
              <div className="mt-1.5 text-[10px] text-muted-light border-t border-border pt-1.5">
                依据：{urgency.basis.name}——{urgency.basis.clause}
              </div>
            )}
          </div>
        </div>
      </CardBody>
    </Card>
  )
}

// ---- 支柱三：诉求治理建议 ----
function GovernancePanel({ governance }: { governance: NonNullable<CaseView['governance']> }) {
  const rows: { tag: string; text: string }[] = []
  if (governance.repeat?.is_repeat) rows.push({ tag: '重复诉求', text: governance.repeat.message })
  if (governance.aggregation) rows.push({ tag: '并案预警', text: governance.aggregation.message })
  if (governance.return_risk) rows.push({ tag: '退回风险', text: governance.return_risk.message })
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>诉求治理提示</CardTitle>
        <span className="text-[11px] text-muted ml-auto">从"办单"到"治事"</span>
      </CardHeader>
      <CardBody className="py-3 space-y-2">
        {rows.map((r) => (
          <div key={r.tag} className="flex items-start gap-2">
            <span className="shrink-0 mt-px rounded-[2px] border border-border bg-surface-hover text-muted text-[10px] font-medium px-1.5 py-0.5 leading-4">
              {r.tag}
            </span>
            <p className="text-xs text-text-secondary leading-relaxed">{r.text}</p>
          </div>
        ))}
        {governance.suggestions?.length > 0 && (
          <div className="border-t border-border pt-2">
            <div className="text-[11px] text-muted mb-1">治理建议</div>
            <ul className="space-y-0.5">
              {governance.suggestions.map((s) => (
                <li key={s} className="text-xs text-text-secondary flex gap-1.5">
                  <span className="text-muted-light">·</span>
                  {s}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

// ---- 支柱五：办理时限倒计时 ----
function DeadlineStrip({ deadline }: { deadline: NonNullable<CaseView['deadline']> }) {
  const tone =
    deadline.state === '超期'
      ? 'border-danger/40 bg-danger-subtle text-danger'
      : deadline.state === '临期'
        ? 'border-warning/40 bg-warning-subtle text-warning'
        : deadline.state === '已办结'
          ? 'border-border bg-surface-elevated text-muted'
          : 'border-border bg-surface-elevated text-text-secondary'
  const remain =
    deadline.remaining_hours >= 0
      ? `${deadline.remaining_hours.toFixed(1)} 小时`
      : `已超期 ${Math.abs(deadline.remaining_hours).toFixed(1)} 小时`
  return (
    <div className={'mb-4 rounded-md border px-3 py-2 text-[11px] ' + tone}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-semibold">办理时限 · {deadline.state}</span>
        <span>{deadline.label}</span>
        <span className="font-mono">
          到期 {deadline.due_at.replace('T', ' ')}（{deadline.mode}）
        </span>
        <span className="font-mono">剩余 {remain}</span>
      </div>
      {deadline.basis?.clause && (
        <div className="mt-1 text-muted-light">
          依据：{deadline.basis.name}——{deadline.basis.clause}
        </div>
      )}
      {deadline.notes?.length > 0 && (
        <div className="mt-0.5 text-muted-light">注：{deadline.notes.join('；')}</div>
      )}
      {deadline.supervision && <div className="mt-1 font-medium">{deadline.supervision}</div>}
    </div>
  )
}

// ---- 支柱四：答复合规审查 ----
function ReplyAuditBlock({ audit }: { audit: NonNullable<CaseView['reply_audit']> }) {
  const tone =
    audit.risk_level === '高'
      ? 'border-danger/40 bg-danger-subtle'
      : audit.risk_level === '中'
        ? 'border-warning/40 bg-warning-subtle'
        : audit.risk_level === '低'
          ? 'border-border bg-surface'
          : 'border-success/30 bg-success-subtle'
  const textTone = audit.risk_level === '高' ? 'text-danger' : audit.risk_level === '中' ? 'text-warning' : audit.risk_level === '低' ? 'text-muted' : 'text-success'
  return (
    <div className={'mt-3 rounded-md border p-2.5 ' + tone}>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className={'text-xs font-semibold ' + textTone}>答复合规审查 · {audit.risk_level}</span>
        <span className="text-[11px] text-text-secondary">{audit.risk_note}</span>
      </div>
      {audit.findings.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {audit.findings.map((f, i) => (
            <li key={i} className="text-[11px] text-text-secondary">
              <span className="font-medium">{f.label}</span>
              {f.quote && f.quote !== '未回应诉求主题' && (
                <span className="text-muted">（原文：{f.quote.length > 24 ? f.quote.slice(0, 24) + '…' : f.quote}）</span>
              )}
              <span className="text-muted-light"> → {f.suggestion}</span>
              {f.source === 'LLM 复核' && <span className="ml-1 text-[10px] text-muted-light">[模型复核]</span>}
            </li>
          ))}
        </ul>
      )}
      {audit.basis?.name && (
        <div className="mt-1.5 text-[10px] text-muted-light border-t border-border pt-1.5">
          依据：{audit.basis.name}——{audit.basis.clause}
        </div>
      )}
    </div>
  )
}

function EfficiencyStrip({ agentSeconds }: { agentSeconds: number }) {
  const humanMin = 20
  const saved = Math.max(0, humanMin - agentSeconds / 60)
  return (
    <div className="mb-4 flex items-center gap-3 text-[11px] text-muted bg-surface-elevated border border-border rounded-md px-3 py-2">
      <span className="font-medium text-text-secondary shrink-0">效率</span>
      <span>
        智能体五节点累计 <b className="font-mono text-text-secondary">{agentSeconds.toFixed(1)}s</b>
      </span>
      <span className="text-border-strong">|</span>
      <span>
        人工基准约 <b className="font-mono text-text-secondary">{humanMin}</b> 分钟/件（要素核对 8′ + 分类转派 4′ + 答复草拟 8′，工序估算）
      </span>
      <span className="text-border-strong">|</span>
      <span className="text-success font-medium">
        本案约节省 <b className="font-mono">{saved.toFixed(1)}</b> 分钟
      </span>
    </div>
  )
}

function QcPanel({ checks }: { checks: { item: string; passed: boolean; detail: string }[] }) {
  const failed = checks.filter((c) => !c.passed)
  return (
    <Card className="mb-4">
      <CardHeader>
        <CardTitle>工单质量检查</CardTitle>
        <span className={'text-[11px] ml-auto font-medium ' + (failed.length === 0 ? 'text-success' : 'text-warning')}>
          {failed.length === 0 ? `${checks.length} 项全部通过` : `${checks.length - failed.length}/${checks.length} 通过`}
        </span>
      </CardHeader>
      <CardBody className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1">
        {checks.map((c) => (
          <div key={c.item} className="flex items-start gap-2 py-1">
            {c.passed ? (
              <Check className="h-3.5 w-3.5 text-success shrink-0 mt-0.5" strokeWidth={3} />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5 text-warning shrink-0 mt-0.5" />
            )}
            <div className="min-w-0">
              <span className={'text-xs font-medium ' + (c.passed ? 'text-text-secondary' : 'text-warning')}>{c.item}</span>
              {!c.passed && c.detail && <div className="text-[11px] text-muted leading-snug">{c.detail}</div>}
            </div>
          </div>
        ))}
      </CardBody>
    </Card>
  )
}

// ---------- 底部审核栏 ----------
function ReviewBar({ data, onChanged }: { data: CaseView; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const sections = ['work_order', 'classification', 'routing', 'reply'] as const
  const labels: Record<string, string> = {
    work_order: '工单', classification: '分类', routing: '转派', reply: '答复',
  }
  const done = sections.filter((s) => (data.review?.[s] ?? 'pending') !== 'pending')
  const allDone = done.length === sections.length
  const canFinal = allDone && data.status === 'awaiting_review'

  const finalize = async () => {
    setBusy(true)
    setError('')
    try {
      await api.review(data.case_id, 'final', 'approve')
      onChanged()
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  if (data.status === 'completed') {
    return (
      <div className="sticky bottom-0 -mx-5 px-5 py-3 bg-surface-elevated/95 backdrop-blur border-t border-success/30 mt-4">
        <div className="flex items-center justify-center gap-2 text-sm font-medium text-success">
          <Check className="h-4 w-4" />
          案件已归档完成{data.completed_at ? ` · ${fmtTime(data.completed_at)}` : ''}
          {data.review_note && <span className="text-muted font-normal">（{data.review_note}）</span>}
        </div>
      </div>
    )
  }

  if (data.status === 'failed') {
    return (
      <div className="sticky bottom-0 -mx-5 px-5 py-3 bg-surface-elevated/95 backdrop-blur border-t border-danger/30 mt-4">
        <div className="text-sm text-danger text-center">{data.error ?? '执行失败'}</div>
      </div>
    )
  }

  return (
    <div className="sticky bottom-0 -mx-5 px-5 py-3 bg-surface-elevated/95 backdrop-blur border-t border-border mt-4">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          {sections.map((s) => {
            const st = data.review?.[s] ?? 'pending'
            return (
              <span
                key={s}
                className={
                  'text-[11px] rounded-[3px] px-1.5 py-0.5 border font-medium ' +
                  (st === 'pending' ? 'bg-surface text-muted border-border'
                    : st === 'approved' ? 'bg-success-subtle text-success border-success/20'
                    : 'bg-info-subtle text-info border-info/20')
                }
              >
                {labels[s]}
              </span>
            )
          })}
        </div>
        <span className="text-xs text-muted">{allDone ? '各节均已审核' : `待审核 ${sections.length - done.length} 节`}</span>
        {error && <span className="text-xs text-danger truncate">{error}</span>}
        <Button
          variant="success"
          size="md"
          className="ml-auto"
          disabled={!canFinal || busy}
          onClick={finalize}
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          最终放行 · 归档
        </Button>
      </div>
    </div>
  )
}

function SkeletonText() {
  return (
    <div className="space-y-2">
      <div className="h-3.5 w-full rounded shimmer" />
      <div className="h-3.5 w-11/12 rounded shimmer" />
      <div className="h-3.5 w-4/6 rounded shimmer" />
    </div>
  )
}
