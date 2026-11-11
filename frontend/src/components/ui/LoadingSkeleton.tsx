import React, { useState, useEffect } from 'react';
import { Loader2, Cpu, Database } from 'lucide-react';

interface LoadingSkeletonProps {
  message?: string;
}

export const LoadingSkeleton: React.FC<LoadingSkeletonProps> = ({
  message = 'Running CPU-Optimized Evidence Retrieval & NLI Inference...',
}) => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="glass-panel rounded-2xl p-8 text-center space-y-6">
      <div className="flex flex-col items-center justify-center gap-3">
        <div className="relative flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan-500/15 text-brand-blue dark:text-cyan-300 border border-cyan-500/30 shadow-glow-cyan">
          <Loader2 className="h-7 w-7 animate-spin" />
          <Cpu className="absolute h-3.5 w-3.5 text-indigo-500 dark:text-indigo-300" />
        </div>
        <div>
          <h4 className="text-base font-semibold text-foreground">{message}</h4>
          <p className="text-xs text-slate-600 dark:text-slate-400 mt-1 flex items-center justify-center gap-2">
            <Database className="h-3.5 w-3.5 text-brand-cyan" />
            <span>Scanning 126k FEVER Wikipedia vectors on CPU &middot; Elapsed: {elapsed}s</span>
          </p>
        </div>
      </div>

      <div className="space-y-3 max-w-lg mx-auto">
        <div className="h-4 w-3/4 rounded bg-slate-300/60 dark:bg-slate-800/70 mx-auto" />
        <div className="h-3 w-5/6 rounded bg-slate-200/70 dark:bg-slate-800/50 mx-auto" />
        <div className="h-3 w-1/2 rounded bg-slate-200/70 dark:bg-slate-800/50 mx-auto" />
      </div>
    </div>
  );
};
