import React, { useState } from 'react';
import { AlertCircle, ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LimitationsCalloutProps {
  limitations: string[];
  className?: string;
}

export const LimitationsCallout: React.FC<LimitationsCalloutProps> = ({
  limitations,
  className,
}) => {
  const [open, setOpen] = useState(false);

  if (!limitations || limitations.length === 0) return null;

  return (
    <div
      className={cn(
        'glass-panel rounded-xl p-4 transition-all duration-200',
        className
      )}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="w-full flex items-center justify-between text-left text-xs font-semibold text-slate-700 dark:text-slate-300 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 rounded"
      >
        <div className="flex items-center gap-2">
          <AlertCircle className="h-4 w-4 text-brand-cyan" />
          <span>System Limitations & Epistemological Boundaries ({limitations.length})</span>
        </div>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>

      {open && (
        <ul className="mt-3 space-y-1.5 border-t border-border/70 pt-3 text-xs text-slate-600 dark:text-slate-400 list-disc list-inside leading-relaxed">
          {limitations.map((lim, idx) => (
            <li key={idx} className="pl-1">
              <span className="text-slate-700 dark:text-slate-300">{lim}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
