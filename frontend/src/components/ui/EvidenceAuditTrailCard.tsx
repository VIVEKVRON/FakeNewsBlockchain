import React, { useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Compass,
  Cpu,
  ExternalLink,
  Filter,
  GitCompare,
  HelpCircle,
  Info,
  Layers,
  Scale,
  ServerCrash,
  XCircle,
} from 'lucide-react';
import type { AuditSourceItem, EvidenceAuditTrail, ModelSignal } from '@/types/verification';
import { cn } from '@/lib/utils';

interface EvidenceAuditTrailCardProps {
  auditTrail?: EvidenceAuditTrail | null;
  compact?: boolean;
  defaultExpanded?: boolean;
}

const formatDirectionBadge = (dir: string): { label: string; cls: string } => {
  if (dir === 'support_oriented') {
    return {
      label: 'Support Search',
      cls: 'bg-emerald-50 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-500/30',
    };
  }
  if (dir === 'contradiction_oriented') {
    return {
      label: 'Contradiction Search',
      cls: 'bg-rose-50 dark:bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-200 dark:border-rose-500/30',
    };
  }
  return {
    label: 'Neutral Search',
    cls: 'bg-slate-100 dark:bg-slate-800/70 text-slate-700 dark:text-slate-300 border-border',
  };
};

const formatTierBadge = (tier: string): { label: string; cls: string } => {
  if (tier === 'TIER_1_PRIMARY_OFFICIAL') {
    return {
      label: 'Tier 1: Official Primary',
      cls: 'bg-indigo-50 dark:bg-indigo-500/15 text-indigo-800 dark:text-indigo-200 border-indigo-300 dark:border-indigo-500/30',
    };
  }
  if (tier === 'TIER_2_SECONDARY_ENCYCLOPEDIC') {
    return {
      label: 'Tier 2: Secondary Encyclopedic',
      cls: 'bg-sky-50 dark:bg-sky-500/10 text-sky-800 dark:text-sky-300 border-sky-200 dark:border-sky-500/30',
    };
  }
  return {
    label: 'Tier 3: Review / Metadata',
    cls: 'bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300 border-amber-200 dark:border-amber-500/30',
  };
};

const formatOutcomeBadge = (outcome: string): { label: string; cls: string } => {
  switch (outcome) {
    case 'success_with_results':
      return {
        label: 'success_with_results',
        cls: 'border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/70 dark:bg-emerald-500/10 text-emerald-800 dark:text-emerald-300',
      };
    case 'cache_hit':
      return {
        label: 'cache_hit',
        cls: 'border-teal-200 dark:border-teal-500/30 bg-teal-50/70 dark:bg-teal-500/10 text-teal-800 dark:text-teal-300',
      };
    case 'no_results':
      return {
        label: 'no_results',
        cls: 'border-slate-200 dark:border-slate-700 bg-slate-100/80 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300',
      };
    case 'skipped_by_policy':
      return {
        label: 'skipped_by_policy',
        cls: 'border-sky-200 dark:border-sky-500/30 bg-sky-50/70 dark:bg-sky-500/10 text-sky-800 dark:text-sky-300',
      };
    case 'timeout':
      return {
        label: 'timeout',
        cls: 'border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200',
      };
    case 'quota_exhausted':
      return {
        label: 'quota_exhausted',
        cls: 'border-orange-300 dark:border-orange-500/30 bg-orange-50 dark:bg-orange-950/30 text-orange-900 dark:text-orange-200',
      };
    case 'unavailable_no_api_key':
      return {
        label: 'unavailable_no_api_key',
        cls: 'border-violet-300 dark:border-violet-500/30 bg-violet-50 dark:bg-violet-950/30 text-violet-900 dark:text-violet-200',
      };
    case 'network_error':
    default:
      return {
        label: outcome || 'network_error',
        cls: 'border-rose-300 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-950/30 text-rose-900 dark:text-rose-200',
      };
  }
};

