import React, { useState } from 'react';
import {
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Layers,
  CheckCircle,
  XCircle,
  HelpCircle,
  Calendar,
  Globe,
  Database
} from 'lucide-react';
import type { EvidenceSentence } from '@/types/verification';
import { cn } from '@/lib/utils';

interface EvidenceCardProps {
  evidence: EvidenceSentence;
  index: number;
}

export const EvidenceCard: React.FC<EvidenceCardProps> = ({ evidence, index }) => {
  const [expanded, setExpanded] = useState(false);

  // Prefer explicit URL from backend provenance, fallback to Wikipedia article URL
  const wikiUrl =
    evidence.source_url ||
    `https://en.wikipedia.org/wiki/${encodeURIComponent(evidence.page.replace(/ /g, '_'))}`;

  const supportsProb = evidence.nli_probabilities?.supports ?? evidence.nli_probabilities?.SUPPORTS ?? 0;
  const refutesProb = evidence.nli_probabilities?.refutes ?? evidence.nli_probabilities?.REFUTES ?? 0;
  const neiProb = evidence.nli_probabilities?.not_enough_info ?? evidence.nli_probabilities?.['NOT ENOUGH INFO'] ?? 0;

  const isLiveWiki =
    evidence.source_type === 'wikipedia_live' || evidence.source_type === 'local_wikipedia';
  const sourceLabelMap: Record<string, string> = {
    official_record: 'Official First-Party Record',
    institutional_document: 'Official Institutional Document',
    wikipedia_live: 'Wikipedia Live API',
    local_wikipedia: 'Wikipedia Local Index',
    google_fact_check: 'Google Fact Check Review',
    gdelt: 'GDELT News Coverage',
    rss: 'RSS News Feed',
    fever_local: 'Local FEVER Corpus',
  };
  const sourceLabel = sourceLabelMap[evidence.source_type || 'fever_local'] || 'Local FEVER Corpus';

  const nliConfig = {
    SUPPORTS: {
      label: 'SUPPORTS',
      icon: CheckCircle,
      badge: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30',
    },
    REFUTES: {
      label: 'REFUTES',
      icon: XCircle,
      badge: 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30',
    },
    'NOT ENOUGH INFO': {
      label: 'NOT ENOUGH INFO',
      icon: HelpCircle,
      badge: 'bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-400/35 dark:border-slate-500/30',
    },
  }[evidence.nli_label] || {
    label: evidence.nli_label,
    icon: HelpCircle,
    badge: 'bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-400/35 dark:border-slate-500/30',
  };

  const roleBadge =
    evidence.evidence_role === 'supporting'
      ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
      : evidence.evidence_role === 'contradicting'
      ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30'
      : 'glass-surface text-slate-600 dark:text-slate-400';

  const NliIcon = nliConfig.icon;

  return (
    <div className="glass-panel rounded-xl p-4 transition-all duration-200 hover:border-cyan-400/40">
      <div className="flex flex-col gap-3">
        {/* Top Header: Rank, Page Link, Role, NLI Badge, Similarity */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-brand-blue/15 text-xs font-semibold text-brand-blue dark:text-cyan-300">
              #{index + 1}
            </span>
            <a
              href={wikiUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center gap-1.5 font-medium text-foreground hover:text-brand-blue dark:hover:text-cyan-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 rounded"
              title="Open source article"
            >
              <span>{evidence.page}</span>
              <ExternalLink className="h-3.5 w-3.5 text-slate-500 group-hover:text-brand-blue dark:group-hover:text-cyan-300 transition-colors" />
            </a>
            <span className="text-xs text-slate-600 dark:text-slate-400 font-mono">
              [sent: {evidence.sentence_id}]
            </span>
            {evidence.evidence_role && (
              <span className={cn('rounded-md border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider', roleBadge)}>
                {evidence.evidence_role}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Calibrated NLI Label */}
            <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium', nliConfig.badge)}>
              <NliIcon className="h-3 w-3" />
              <span>{nliConfig.label}</span>
              <span className="font-mono opacity-80">({(evidence.nli_confidence * 100).toFixed(1)}%)</span>
            </span>

            {/* Retrieval Similarity */}
            <div className="glass-surface flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs">
              <span className="text-slate-600 dark:text-slate-400">Sim:</span>
              <span className="font-mono font-semibold text-brand-blue dark:text-cyan-300">
                {evidence.retrieval_similarity.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Source & Publication / Revision Date Provenance Row */}
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-600 dark:text-slate-400">
          <span className="inline-flex items-center gap-1 font-medium text-slate-700 dark:text-slate-300">
            {isLiveWiki || evidence.source_type === 'gdelt' || evidence.source_type === 'rss' ? (
              <Globe className="h-3 w-3 text-cyan-600 dark:text-cyan-400" />
            ) : (
              <Database className="h-3 w-3 text-indigo-600 dark:text-indigo-400" />
            )}
            <span>{sourceLabel}</span>
          </span>
          {evidence.publication_date && (
            <span className="inline-flex items-center gap-1 font-mono">
              <Calendar className="h-3 w-3 text-slate-500" />
              <span>Revision/Date: {evidence.publication_date}</span>
            </span>
          )}
        </div>

        {/* Evidence text */}
        <blockquote className="glass-surface rounded-lg border-l-2 border-l-cyan-500 px-3.5 py-2.5 text-sm text-foreground/95 italic leading-relaxed">
          "{evidence.text}"
        </blockquote>

        {/* Expandable Raw NLI Distribution & Alignment Details */}
        <div>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            className="flex items-center gap-1 text-xs text-slate-600 dark:text-slate-400 hover:text-brand-blue dark:hover:text-cyan-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 rounded"
          >
            <Layers className="h-3 w-3" />
            <span>{expanded ? 'Hide NLI distribution & alignment' : 'Inspect DeBERTa NLI distribution & alignment'}</span>
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>

          {expanded && (
            <div className="glass-surface mt-2.5 space-y-2 rounded-lg p-2.5 text-xs">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div className="flex items-center justify-between px-2.5 py-1.5 rounded-md bg-white/70 dark:bg-navy-900/70 border border-border/60">
                  <span className="text-emerald-700 dark:text-emerald-400 font-medium">SUPPORTS (raw)</span>
                  <span className="font-mono text-foreground font-semibold">
                    {(supportsProb * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-between px-2.5 py-1.5 rounded-md bg-white/70 dark:bg-navy-900/70 border border-border/60">
                  <span className="text-rose-700 dark:text-rose-400 font-medium">REFUTES (raw)</span>
                  <span className="font-mono text-foreground font-semibold">
                    {(refutesProb * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-between px-2.5 py-1.5 rounded-md bg-white/70 dark:bg-navy-900/70 border border-border/60">
                  <span className="text-slate-600 dark:text-slate-400 font-medium">NOT ENOUGH INFO (raw)</span>
                  <span className="font-mono text-foreground font-semibold">
                    {(neiProb * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              {evidence.alignment_notes && (
                <p className="text-[11px] text-slate-600 dark:text-slate-400 px-1 leading-relaxed">
                  <strong className="text-foreground/90">Alignment Assessment: </strong>
                  {evidence.alignment_notes}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
