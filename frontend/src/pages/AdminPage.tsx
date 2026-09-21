// 账号与审计：登录、当前身份、账号管理（管理员）、操作审计查询
import { useState } from 'react'
import useSWR from 'swr'
import { AlertTriangle, Loader2, LogIn, LogOut, Plus, ShieldCheck } from 'lucide-react'
import { api, auth } from '../lib/api'
import { Badge, Button, Card, CardBody, CardHeader, CardTitle, Spinner } from '../ui'
import { cn } from '../lib/utils'

export function AdminPage() {
  const { data: status, mutate: mutateStatus } = useSWR(['auth-status'], () => api.authStatus(), { refreshInterval: 20000 })
  const { data: me, mutate: mutateMe, error: meError } = useSWR(['me'], () => api.me(), { shouldRetryOnError: false })

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const loggedIn = !!me && !meError
  const canViewAudit = loggedIn && ['admin', 'supervisor', 'reviewer'].includes(me!.role)

  const { data: audit } = useSWR(
    canViewAudit || (status && !status.enabled) ? ['audit'] : null,
    () => api.auditLog({ limit: 80 }),
    { refreshInterval: 15000 },
  )
  const { data: users } = useSWR(
    loggedIn && me!.role === 'admin' ? ['users'] : null,
    () => api.listUsers(),
  )

  const doLogin = async () => {
    setBusy(true); setErr(''); setMsg('')
    try {
      const r = await api.login(username.trim(), password)
      auth.set(r.token)
      setMsg(`登录成功：${r.user.display_name}（${r.user.role_label}）`)
      setPassword('')
      await Promise.all([mutateMe(), mutateStatus()])
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const doLogout = async () => {
    setBusy(true)
    try {
      await api.logout()
    } catch { /* 忽略 */ }
    auth.clear()
    setMsg('已退出登录')
    await Promise.all([mutateMe(), mutateStatus()])
    setBusy(false)
  }

  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '', role: 'agent', org: '' })
  const createUser = async () => {
    setBusy(true); setErr(''); setMsg('')
    try {
      await api.createUser(newUser)
      setMsg(`已创建账号 ${newUser.username}（${newUser.role}）`)
      setNewUser({ username: '', password: '', display_name: '', role: 'agent', org: '' })
      await mutateStatus()
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="max-w-[1080px] mx-auto p-5 pb-16">
        <header className="mb-5 pb-3 border-b border-border">
          <h1 className="text-base font-semibold tracking-tight">账号与操作审计</h1>
          <p className="text-xs text-muted mt-1">
            轻量 RBAC：坐席 / 派单员 / 审核员 / 部门用户 / 管理员 / 监督员六类角色，关键操作留痕可追责。
            {status && (status.enabled
              ? '当前为鉴权已启用模式。'
              : '当前为演示态（未启用鉴权）：所有操作放行，但审计仍在记录。')}
          </p>
        </header>

        {err && <div className="mb-3 text-xs text-danger bg-danger-subtle border border-danger/20 rounded-md p-2.5">{err}</div>}
        {msg && <div className="mb-3 text-xs text-success bg-success-subtle border border-success/20 rounded-md p-2.5">{msg}</div>}

        <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-4">
          {/* 左：身份 */}
          <Card className="self-start">
            <CardHeader>
              <ShieldCheck className="h-4 w-4 text-muted-light" />
              <CardTitle>当前身份</CardTitle>
              <span className="ml-auto text-[11px] text-muted">
                {status ? `${status.users} 个账号｜${status.audit_records} 条审计` : '…'}
              </span>
            </CardHeader>
            <CardBody className="space-y-2.5">
              {loggedIn ? (
                <>
                  <div className="flex items-center gap-2">
                    <Badge tone="primary">{me!.role_label}</Badge>
                    <span className="text-sm font-medium">{me!.actor}</span>
                    <span className="text-[11px] text-muted font-mono ml-auto">{me!.username}</span>
                  </div>
                  <div className="text-[11px] text-muted">
                    {status?.enabled ? '鉴权已启用：关键操作按角色校验' : '演示态：未启用鉴权（守卫放行）'}
                  </div>
                  <Button size="sm" onClick={doLogout} disabled={busy}>
                    <LogOut className="h-3.5 w-3.5" />
                    退出登录
                  </Button>
                </>
              ) : (
                <>
                  <div className="text-xs text-muted">
                    {status?.enabled ? '请输入账号密码登录（首次启动的账号见后端启动日志）' : '未启用鉴权，可直接查看审计'}
                  </div>
                  <input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    placeholder="账号"
                    className="w-full h-8 text-sm rounded-md border border-border bg-surface px-2.5 focus:outline-none focus:border-primary"
                  />
                  <input
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && doLogin()}
                    type="password"
                    placeholder="密码"
                    className="w-full h-8 text-sm rounded-md border border-border bg-surface px-2.5 focus:outline-none focus:border-primary"
                  />
                  <Button size="sm" variant="primary" onClick={doLogin} disabled={busy || !username || !password}>
                    {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <LogIn className="h-3.5 w-3.5" />}
                    登录
                  </Button>
                </>
              )}

              {status && (
                <div className="pt-2 border-t border-border text-[11px] text-muted space-y-0.5">
                  <div className="font-medium text-text-secondary">角色权限</div>
                  {Object.entries(status.roles).map(([k, v]) => (
                    <div key={k} className="flex justify-between">
                      <span className="font-mono text-muted-light">{k}</span>
                      <span>{v}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>

          {/* 右：账号管理 + 审计 */}
          <div className="space-y-4">
            {loggedIn && me!.role === 'admin' && (
              <Card>
                <CardHeader>
                  <CardTitle>账号管理（管理员）</CardTitle>
                  <span className="text-[11px] text-muted ml-auto">仅管理员可新建账号</span>
                </CardHeader>
                <CardBody className="space-y-2">
                  <div className="grid grid-cols-2 gap-2">
                    <input value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                           placeholder="账号" className="h-7 text-xs rounded-md border border-border bg-surface px-2 focus:outline-none focus:border-primary" />
                    <input value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                           placeholder="初始密码（≥6 位）" type="password" className="h-7 text-xs rounded-md border border-border bg-surface px-2 focus:outline-none focus:border-primary" />
                    <input value={newUser.display_name} onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })}
                           placeholder="姓名" className="h-7 text-xs rounded-md border border-border bg-surface px-2 focus:outline-none focus:border-primary" />
                    <select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                            className="h-7 text-xs rounded-md border border-border bg-surface px-2 focus:outline-none focus:border-primary">
                      {Object.entries(status?.roles ?? {}).map(([k, v]) => (
                        <option key={k} value={k}>{v}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" onClick={createUser} disabled={busy || !newUser.username || newUser.password.length < 6}>
                      <Plus className="h-3.5 w-3.5" />
                      新建账号
                    </Button>
                    <span className="text-[11px] text-muted-light">密码使用 pbkdf2-SHA256 + 随机盐，不明文存储</span>
                  </div>
                  {(users ?? []).length > 0 && (
                    <div className="pt-2 border-t border-border space-y-1">
                      {(users ?? []).map((u) => (
                        <div key={u.id} className="flex items-center gap-2 text-[11px]">
                          <span className="font-mono text-muted-light w-20">{u.username}</span>
                          <span className="text-text-secondary w-24">{u.display_name}</span>
                          <Badge>{u.role_label}</Badge>
                          <span className="text-muted-light ml-auto truncate">{u.org || '—'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </CardBody>
              </Card>
            )}

            <Card>
              <CardHeader>
                <CardTitle>操作审计</CardTitle>
                <span className="text-[11px] text-muted ml-auto">
                  {audit ? `共 ${audit.total} 条` : canViewAudit || (status && !status.enabled) ? '…' : '需登录（管理员/监督员/审核员）'}
                </span>
              </CardHeader>
              <CardBody>
                {!audit && <div className="flex items-center gap-2 text-xs text-muted"><Spinner />加载审计…</div>}
                {audit && audit.records.length === 0 && <div className="text-xs text-muted">暂无审计记录</div>}
                {audit && audit.records.length > 0 && (
                  <div className="divide-y divide-border rounded-md border border-border max-h-[520px] overflow-y-auto">
                    {audit.records.map((r) => (
                      <div key={r.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-3 py-2">
                        <span className="font-mono text-[10px] text-muted-light">{r.created_at.slice(5, 19).replace('T', ' ')}</span>
                        <span className={cn('text-[11px] font-medium',
                          r.action.includes('失败') || r.action.includes('被拒') ? 'text-danger' : 'text-text-secondary')}>
                          {r.action}
                        </span>
                        <span className="text-[11px] text-muted">{r.actor}（{r.role || '—'}）</span>
                        {r.target_type && (
                          <span className="text-[10px] text-muted-light font-mono">
                            {r.target_type}:{r.target_id.slice(0, 12)}
                          </span>
                        )}
                        {r.detail && <span className="text-[10px] text-muted-light truncate max-w-[320px]">{r.detail}</span>}
                      </div>
                    ))}
                  </div>
                )}
                {!status?.enabled && (
                  <div className="mt-2 flex items-start gap-1.5 text-[11px] text-muted">
                    <AlertTriangle className="h-3.5 w-3.5 text-warning shrink-0 mt-px" />
                    演示态下守卫放行，但每次关键操作仍写入审计——启用鉴权只需在后端 .env 设 RBAC_ENABLED=true 并重启。
                  </div>
                )}
              </CardBody>
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