const ModelSignalPanel: React.FC<{ title: string; sig: ModelSignal }> = ({ title, sig }) => (
  <div className="rounded-lg border border-border bg-white/80 dark:bg-slate-950/40 p-3 space-y-1.5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="text-[11px] font-bold uppercase tracking-wider text-foreground">
        {title} ({sig.dataset_origin})
      </span>
      <span className="rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-slate-600 dark:text-slate-400">
        input: {sig.applicable_input_type}
      </span>
    </div>
    {sig.applicable && sig.prediction ? (
      <>
        <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
          <span className="font-bold text-brand-blue">{sig.prediction}</span>
          {sig.confidence !== null && sig.confidence !== undefined && (
            <span className="text-slate-600 dark:text-slate-400">
              softmax: {(sig.confidence * 100).toFixed(1)}%
            </span>
          )}
          <span className="text-[10px] text-slate-500">model: {sig.model_name}</span>
        </div>
        {Object.keys(sig.raw_logits || {}).length > 0 && (
          <div className="text-[10px] font-mono text-slate-600 dark:text-slate-400 truncate" title={JSON.stringify(sig.raw_logits)}>
            raw logits: {Object.entries(sig.raw_logits).slice(0, 4).map(([k, v]) => `${k}:${v}`).join(' | ')}
          </div>
        )}
      </>
    ) : (
      <p className="text-[11px] italic text-slate-600 dark:text-slate-400">
        Not applicable for this input type ({sig.applicable_input_type}).
      </p>
    )}
    <p className="text-[10px] text-slate-600 dark:text-slate-400 leading-snug">{sig.disclaimer}</p>
  </div>
);

