import React, { useState } from 'react';
import {
  ShieldCheck,
  Activity,
  ChevronDown,
  ChevronUp,
  HelpCircle,
} from 'lucide-react';
import type { ArticleVerificationResponse } from '@/types/verification';
import { VerdictBadge } from '@/components/ui/VerdictBadge';
import { EvidenceCard } from '@/components/ui/EvidenceCard';
import { EvidenceAuditTrailCard } from '@/components/ui/EvidenceAuditTrailCard';
import { ExternalEvidenceSection } from '@/components/ui/ExternalEvidenceSection';
import { ModelSignalCard } from '@/components/ui/ModelSignalCard';
import { LimitationsCallout } from '@/components/ui/LimitationsCallout';
import { BlockchainAnchorCard } from '@/components/ui/BlockchainAnchorCard';
import { getVerdictPanelAccent } from '@/lib/utils';

interface ArticleVerificationResultProps {
  result: ArticleVerificationResponse;
}

export const ArticleVerificationResult: React.FC<ArticleVerificationResultProps> = ({ result }) => {
  const [expandedClaim, setExpandedClaim] = useState<number | null>(0);

  return (
    <div className="space-y-8">
      {/* 1. Overall Verdict Banner */}
      <div className={`glass-panel rounded-3xl p-6 sm:p-8 space-y-5 ${getVerdictPanelAccent(result.overall_verdict)}`}>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <span className="text-xs uppercase tracking-wider text-slate-600 dark:text-slate-400 font-semibold">
              Article Overall Truth Verdict
            </span>
            <div>
              <VerdictBadge verdict={result.overall_verdict} size="lg" showDescription />
            </div>
          </div>

          {/* Alignment Gauge */}
          <div className="flex flex-col sm:items-end space-y-1">
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">
              Alignment Score (Not Calibrated Truth Prob.)
            </span>
            <div className="flex items-center gap-2">
              <div className="h-2.5 w-32 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-[#087BFF] to-[#00C8FF] transition-all duration-500"
                  style={{ width: `${Math.round(result.overall_confidence * 100)}%` }}
                />
              </div>
              <span className="font-mono text-sm font-bold text-foreground">
                {(result.overall_confidence * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        </div>

        {/* Overall narrative explanation */}
        <div className="glass-surface rounded-2xl p-4 text-sm text-foreground leading-relaxed">
          <strong>Article Evaluation Summary: </strong>
          <span>{result.summary_explanation}</span>
        </div>

        {/* Uncertainty & Alignment Explanation */}
        {result.uncertainty_explanation && (
          <div className="rounded-2xl bg-amber-500/10 border border-amber-500/25 p-4 text-xs text-amber-900 dark:text-amber-100/90 leading-relaxed flex items-start gap-2.5">
            <HelpCircle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div>
              <strong className="text-amber-800 dark:text-amber-300">Uncertainty &amp; Aggregation Note: </strong>
              <span>{result.uncertainty_explanation}</span>
            </div>
          </div>
        )}
      </div>

      {/* 2. Experimental ML Signals */}
      <ModelSignalCard
        isotSignal={result.article_classifier}
        className="border-amber-500/30"
      />

      {/* 3. Evidence-Based Verification */}
      <div className="space-y-4">
        <div className="flex items-center justify-between border-b border-border/70 pb-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-500 dark:text-emerald-400" />
            <h2 className="font-bold text-foreground text-base tracking-tight">
              Evidence-Based Verification (FEVER + FAISS)
            </h2>
          </div>
          <span className="text-xs text-slate-600 dark:text-slate-400 font-mono">
            {result.claims_analyzed} Factual Claims Analyzed
          </span>
        </div>

        {/* Extracted claims accordion list */}
        <div className="space-y-4">
          {result.extracted_claims.map((claimItem, idx) => (
            <div
              key={idx}
              className="glass-panel rounded-2xl overflow-hidden transition-all duration-200"
            >
              <button
                type="button"
                onClick={() => setExpandedClaim(expandedClaim === idx ? null : idx)}
                aria-expanded={expandedClaim === idx}
                className="w-full p-5 text-left flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 cursor-pointer hover:bg-cyan-500/5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-6 w-6 items-center justify-center rounded-md bg-brand-blue/15 text-xs font-semibold text-brand-blue dark:text-cyan-300 shrink-0 mt-0.5">
                    #{claimItem.relevance_rank}
                  </span>
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-foreground leading-snug">
                      "{claimItem.claim}"
                    </p>
                    <p className="text-xs text-slate-600 dark:text-slate-400">
                      {claimItem.explanation}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
                  <VerdictBadge verdict={claimItem.verdict} size="sm" />
                  {expandedClaim === idx ? (
                    <ChevronUp className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                  )}
                </div>
              </button>

              {expandedClaim === idx && (
                <div className="glass-surface border-t border-x-0 border-b-0 p-5 space-y-4">
                  {claimItem.liar_signal && (
                    <div className="glass-panel rounded-xl p-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs">
                      <div className="flex items-center gap-2">
                        <Activity className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                        <span className="font-semibold text-slate-700 dark:text-slate-300">
                          Supplementary LIAR Signal:
                        </span>
                        <span className="font-mono capitalize font-bold text-indigo-700 dark:text-indigo-300">
                          {claimItem.liar_signal.prediction}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-600 dark:text-slate-400 italic">
                        {claimItem.liar_signal.disclaimer}
                      </span>
                    </div>
                  )}

                  {claimItem.uncertainty_explanation && (
                    <p className="text-[11px] text-amber-900 dark:text-amber-200/85 bg-amber-500/10 border border-amber-500/25 rounded-lg p-2.5 leading-relaxed">
                      <strong>Claim Alignment &amp; Uncertainty: </strong>
                      {claimItem.uncertainty_explanation}
                    </p>
                  )}

                  <div className="space-y-3">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                      Retrieved Evidence Sentences ({claimItem.evidence.length})
                    </h3>
                    {claimItem.evidence.length === 0 ? (
                      <p className="text-xs text-slate-600 dark:text-slate-400 italic">
                        No matching evidence sentences found in local FEVER or Wikipedia sources.
                      </p>
                    ) : (
                      claimItem.evidence.map((ev, eIdx) => (
                        <EvidenceCard key={eIdx} evidence={ev} index={eIdx} />
                      ))
                    )}
                  </div>

                  {claimItem.evidence_audit_trail && (
                    <div className="pt-2">
                      <EvidenceAuditTrailCard auditTrail={claimItem.evidence_audit_trail} compact />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Article-Level IEVE Audit Trail */}
      <EvidenceAuditTrailCard auditTrail={result.evidence_audit_trail} />

      {/* External Evidence */}
      <ExternalEvidenceSection
        factCheckMatches={result.fact_check_matches}
        newsEvidence={result.news_evidence}
        externalStatus={result.external_source_status}
      />

      {/* Limitations */}
      <LimitationsCallout limitations={result.limitations} />

      {/* Blockchain Anchoring */}
      <BlockchainAnchorCard
        verificationId={result.article_id}
        recordHash={result.blockchain_hash?.record_hash}
        canonicalRecord={result.blockchain_hash?.canonical_record}
      />
    </div>
  );
};
