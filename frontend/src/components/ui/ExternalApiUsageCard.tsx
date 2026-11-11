import React from 'react';
import {
  Activity,
  AlertTriangle,
  Database,
  RefreshCw,
  ShieldAlert,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import type { GdeltUsageStatus } from '@/types/verification';
import { cn } from '@/lib/utils';

interface ExternalApiUsageCardProps {
  usage?: GdeltUsageStatus | null;
  googleAvailable?: boolean | null;
  onRefresh?: () => void;
  refreshing?: boolean;
  compact?: boolean;
  className?: string;
}

export const ExternalApiUsageCard: React.FC<ExternalApiUsageCardProps> = ({
  usage,
  googleAvailable,
  onRefresh,
  refreshing = false,
  compact = false,
  className,
}) => {
  if (!usage) {
    return (
      <div
        className={cn(
          'glass-panel rounded-2xl p-4 text-xs text-slate-600 dark:text-slate-400',
          className
        )}
      >
        External API quota telemetry will populate after loading backend usage state.
      </div>
    );
  }

  const limit = Math.max(1, usage.allowance_limit || 200);
  const used = Math.max(0, usage.requests_used || 0);
  const remaining = Math.max(0, usage.requests_remaining ?? Math.max(0, limit - used));
  const pct = Math.min(100, Math.round((used / limit) * 100));
  const resolvedGoogleAvail =
    googleAvailable ?? usage.google_fact_check_available ?? null;

  const progressColor = usage.limit_reached
    ? 'bg-rose-500'
    : usage.warning_active
    ? 'bg-amber-500'
    : 'bg-brand-blue';

  return (
    <div
      className={cn(
        'glass-panel rounded-2xl',
        compact ? 'p-4 space-y-3' : 'p-5 space-y-4',
        className
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-brand-blue" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">
            External API Usage &amp; Shared GDELT Quota
          </h4>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {resolvedGoogleAvail !== null && (
            <span
              className={cn(
                'inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium',
                resolvedGoogleAvail
                  ? 'bg-emerald-50 dark:bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/30'
                  : 'bg-slate-100 dark:bg-slate-800/70 text-slate-700 dark:text-slate-300 border-border'
              )}
            >
              {resolvedGoogleAvail ? (
                <CheckCircle2 className="h-3 w-3" />
              ) : (
                <XCircle className="h-3 w-3" />
              )}
              <span>
                Google Fact Check:{' '}
                {resolvedGoogleAvail ? 'Configured (Backend)' : 'Not Configured'}
              </span>
            </span>
          )}

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={refreshing}
              className="inline-flex items-center gap-1 rounded-lg border border-border bg-slate-100/80 dark:bg-slate-900/50 px-2.5 py-1 text-[11px] font-medium text-foreground hover:border-brand-blue/50 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />
              <span>Sync Usage</span>
            </button>
          )}
        </div>
      </div>

      {/* Warning / Exhaustion / Tracker Unavailable Banners */}
      {!usage.tracker_available && (
        <div className="flex items-start gap-2 rounded-xl border border-rose-300 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-950/30 p-3 text-xs text-rose-900 dark:text-rose-200">
          <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-rose-600 dark:text-rose-400" />
          <span>
            Shared GDELT SQLite quota tracker is currently unavailable. Outbound GDELT calls fail closed to protect the request budget.
          </span>
        </div>
      )}

      {usage.limit_reached ? (
        <div className="flex items-start gap-2 rounded-xl border border-rose-300 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-950/30 p-3 text-xs text-rose-900 dark:text-rose-200">
          <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-rose-600 dark:text-rose-400" />
          <span>
            <strong>Hard GDELT Request Cap Reached ({used} / {limit}):</strong>{' '}
            Outbound GDELT HTTP requests are blocked across Live News Monitor, Text Verify, and Article Verify. Cached external lookups and local/RSS/Wikipedia pipelines continue operating normally.
          </span>
        </div>
      ) : usage.warning_active ? (
        <div className="flex items-start gap-2 rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs text-amber-900 dark:text-amber-200">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
          <span>
            <strong>GDELT Budget Low ({remaining} remaining):</strong>{' '}
            Within the warning threshold ({usage.warning_threshold} requests left of {limit} total shared budget).
          </span>
        </div>
      ) : null}

      {/* Progress & Counters */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="font-medium text-slate-700 dark:text-slate-300">
            Shared GDELT Allowance (Live News + Text + Article)
          </span>
          <span className="font-mono font-bold text-foreground">
            {used} / {limit} used ({remaining} left)
          </span>
        </div>
        <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div
            className={cn('h-full rounded-full transition-all duration-300', progressColor)}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Detailed Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
        <div className="rounded-xl border border-border bg-slate-100/70 dark:bg-slate-900/40 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-slate-600 dark:text-slate-400">
            Requests Used
          </div>
          <div className="font-mono font-bold text-foreground mt-0.5">{used}</div>
        </div>
        <div className="rounded-xl border border-border bg-slate-100/70 dark:bg-slate-900/40 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-slate-600 dark:text-slate-400">
            Remaining
          </div>
          <div className="font-mono font-bold text-foreground mt-0.5">{remaining}</div>
        </div>
        <div className="rounded-xl border border-border bg-slate-100/70 dark:bg-slate-900/40 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-slate-600 dark:text-slate-400">
            Cache Hits (0 Cost)
          </div>
          <div className="font-mono font-bold text-emerald-700 dark:text-emerald-400 mt-0.5">
            {usage.cache_hits ?? 0}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-slate-100/70 dark:bg-slate-900/40 px-3 py-2">
          <div className="text-[10px] uppercase tracking-wider text-slate-600 dark:text-slate-400">
            Failed (Counted)
          </div>
          <div className="font-mono font-bold text-foreground mt-0.5">
            {usage.failed_requests ?? 0}
          </div>
        </div>
      </div>

      {/* Accounting Rule & Last Activity Footer */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-1 border-t border-border text-[11px] text-slate-600 dark:text-slate-400">
        <span className="flex items-start gap-1.5 leading-relaxed">
          <Database className="h-3.5 w-3.5 shrink-0 mt-0.5 text-brand-cyan" />
          <span>{usage.accounting_rule}</span>
        </span>
        {usage.last_status && (
          <span className="font-mono shrink-0 text-[10px] rounded bg-slate-100 dark:bg-slate-800/80 px-2 py-0.5 border border-border text-slate-700 dark:text-slate-300">
            Last: {usage.last_source || 'app'} &middot; {usage.last_status}
          </span>
        )}
      </div>
    </div>
  );
};
