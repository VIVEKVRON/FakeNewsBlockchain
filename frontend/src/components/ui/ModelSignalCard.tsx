import React from 'react';
import { AlertTriangle, Activity, Info, BarChart2 } from 'lucide-react';
import type { ArticleClassifierSignal, LIARClassifierSignal } from '@/types/verification';
import { cn } from '@/lib/utils';

interface ModelSignalCardProps {
  isotSignal?: ArticleClassifierSignal;
  liarSignal?: LIARClassifierSignal;
  className?: string;
}

export const ModelSignalCard: React.FC<ModelSignalCardProps> = ({
  isotSignal,
  liarSignal,
  className,
}) => {
  if (!isotSignal && !liarSignal) return null;

  return (
    <div
      className={cn(
        'glass-panel rounded-2xl border-amber-500/30 bg-amber-500/10 dark:bg-amber-950/15 p-5 space-y-4',
        className
      )}
    >
      {/* Section Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-500/20 pb-3">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-amber-600 dark:text-amber-400" />
          <h3 className="font-semibold text-foreground text-sm tracking-wide">
            Experimental ML Signals (ISOT + LIAR)
          </h3>
        </div>
        <span className="rounded-full bg-amber-500/15 border border-amber-500/30 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:text-amber-300">
          Supplementary Stylistic Classifier
        </span>
      </div>

      <div className="text-xs text-slate-700 dark:text-slate-300 flex items-start gap-1.5 leading-relaxed">
        <Info className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <p>
          <strong>Notice:</strong> Machine learning pattern classifiers analyze linguistic styles, not empirical truth.
          Predictions should never be treated as definitive fact verification without matching retrieval evidence.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
        {/* ISOT Signal */}
        {isotSignal && (
          <div className="glass-surface rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                BERT ISOT Article Classifier
              </span>
              <span
                className={cn(
                  'rounded-md px-2 py-0.5 text-xs font-bold font-mono border',
                  isotSignal.prediction === 'REAL'
                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                    : 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30'
                )}
              >
                Pattern: {isotSignal.prediction}
              </span>
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-slate-700 dark:text-slate-300">
                <span>Pattern Confidence:</span>
                <span className="font-mono font-semibold text-foreground">{(isotSignal.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div
                  className={cn(
                    'h-full transition-all duration-300',
                    isotSignal.prediction === 'REAL' ? 'bg-emerald-500' : 'bg-rose-500'
                  )}
                  style={{ width: `${Math.round(isotSignal.confidence * 100)}%` }}
                />
              </div>
            </div>

            {/* Warning callout */}
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/25 p-2.5 text-xs text-amber-900 dark:text-amber-200/90 leading-relaxed flex items-start gap-2">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
              <span>{isotSignal.distribution_shift_warning}</span>
            </div>
          </div>
        )}

        {/* LIAR Signal */}
        {liarSignal && (
          <div className="glass-surface rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                BERT LIAR Claim Classifier
              </span>
              <span className="rounded-md bg-indigo-500/15 border border-indigo-500/30 px-2 py-0.5 text-xs font-bold font-mono text-indigo-700 dark:text-indigo-300 capitalize">
                Signal: {liarSignal.prediction}
              </span>
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-slate-700 dark:text-slate-300">
                <span>Top Label Softmax:</span>
                <span className="font-mono font-semibold text-foreground">{(liarSignal.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-indigo-500 transition-all duration-300"
                  style={{ width: `${Math.round(liarSignal.confidence * 100)}%` }}
                />
              </div>
            </div>

            {/* Disclaimer */}
            <div className="rounded-lg bg-white/60 dark:bg-navy-900/60 border border-border p-2.5 text-xs text-slate-700 dark:text-slate-300 leading-relaxed flex items-start gap-2">
              <BarChart2 className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400 shrink-0 mt-0.5" />
              <span>{liarSignal.disclaimer}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