const AuditItemList: React.FC<{
  items: AuditSourceItem[];
  emptyText: string;
  accent: 'support' | 'contradict' | 'neutral' | 'rejected';
}> = ({ items, emptyText, accent }) => {
  if (items.length === 0) {
    return (
      <p className="text-xs italic text-slate-600 dark:text-slate-400 py-2">
        {emptyText}
      </p>
    );
  }

  const borderAccent =
    accent === 'support'
      ? 'border-l-emerald-500'
      : accent === 'contradict'
      ? 'border-l-rose-500'
      : accent === 'rejected'
      ? 'border-l-amber-500'
      : 'border-l-slate-400';

  return (
    <div className="space-y-2.5">
      {items.map((item, idx) => {
        const dirBadge = formatDirectionBadge(item.retrieval_direction);
        const tierBadge = formatTierBadge(item.evidence_tier);
        const probs = item.ml_nli_probabilities || {};
        return (
          <div
            key={`${item.source_type}-${idx}-${item.title_or_page}`}
            className={cn(
              'rounded-xl border border-border border-l-4 bg-slate-50/80 dark:bg-slate-900/40 p-3.5 space-y-2',
              borderAccent
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-foreground">{item.source_name}</span>
                <span className="text-slate-500">&middot;</span>
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-brand-blue hover:underline max-w-[260px] truncate"
                    title={item.title_or_page}
                  >
                    <span className="truncate">{item.title_or_page}</span>
                    <ExternalLink className="h-3 w-3 shrink-0" />
                  </a>
                ) : (
                  <span className="text-slate-700 dark:text-slate-300 truncate max-w-[260px]">
                    {item.title_or_page}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <span className={cn('rounded-md border px-2 py-0.5 text-[10px] font-medium', tierBadge.cls)}>
                  {tierBadge.label}
                </span>
                <span className={cn('rounded-md border px-2 py-0.5 text-[10px] font-medium', dirBadge.cls)}>
                  {dirBadge.label}
                </span>
                <span className="rounded-md border border-border bg-white/80 dark:bg-slate-800/80 px-2 py-0.5 font-mono text-[10px] text-slate-700 dark:text-slate-300">
                  Quality: {(item.overall_quality_score * 100).toFixed(0)}%
                </span>
              </div>
            </div>

            <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
              "{item.text_excerpt}"
            </p>

            {/* Quality Dimensions & DeBERTa NLI Pair Assessment */}
            <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-slate-600 dark:text-slate-400">
              <span>Relevance: {(item.relevance_score * 100).toFixed(0)}%</span>
              <span>&middot;</span>
              <span>Entity: {(item.subject_entity_alignment * 100).toFixed(0)}%</span>
              <span>&middot;</span>
              <span>Predicate: {(item.predicate_alignment * 100).toFixed(0)}%</span>
              <span>&middot;</span>
              <span>Specificity: {(item.evidence_specificity * 100).toFixed(0)}%</span>
              <span>&middot;</span>
              <span>Geo: {item.geographic_status}</span>
              {(item.source_type === 'fever_local' || item.source_type === 'wikipedia_live' || item.source_type === 'official_record') && (
                <>
                  <span>&middot;</span>
                  <span className="text-foreground font-semibold">
                    DeBERTa NLI: {item.ml_nli_label} ({(item.ml_nli_confidence * 100).toFixed(0)}%
                    {probs.supports !== undefined ? ` | S:${(probs.supports * 100).toFixed(0)} R:${((probs.refutes || 0) * 100).toFixed(0)} N:${((probs.not_enough_info || 0) * 100).toFixed(0)}` : ''})
                  </span>
                </>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-slate-600 dark:text-slate-400 pt-1 border-t border-border/60">
              <div className="flex flex-wrap items-center gap-3">
                {item.publication_date && (
                  <span className="inline-flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    <span>Pub: {item.publication_date}</span>
                  </span>
                )}
                <span>Retrieved: {item.retrieved_at.slice(0, 19).replace('T', ' ')}Z</span>
              </div>
              {item.rejection_reason ? (
                <span className="text-amber-700 dark:text-amber-300 font-semibold">
                  Filtered: {item.rejection_reason}
                </span>
              ) : (
                <span className="truncate max-w-[360px]">{item.alignment_notes}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

export const EvidenceAuditTrailCard: React.FC<EvidenceAuditTrailCardProps> = ({
  auditTrail,
  compact = false,
  defaultExpanded,
}) => {
  const [expanded, setExpanded] = useState<boolean>(
    defaultExpanded !== undefined ? defaultExpanded : !compact
  );
  const [showAllAttempts, setShowAllAttempts] = useState<boolean>(!compact);
  const [activeTab, setActiveTab] = useState<'support' | 'contradict' | 'neutral' | 'rejected'>('support');

  if (!auditTrail || !auditTrail.initial_ml_signals) {
    return null;
  }

  const initSigs = auditTrail.initial_ml_signals;
  const nliEv = auditTrail.nli_evaluation;
  const qs = auditTrail.evidence_quality_summary;

  return (
    <div
      className={cn(
        'glass-panel rounded-2xl',
        compact ? 'p-3.5' : 'p-5 sm:p-6'
      )}
    >
      {/* Collapsible Header Button */}
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        className="w-full flex flex-wrap items-center justify-between gap-3 text-left"
      >
        <div className="space-y-0.5">
          <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-2">
            <Scale className="h-4 w-4 text-brand-blue" />
            <span>Evidence Audit Trail (IEVE)</span>
          </h4>
          <p className="text-[11px] text-slate-600 dark:text-slate-400">
            Bidirectional collection ({auditTrail.directions_executed.join(', ')}) &middot; Support: {qs.support_count}, Contradict: {qs.contradict_count}, Filtered: {qs.rejected_irrelevant_count} &middot; 2nd Pass: {auditTrail.second_pass_decision}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-md border border-border bg-slate-100 dark:bg-slate-800/80 px-2.5 py-0.5 font-mono text-[11px] text-foreground">
            Final: {auditTrail.final_verdict} ({(auditTrail.final_confidence * 100).toFixed(0)}%)
          </span>
          <span className="inline-flex items-center gap-1 rounded-lg border border-border bg-slate-100 dark:bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-foreground">
            <span>{expanded ? 'Hide' : 'Inspect'}</span>
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-border space-y-5">
          {/* 1. Separate Initial ML Signals (LIAR BERT & ISOT BERT — NEVER combined) */}
          <div className="rounded-xl border border-border bg-slate-50/80 dark:bg-slate-900/40 p-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-foreground">
                Pass 1: Separate Preliminary Linguistic Signals (Non-Filtering)
              </span>
              <div className="flex items-center gap-2 text-xs font-mono">
                <span>Final 2nd-Pass:</span>
                <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                <span className="font-bold text-brand-blue">{auditTrail.final_verdict}</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <ModelSignalPanel title="LIAR BERT Claim Classifier" sig={initSigs.liar_signal} />
              <ModelSignalPanel title="ISOT BERT Article Classifier" sig={initSigs.isot_signal} />
            </div>

            <div className="flex items-start gap-2 rounded-lg border border-sky-200 dark:border-cyan-500/25 bg-sky-50/70 dark:bg-cyan-950/20 px-3 py-2 text-[11px] text-sky-900 dark:text-cyan-200">
              <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              <span>{initSigs.note}</span>
            </div>

            {/* Post-Retrieval DeBERTa NLI Evaluation Stage */}
            {nliEv && (
              <div className="rounded-lg border border-border bg-white/75 dark:bg-slate-950/40 p-3 space-y-1">
                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                  <span className="font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
                    <Cpu className="h-3.5 w-3.5 text-brand-cyan" />
                    <span>Evidence Evaluation Stage: DeBERTa FEVER NLI ({nliEv.pairs_evaluated} pairs)</span>
                  </span>
                  <span className="font-mono text-[10px] text-slate-600 dark:text-slate-400">
                    stage: {nliEv.evaluation_stage}
                  </span>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-[11px] font-mono text-slate-700 dark:text-slate-300">
                  <span>
                    Raw NLI: S={nliEv.raw_label_counts.SUPPORTS || 0}, R={nliEv.raw_label_counts.REFUTES || 0}, NEI={nliEv.raw_label_counts['NOT ENOUGH INFO'] || 0}
                  </span>
                  <span>&middot;</span>
                  <span>
                    Calibrated Alignment: S={nliEv.calibrated_label_counts.SUPPORTS || 0}, R={nliEv.calibrated_label_counts.REFUTES || 0}, NEI={nliEv.calibrated_label_counts['NOT ENOUGH INFO'] || 0}
                  </span>
                </div>
                <p className="text-[10px] text-slate-600 dark:text-slate-400">{nliEv.disclaimer}</p>
              </div>
            )}

            {auditTrail.verdict_changed_from_initial && auditTrail.verdict_change_reason && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs text-amber-900 dark:text-amber-200">
                <GitCompare className="h-4 w-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
                <span>
                  <strong>Why Final Verdict Differs From Preliminary Signal: </strong>
                  {auditTrail.verdict_change_reason}
                </span>
              </div>
            )}

            <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
              <strong>Second-Pass Verdict Reasoning: </strong>
              {auditTrail.second_pass_reasoning}
            </p>
          </div>

          {/* 2. Tier & Quality Summary Strip */}
          <div className="space-y-2">
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
              <div className="rounded-xl border border-border bg-slate-50/80 dark:bg-slate-900/40 px-3 py-2">
                <div className="text-[10px] uppercase text-slate-600 dark:text-slate-400">Supporting</div>
                <div className="font-mono font-bold text-emerald-700 dark:text-emerald-400">
                  {qs.support_count} ({qs.independent_supporting_sources} indep.)
                </div>
              </div>
              <div className="rounded-xl border border-border bg-slate-50/80 dark:bg-slate-900/40 px-3 py-2">
                <div className="text-[10px] uppercase text-slate-600 dark:text-slate-400">Contradicting</div>
                <div className="font-mono font-bold text-rose-700 dark:text-rose-400">
                  {qs.contradict_count} ({qs.independent_contradicting_sources} indep.)
                </div>
              </div>
              <div className="rounded-xl border border-border bg-slate-50/80 dark:bg-slate-900/40 px-3 py-2">
                <div className="text-[10px] uppercase text-slate-600 dark:text-slate-400">Tier 1 / Tier 2 / Tier 3</div>
                <div className="font-mono font-bold text-foreground">
                  {qs.tier1_official_primary_count} / {qs.tier2_encyclopedic_count} / {qs.tier3_secondary_or_metadata_count}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-slate-50/80 dark:bg-slate-900/40 px-3 py-2">
                <div className="text-[10px] uppercase text-slate-600 dark:text-slate-400">Filtered Irrelevant</div>
                <div className="font-mono font-bold text-amber-700 dark:text-amber-400">
                  {qs.rejected_irrelevant_count}
                </div>
              </div>
              <div className="rounded-xl border border-border bg-slate-50/80 dark:bg-slate-900/40 px-3 py-2">
                <div className="text-[10px] uppercase text-slate-600 dark:text-slate-400">Max Quality (S / C)</div>
                <div className="font-mono font-bold text-foreground">
                  {(qs.max_support_quality * 100).toFixed(0)}% / {(qs.max_contradict_quality * 100).toFixed(0)}%
                </div>
              </div>
            </div>

            {!qs.primary_official_sources_available && (
              <div className="flex items-start gap-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-100/70 dark:bg-slate-900/50 px-3 py-2 text-[11px] text-slate-700 dark:text-slate-300">
                <Layers className="h-3.5 w-3.5 shrink-0 mt-0.5 text-brand-blue" />
                <span>
                  <strong>Provenance Disclosure: </strong>
                  {qs.claim_requires_primary_record && qs.primary_record_need_reason
                    ? `${qs.primary_record_need_reason} Zero Tier 1 official primary documents are available from the four configured sources.`
                    : 'No Tier 1 first-party official/institutional documents were retrieved; current sources provide Tier 2 encyclopedic references and Tier 3 review/coverage metadata only.'}
                </span>
              </div>
            )}
          </div>

          {/* 3. Conflicts & Provider Failure Notices */}
          {auditTrail.conflicts_detected && auditTrail.conflict_details.length > 0 && (
            <div className="flex items-start gap-2 rounded-xl border border-rose-300 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-950/30 p-3 text-xs text-rose-900 dark:text-rose-200">
              <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-rose-600 dark:text-rose-400" />
              <div>
                <strong>Source Conflicts Detected: </strong>
                {auditTrail.conflict_details.join(' ')}
              </div>
            </div>
          )}

          {auditTrail.unavailable_providers.length > 0 && (
            <div className="flex items-start gap-2 rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs text-amber-900 dark:text-amber-200">
              <ServerCrash className="h-4 w-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
              <span>
                <strong>Unavailable / Failed Providers: </strong>
                {auditTrail.unavailable_providers.join(', ')} — recorded strictly as unavailable coverage, never as negative evidence against the claim.
              </span>
            </div>
          )}

          {/* 4. Directional Query Badges & GDELT Selection Log */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600 dark:text-slate-400">
              <Compass className="h-3.5 w-3.5 text-brand-cyan shrink-0" />
              <span className="font-semibold text-foreground">Independent Search Formulations:</span>
              {Object.entries(auditTrail.queries_by_direction).map(([dir, q]) => (
                <span
                  key={dir}
                  className="rounded-md border border-border bg-slate-100/80 dark:bg-slate-900/50 px-2 py-0.5 font-mono text-[10px] truncate max-w-[230px]"
                  title={`${dir}: ${q}`}
                >
                  {dir}: "{q}"
                </span>
              ))}
            </div>

            {auditTrail.gdelt_claim_selections && auditTrail.gdelt_claim_selections.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono text-slate-600 dark:text-slate-400">
                <span className="font-semibold text-foreground">GDELT Claim Selection:</span>
                {auditTrail.gdelt_claim_selections.map((gs, idx) => (
                  <span
                    key={`gs-${idx}`}
                    className={cn(
                      'rounded border px-2 py-0.5',
                      gs.selected
                        ? 'border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/70 dark:bg-emerald-500/10 text-emerald-800 dark:text-emerald-300'
                        : 'border-border bg-slate-100 dark:bg-slate-800/60 text-slate-700 dark:text-slate-300'
                    )}
                    title={gs.claim}
                  >
                    {gs.selected ? 'Queried' : 'Skipped'}: "{gs.claim.length > 32 ? `${gs.claim.slice(0, 32)}...` : gs.claim}" ({gs.reason})
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* 5. Supporting / Contradicting / Neutral / Filtered Evidence Tabs */}
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 border-b border-border pb-2">
              <button
                type="button"
                onClick={() => setActiveTab('support')}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                  activeTab === 'support'
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-100 dark:bg-slate-800/70 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800'
                )}
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>Supporting ({auditTrail.supporting_evidence.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('contradict')}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                  activeTab === 'contradict'
                    ? 'bg-rose-600 text-white'
                    : 'bg-slate-100 dark:bg-slate-800/70 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800'
                )}
              >
                <XCircle className="h-3.5 w-3.5" />
                <span>Contradicting ({auditTrail.contradicting_evidence.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('neutral')}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                  activeTab === 'neutral'
                    ? 'bg-brand-blue text-white'
                    : 'bg-slate-100 dark:bg-slate-800/70 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800'
                )}
              >
                <HelpCircle className="h-3.5 w-3.5" />
                <span>Neutral ({auditTrail.neutral_evidence.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('rejected')}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                  activeTab === 'rejected'
                    ? 'bg-amber-600 text-white'
                    : 'bg-slate-100 dark:bg-slate-800/70 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-800'
                )}
              >
                <Filter className="h-3.5 w-3.5" />
                <span>Filtered Irrelevant ({auditTrail.rejected_irrelevant_evidence.length})</span>
              </button>
            </div>

            {activeTab === 'support' && (
              <AuditItemList
                items={auditTrail.supporting_evidence}
                emptyText="No aligned supporting evidence items passed relevance checks."
                accent="support"
              />
            )}
            {activeTab === 'contradict' && (
              <AuditItemList
                items={auditTrail.contradicting_evidence}
                emptyText="No aligned contradicting evidence items passed relevance checks."
                accent="contradict"
              />
            )}
            {activeTab === 'neutral' && (
              <AuditItemList
                items={auditTrail.neutral_evidence}
                emptyText="No neutral contextual evidence items returned."
                accent="neutral"
              />
            )}
            {activeTab === 'rejected' && (
              <AuditItemList
                items={auditTrail.rejected_irrelevant_evidence}
                emptyText="All retrieved items passed entity, semantic, and geographic relevance filters."
                accent="rejected"
              />
            )}
          </div>

          {/* 6. Retrieval Attempts & Methodology Footer */}
          <div className="space-y-2 border-t border-border pt-3 text-[11px] text-slate-600 dark:text-slate-400">
            {auditTrail.retrieval_attempts && auditTrail.retrieval_attempts.length > 0 && (() => {
              const allAttempts = auditTrail.retrieval_attempts;
              const totalCount = auditTrail.total_retrieval_attempts ?? allAttempts.length;
              const visibleAttempts = showAllAttempts ? allAttempts : allAttempts.slice(0, 12);
              const compactOmitted = allAttempts.length - visibleAttempts.length;
              const backendOmitted = auditTrail.omitted_retrieval_attempts ?? 0;
              return (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-semibold text-foreground">
                    Retrieval Attempts ({totalCount}):
                  </span>
                  {visibleAttempts.map((ra, idx) => {
                    const ob = formatOutcomeBadge(ra.outcome);
                    return (
                      <span
                        key={`att-${ra.provider}-${ra.claim_id || idx}-${idx}`}
                        className={cn('rounded-md border px-2 py-0.5 font-mono text-[10px]', ob.cls)}
                        title={`${ra.claim_id ? `[${ra.claim_id}] ` : ''}Query: "${ra.query}" | Reason: ${ra.reason || ra.outcome}`}
                      >
                        {ra.claim_id ? `${ra.claim_id} · ` : ''}{ra.provider} [{ra.direction}]: {ob.label} ({ra.relevant_items}/{ra.items_retrieved})
                      </span>
                    );
                  })}
                  {compactOmitted > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowAllAttempts(true)}
                      className="rounded-md border border-border bg-slate-100 dark:bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-brand-blue hover:underline"
                    >
                      +{compactOmitted} omitted in compact view — Show all {allAttempts.length}
                    </button>
                  )}
                  {compact && showAllAttempts && allAttempts.length > 12 && (
                    <button
                      type="button"
                      onClick={() => setShowAllAttempts(false)}
                      className="rounded-md border border-border bg-slate-100 dark:bg-slate-800 px-2 py-0.5 font-mono text-[10px] text-slate-500 hover:underline"
                    >
                      Collapse attempts
                    </button>
                  )}
                  {backendOmitted > 0 && (
                    <span className="text-[10px] italic text-amber-700 dark:text-amber-300">
                      ({backendOmitted} historical attempts omitted from payload)
                    </span>
                  )}
                </div>
              );
            })()}

            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-foreground">Provider Status:</span>
              {auditTrail.provider_statuses.map((ps) => (
                <span
                  key={ps.provider}
                  className={cn(
                    'rounded-md border px-2 py-0.5 font-mono text-[10px]',
                    ps.available
                      ? 'border-emerald-200 dark:border-emerald-500/30 bg-emerald-50/70 dark:bg-emerald-500/10 text-emerald-800 dark:text-emerald-300'
                      : 'border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 text-amber-800 dark:text-amber-300'
                  )}
                  title={ps.error_or_reason || ''}
                >
                  {ps.provider}: {ps.status} ({ps.relevant_items}/{ps.items_retrieved})
                </span>
              ))}
            </div>
            <p className="leading-relaxed">{qs.methodology_note}</p>
          </div>
        </div>
      )}
    </div>
  );
};
