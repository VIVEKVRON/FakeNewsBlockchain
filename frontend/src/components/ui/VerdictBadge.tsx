import React from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  HelpCircle,
  Split,
  Clock
} from 'lucide-react';
import type { VerdictType } from '@/types/verification';
import { cn } from '@/lib/utils';

interface VerdictBadgeProps {
  verdict: VerdictType;
  size?: 'sm' | 'md' | 'lg';
  showIcon?: boolean;
  showDescription?: boolean;
  className?: string;
}

export const VERDICT_METADATA: Record<
  VerdictType,
  {
    label: string;
    description: string;
    icon: React.ElementType;
    classes: string;
  }
> = {
  GENUINE: {
    label: 'GENUINE · Supported',
    description: 'Strong and relevant supporting evidence, without material unresolved contradictions.',
    icon: ShieldCheck,
    classes: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/35 shadow-glow-emerald',
  },
  LIKELY_GENUINE: {
    label: 'GENUINE · Supported (Legacy)',
    description: 'Historical record corroborated by FEVER Wikipedia knowledge base.',
    icon: ShieldCheck,
    classes: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/35 shadow-glow-emerald',
  },
  FAKE: {
    label: 'FAKE · Refuted',
    description: 'Directly contradicted by subject-matched documentary evidence.',
    icon: ShieldAlert,
    classes: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/35 shadow-glow-rose',
  },
  LIKELY_FAKE: {
    label: 'FAKE · Refuted (Legacy)',
    description: 'Historical record refuted by Wikipedia knowledge base.',
    icon: ShieldAlert,
    classes: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/35 shadow-glow-rose',
  },
  MISLEADING: {
    label: 'MISLEADING · Distorted Framing',
    description: 'Material contextual distortion, omission, or inaccurate attribute framing.',
    icon: AlertTriangle,
    classes: 'bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-500/35',
  },
  PARTIALLY_TRUE: {
    label: 'PARTIALLY TRUE · Mixed Claims',
    description: 'Multiple factual claims combining corroborated assertions with refuted or outdated elements.',
    icon: Split,
    classes: 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 border-indigo-500/35',
  },
  OUTDATED: {
    label: 'OUTDATED · Historically Expired',
    description: 'Historically accurate role or state framed as current despite documented termination or rebrand.',
    icon: Clock,
    classes: 'bg-orange-500/15 text-orange-800 dark:text-orange-300 border-orange-500/35',
  },
  UNVERIFIED: {
    label: 'UNVERIFIED · Insufficient Evidence',
    description: 'Insufficient, irrelevant, or unresolvable evidence; absence of evidence never implies falsehood.',
    icon: HelpCircle,
    classes: 'bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-400/40 dark:border-slate-500/35',
  },
};

export const VerdictBadge: React.FC<VerdictBadgeProps> = ({
  verdict,
  size = 'md',
  showIcon = true,
  showDescription = false,
  className,
}) => {
  const config = VERDICT_METADATA[verdict] || VERDICT_METADATA.UNVERIFIED;
  const Icon = config.icon;

  const sizeClasses = {
    sm: 'text-xs px-2.5 py-0.5 gap-1.5',
    md: 'text-sm px-3 py-1 gap-2',
    lg: 'text-base px-4 py-1.5 gap-2.5 font-semibold',
  };

  const iconSizes = {
    sm: 'w-3.5 h-3.5',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
  };

  return (
    <div className="inline-flex flex-col gap-1">
      <span
        title={config.description}
        className={cn(
          'inline-flex items-center rounded-full border backdrop-blur-sm transition-all duration-150 font-medium tracking-wide w-fit',
          config.classes,
          sizeClasses[size],
          className
        )}
      >
        {showIcon && <Icon className={cn(iconSizes[size], 'shrink-0')} />}
        <span>{config.label}</span>
      </span>
      {showDescription && (
        <span className="text-xs text-slate-600 dark:text-slate-400 leading-snug">
          {config.description}
        </span>
      )}
    </div>
  );
};
