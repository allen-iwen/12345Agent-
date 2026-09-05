// 轻量 UI 原语（shadcn 风格，手写最小集）
import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from 'react'
import { cn } from './lib/utils'

// ---------- Button ----------
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'success'
  size?: 'sm' | 'md' | 'lg'
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'secondary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center gap-1.5 font-medium rounded-md border transition-colors',
          'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary',
          'disabled:pointer-events-none disabled:opacity-50',
          size === 'sm' && 'h-7 px-2.5 text-xs',
          size === 'md' && 'h-9 px-3.5 text-sm',
          size === 'lg' && 'h-11 px-6 text-base',
          variant === 'primary' && 'bg-primary text-white border-transparent hover:bg-primary-dark',
          variant === 'secondary' && 'bg-surface-elevated text-text border-border hover:border-primary hover:text-primary',
          variant === 'ghost' && 'bg-transparent text-muted border-transparent hover:bg-surface-hover hover:text-text',
          variant === 'danger' && 'bg-danger text-white border-transparent hover:opacity-90',
          variant === 'success' && 'bg-success text-white border-transparent hover:opacity-90',
          className,
        )}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'

// ---------- Card ----------
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('bg-surface-elevated border border-border rounded-lg shadow-[0_1px_2px_rgba(28,36,48,0.04)]', className)}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('flex items-center gap-2 px-4 py-3 border-b border-border', className)} {...props} />
}

export function CardTitle({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn('text-sm font-semibold text-text', className)} {...props} />
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('px-4 py-3', className)} {...props} />
}

// ---------- Badge ----------
export function Badge({
  className,
  tone = 'neutral',
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'primary' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-[3px] px-1.5 py-0.5 text-[11px] font-medium whitespace-nowrap leading-4',
        tone === 'neutral' && 'bg-surface-hover text-muted border border-border',
        tone === 'success' && 'bg-success-subtle text-success border border-success/20',
        tone === 'warning' && 'bg-warning-subtle text-warning border border-warning/25',
        tone === 'danger' && 'bg-danger-subtle text-danger border border-danger/25',
        tone === 'info' && 'bg-info-subtle text-info border border-info/20',
        tone === 'primary' && 'bg-primary-subtle text-primary-dark border border-primary/20',
        className,
      )}
      {...props}
    />
  )
}

// ---------- Field（键值行） ----------
export function Field({ k, v, block, mono }: { k: string; v?: ReactNode; block?: boolean; mono?: boolean }) {
  if (v === undefined || v === null || v === '') return null
  return (
    <div className={cn('flex gap-3 py-1.5', block ? 'flex-col gap-1' : 'items-baseline')}>
      <span className="text-xs text-muted shrink-0 w-20 text-right pt-px">{k}</span>
      <span className={cn('text-sm text-text leading-relaxed flex-1', mono && 'font-mono text-xs')}>{v}</span>
    </div>
  )
}

// ---------- Spinner ----------
export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        'inline-block h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin',
        className,
      )}
    />
  )
}
