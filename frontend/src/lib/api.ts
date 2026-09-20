// 后端 API 客户端（VITE_API_BASE_URL 可覆盖，默认本机 8000）
const BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export type SectionStatus = 'pending' | 'approved' | 'modified'

export interface CaseView {
  case_id: string
  raw_text: string
  source_channel: string
  status: 'processing' | 'awaiting_review' | 'needs_clarification' | 'completed' | 'failed'
  understanding: {
    summary: string
    elements: Record<string, string>
    urgent: boolean
    repeat_request: boolean
    needs_clarification: boolean
    missing_fields: string[]
    manual_action: string | null
  } | null
  work_order: {
    title: string
    region: string
    requester: string
    contact: string
    location: string
    occurrence_time: string
    event_description: string
    handling_request: string
  } | null
  classification: {
    category_code: string | null
    category_name: string | null
    confidence: number
    reason: string
    candidates: { code: string; name: string; score: number; reason: string }[]
    needs_human_judgment: boolean
    judgment_note: string
  } | null
  routing: {
    departments: { name: string; role: string; reason: string }[]
    primary: string | null
    note: string
    needs_human_judgment: boolean
    judgment_note: string
    // 支柱一：属地+部门双维派单决策
    dispatch_path?: string
    primary_kind?: string
    evidence_chain?: { type: string; source: string; detail: string }[]
    return_risk?: string
    rule_primary?: string
    rule_llm_agreement?: boolean
  } | null
  reply_draft: {
    reply_text: string
    tone: string
    disclaimer: string
    followup_script: string
    policy_refs: string[]
  } | null
  review: Record<string, SectionStatus>
  review_note: string
  clarification_context: string[]
  created_at: string
  updated_at: string
  completed_at: string
  error: string | null
  qc_checks: { item: string; passed: boolean; detail: string }[]
  early_warning: {
    kind: string
    message: string
    related: { case_id: string; title: string; created_at: string; status: string; shared_place?: string }[]
    window_days: number
    total: number
  } | null
  agent_seconds: number | null
  // 支柱二：急件识别与办理时限分级
  urgency?: {
    level: '特急' | '紧急' | '一般'
    label: string
    limit_hint: string
    actions: string[]
    signals: string[]
    basis: { name: string; clause: string }
    escalated_by_understanding: boolean
  } | null
  // 支柱三：诉求治理建议包
  governance?: {
    aggregation?: { kind: string; message: string; total: number; window_days: number; suggestion: string; related: { case_id: string; title: string; created_at: string; shared_place?: string }[] }
    repeat?: { is_repeat: boolean; markers: string[]; related_count: number; message: string }
    return_risk?: { level: string; message: string; suggestion: string }
    suggestions: string[]
    has_governance_alert: boolean
  } | null
}

export interface StatsView {
  official_total: number
  official_by_category: Record<string, number>
  demo_total: number
  demo_by_category: Record<string, number>
  demo_urgent: number
  demo_repeat: number
  demo_completed: number
  efficiency: {
    human_baseline_min_per_case: number
    cases_measured: number
    agent_minutes_total: number
    human_minutes_estimated: number
    minutes_saved_est: number
  }
}

export interface PolicyDoc {
  upload_id: string
  source_name: string
  publisher: string
  category_name: string
  chunks: number
  chars: number
  indexed_at: string
}

export interface DepartmentInfo {
  name: string
  categories: string[]
  co_departments: string[]
  keywords: string[]
  responsibilities: string
}

export interface RunRecord {
  id: number
  node: string
  prompt_kind: string
  status: string
  input_json: unknown
  output_json: unknown
  duration_ms: number | null
  error: string | null
  created_at: string
}

export interface KnowledgeOrder {
  source_id: string
  category: string
  title: string
  request_content: string
  handling_departments: string[]
  reply_content: string
  region: string
  accepted_at?: string
  source_channel?: string
}

export interface SimilarHit {
  source_id: string
  category: string
  title: string
  request_content: string
  handling_departments: string[]
  reply_content: string
  region: string
  score: number
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* ignore */
    }
    throw new Error(`API ${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => req<{ status: string }>('/health'),
  createCase: (text: string, source_channel = '直接来电（呼入）') =>
    req<CaseView>('/api/cases', { method: 'POST', body: JSON.stringify({ text, source_channel }) }),
  listCases: () => req<CaseView[]>('/api/cases?limit=30'),
  getCase: (id: string) => req<CaseView>(`/api/cases/${id}`),
  review: (
    id: string,
    section: 'work_order' | 'classification' | 'routing' | 'reply' | 'final',
    action: 'approve' | 'modify',
    payload?: object,
    note = '',
  ) =>
    req<CaseView>(`/api/cases/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ section, action, payload, note }),
    }),
  clarify: (id: string, answers: string) =>
    req<CaseView>(`/api/cases/${id}/clarify`, { method: 'POST', body: JSON.stringify({ answers }) }),
  // 运行轨迹
  listRuns: (caseId: string) => req<{ case_id: string; runs: RunRecord[] }>(`/api/runs/cases/${caseId}`),
  // 录音转写
  transcribeAudio: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(BASE + '/api/asr', { method: 'POST', body: form })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const body = await res.json()
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      } catch { /* ignore */ }
      throw new Error(`转写失败：${detail}`)
    }
    return (await res.json()) as {
      filename: string
      text: string
      text_clean: string
      clean_applied: boolean
      clean_note: string
      clean_changes: string[]
      source: 'xfyun' | 'sensevoice'
      latency_ms: number
      segments: number
      fallback_note: string
    }
  },
  // 知识库
  listOrders: (q = '', category = '') => {
    const p = new URLSearchParams()
    if (q) p.set('q', q)
    if (category) p.set('category', category)
    return req<{ total: number; orders: KnowledgeOrder[] }>(`/api/knowledge/orders?${p}`)
  },
  searchSimilar: (text: string, topK = 3) => {
    const p = new URLSearchParams({ text, top_k: String(topK) })
    return req<{ query: string; hits: SimilarHit[] }>(`/api/knowledge/search?${p}`)
  },
  stats: () => req<StatsView>('/api/knowledge/stats'),
  // 部门职能目录
  listDepartments: () =>
    req<{ notice: string; departments: DepartmentInfo[] }>('/api/knowledge/departments'),
  // 政策库
  listPolicies: () => req<{ documents: PolicyDoc[] }>('/api/policies'),
  uploadPolicy: async (file: File, sourceName: string, publisher: string, categoryName: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('source_name', sourceName)
    form.append('publisher', publisher)
    form.append('category_name', categoryName)
    const res = await fetch(BASE + '/api/policies', { method: 'POST', body: form })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const body = await res.json()
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      } catch { /* ignore */ }
      throw new Error(`入库失败：${detail}`)
    }
    return (await res.json()) as { upload_id: string; chunks: number; source_name: string }
  },
  deletePolicy: (id: string) => req<{ deleted: string }>(`/api/policies/${id}`, { method: 'DELETE' }),
}
