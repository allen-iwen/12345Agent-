// 后端 API 客户端（VITE_API_BASE_URL 可覆盖，默认本机 8000）
const BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export type SectionStatus = 'pending' | 'approved' | 'modified'

export interface WikiEntry {
  slug: string
  title: string
  category: string
  body_md: string
  tags: string[]
  version: number
  status: 'draft' | 'published'
  author: string
  reviewer: string
  source_case_id: string
  created_at: string
  updated_at: string
  excerpt?: string
  revisions?: { id: number; slug: string; version: number; title: string; editor: string; note: string; created_at: string }[]
}

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
  // 流转状态（工单在业务流程中的位置）
  flow_state?: string
  flow_label?: string
  flow_history?: {
    id: number; from_state: string | null; to_state: string; from_label: string; to_label: string
    actor: string; role: string; action: string; note: string; created_at: string
  }[]
  // 证据附件（图片/音频）及其视觉分析结论
  attachments?: {
    id: string
    kind: string
    filename: string
    mime: string
    size: number
    created_at: string
    vision: {
      available: boolean
      provider?: string
      model?: string
      hazard?: boolean
      hazard_type?: string
      severity?: string
      summary?: string
      confidence?: number
      elements?: Record<string, string>
      note?: string
    } | null
  }[]
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
    overdue?: { level: string; message: string; suggestion: string }
    suggestions: string[]
    has_governance_alert: boolean
  } | null
  // 支柱四：答复合规审查
  reply_audit?: {
    risk_level: '高' | '中' | '低' | '无'
    risk_note: string
    findings: { type: string; label: string; severity: 'high' | 'medium' | 'low'; quote: string; index: number; suggestion: string; source: string }[]
    rewrite_hint: string[]
    checked_rules: number
    llm_reviewed: boolean
    basis: { name: string; clause: string }
  } | null
  // 支柱五：办理时限倒计时
  deadline?: {
    level: string
    label: string
    due_at: string
    mode: string
    total_hours: number
    remaining_hours: number
    state: '正常' | '临期' | '超期' | '已办结'
    near_due_threshold_hours: number
    basis: { name: string; clause: string }
    commitment_note: string
    notes: string[]
    supervision?: string
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

// ---- 会话令牌（轻量 RBAC）：仅存浏览器本地，随请求头携带 ----
const TOKEN_KEY = 'dsh_token'
export const auth = {
  token: () => localStorage.getItem(TOKEN_KEY) || '',
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = auth.token()
  const res = await fetch(BASE + path, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
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
    throw new Error(`${res.status === 401 ? '未登录或会话已过期：' : ''}${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => req<{ status: string }>('/health'),
  // 认证与审计（轻量 RBAC）
  authStatus: () => req<{
    enabled: boolean
    users: number
    audit_records: number
    roles: Record<string, string>
    session_ttl_hours: number
  }>('/api/auth/status'),
  me: () => req<{ actor: string; role: string; role_label: string; username: string; rbac_enabled: boolean }>('/api/auth/me'),
  login: (username: string, password: string) =>
    req<{ token: string; expires_at: string; user: { username: string; display_name: string; role: string; role_label: string; org: string } }>(
      '/api/auth/login',
      { method: 'POST', body: JSON.stringify({ username, password }) },
    ),
  logout: () => req<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  listUsers: () => req<{ id: number; username: string; display_name: string; role: string; role_label: string; org: string; active: number }[]>('/api/auth/users'),
  createUser: (payload: { username: string; password: string; display_name?: string; role: string; org?: string }) =>
    req<{ ok: boolean; id: number; username: string }>('/api/auth/users', { method: 'POST', body: JSON.stringify(payload) }),
  auditLog: (params: { limit?: number; target_id?: string; actor?: string } = {}) => {
    const qs = new URLSearchParams()
    if (params.limit) qs.set('limit', String(params.limit))
    if (params.target_id) qs.set('target_id', params.target_id)
    if (params.actor) qs.set('actor', params.actor)
    const suffix = qs.toString() ? `?${qs}` : ''
    return req<{ total: number; records: { id: number; actor: string; role: string; action: string; target_type: string; target_id: string; detail: string; ip: string; created_at: string }[] }>(`/api/auth/audit${suffix}`)
  },
  createCase: (text: string, source_channel = '直接来电（呼入）', attachment_ids: string[] = []) =>
    req<CaseView>('/api/cases', { method: 'POST', body: JSON.stringify({ text, source_channel, attachment_ids }) }),
  // 证据附件（现场照片 → 视觉分析）
  uploadAttachment: async (file: File, kind: 'image' | 'audio' = 'image', contextText = '') => {
    const form = new FormData()
    form.append('file', file)
    form.append('kind', kind)
    form.append('context_text', contextText)
    const res = await fetch(BASE + '/api/attachments', { method: 'POST', body: form })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const body = await res.json()
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      } catch { /* ignore */ }
      throw new Error(`图片上传失败：${detail}`)
    }
    return (await res.json()) as {
      id: string
      kind: string
      filename: string
      size: number
      vision: {
        available: boolean
        hazard?: boolean
        hazard_type?: string
        severity?: string
        summary?: string
        confidence?: number
        elements?: Record<string, string>
        note?: string
      } | null
      vision_available: boolean
    }
  },
  deleteAttachment: (id: string) => req<{ ok: boolean }>(`/api/attachments/${id}`, { method: 'DELETE' }),
  attachmentRawUrl: (id: string) => `${BASE}/api/attachments/${id}/raw`,
  visionStatus: () => req<{ available: boolean; providers: string[]; max_bytes: number }>('/api/attachments/status'),
  // 工单流转（状态机 + 看板）
  flowStates: () => req<{
    states: { key: string; label: string }[]
    main_flow: string[]
    roles: string[]
    transitions: { from: string; to: string; from_label: string; to_label: string; action: string; description: string; required_roles: string[] }[]
  }>('/api/flow/states'),
  board: () => req<{
    groups: {
      state: string
      label: string
      count: number
      items: {
        case_id: string; title: string; status: string; flow_state: string; flow_label: string
        urgency_level: string; created_at: string; updated_at: string
        deadline_state: string; due_at: string; remaining_hours: number
      }[]
    }[]
    counts: Record<string, number>
    total_cases: number
    listed: number
  }>('/api/flow/board'),
  caseFlow: (caseId: string) => req<{
    case_id: string
    flow_state: string
    flow_label: string
    next_actions: { to: string; to_label: string; action: string; description: string; allowed: boolean; required_roles: string[] }[]
    history: { id: number; from_state: string | null; to_state: string; from_label: string; to_label: string; actor: string; role: string; action: string; note: string; created_at: string }[]
  }>(`/api/cases/${caseId}/flow`),
  transition: (caseId: string, to: string, opts: { note?: string; actor?: string; role?: string; expectedFrom?: string } = {}) =>
    req<{ ok: boolean; from_label: string; to_label: string; action: string }>(`/api/cases/${caseId}/transition`, {
      method: 'POST',
      body: JSON.stringify({
        to,
        note: opts.note ?? '',
        actor: opts.actor ?? '坐席（演示）',
        role: opts.role ?? 'dispatcher',
        expected_from: opts.expectedFrom ?? null,
      }),
    }),
  // 统计（交叉复核 / 时限督办）
  reviewStats: () => req<{
    config: { enabled: boolean; model: string; base_url: string; note: string }
    checked_cases: number
    agreed: number
    diverged: number
    agreement_rate: number | null
    divergence_rate: number | null
    human_gated: number
    human_gate_rate: number | null
    divergence_samples: { case_id: string; title: string; primary: string; secondary: string; secondary_name: string; secondary_model: string }[]
    note: string
  }>('/api/stats/review'),
  deadlineStats: () => req<{
    total: number
    buckets: Record<string, number>
    urgent: { case_id: string; title: string; level: string; state: string; due_at: string; remaining_hours: number; supervision: string }[]
    note: string
  }>('/api/stats/deadlines'),
  // 知识词条（wiki）
  wikiList: (params: { category?: string; status?: string; q?: string } = {}) => {
    const qs = new URLSearchParams()
    if (params.category) qs.set('category', params.category)
    if (params.status) qs.set('status', params.status)
    if (params.q) qs.set('q', params.q)
    const suffix = qs.toString() ? `?${qs}` : ''
    return req<{
      counts: { by_status: Record<string, number>; by_category: Record<string, number>; total: number }
      categories: string[]
      items: WikiEntry[]
    }>(`/api/wiki${suffix}`)
  },
  wikiGet: (slug: string) => req<WikiEntry>(`/api/wiki/${slug}`),
  wikiSave: (payload: { slug: string; title: string; body_md: string; category: string; tags?: string[]; note?: string }) =>
    req<{ ok: boolean; slug: string; version: number }>('/api/wiki', { method: 'POST', body: JSON.stringify(payload) }),
  wikiPublish: (slug: string, note = '') =>
    req<{ ok: boolean; slug: string; status: string }>(`/api/wiki/${slug}/publish`, { method: 'POST', body: JSON.stringify({ note }) }),
  wikiUnpublish: (slug: string) =>
    req<{ ok: boolean; slug: string; status: string }>(`/api/wiki/${slug}/unpublish`, { method: 'POST' }),
  wikiDistill: (caseId: string, category = '案例经验') =>
    req<{ ok: boolean; slug: string; version: number; preview: string }>(`/api/wiki/distill/${caseId}`, {
      method: 'POST',
      body: JSON.stringify({ category }),
    }),
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
