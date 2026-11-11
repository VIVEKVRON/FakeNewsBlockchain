import React, { useState, useEffect } from 'react';
import {
  FileCheck2,
  Sliders,
  ShieldCheck,
  Send,
  Database,
  HelpCircle,
  CheckCircle2,
  XCircle,
  Split,
} from 'lucide-react';
import { verifyText } from '@/api/verify';
import type { TextVerificationResponse } from '@/types/verification';
import { VerdictBadge } from '@/components/ui/VerdictBadge';
import { EvidenceCard } from '@/components/ui/EvidenceCard';
import { EvidenceAuditTrailCard } from '@/components/ui/EvidenceAuditTrailCard';
import { ExternalEvidenceSection } from '@/components/ui/ExternalEvidenceSection';
import { LimitationsCallout } from '@/components/ui/LimitationsCallout';
import { LoadingSkeleton } from '@/components/ui/LoadingSkeleton';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { BlockchainAnchorCard } from '@/components/ui/BlockchainAnchorCard';
import { RippleButton } from '@/components/ui/RippleButton';
import { getVerdictPanelAccent } from '@/lib/utils';
import { useHistory } from '@/hooks/useHistory';

const SAMPLE_CLAIMS = [
  {
    label: 'Genuine',
    claim: '19 Kids and Counting is an American reality television show featuring the Duggar family.',
  },
  {
    label: 'Fake',
    claim: '19 Kids and Counting was cancelled in 2030.',
  },
  {
    label: 'Misleading',
    claim: '19 Kids and Counting aired on HBO.',
  },
  {
    label: 'Partially True',
    claim: 'Paris is the capital of France, and Apollo 11 landed on Mars in 1969.',
  },
  {
    label: 'Outdated',
    claim: 'Barack Obama is the current President of the United States.',
  },
  {
    label: 'Unverified',
    claim: 'Biologists discovered alien potatoes on Pluto in 2026.',
  },
];

interface TextVerifyPanelProps {
  initialClaim?: string;
  showHeader?: boolean;
}

export const TextVerifyPanel: React.FC<TextVerifyPanelProps> = ({
  initialClaim,
  showHeader = true,
}) => {
  const { addClaimVerification } = useHistory();

  const [claim, setClaim] = useState(initialClaim || '');
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TextVerificationResponse | null>(null);

  useEffect(() => {
    if (initialClaim) {
      setClaim(initialClaim);
    }
  }, [initialClaim]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!claim.trim() || claim.trim().length < 5) {
      setError('Please provide a claim of at least 5 characters.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await verifyText({
        claim: claim.trim(),
        top_k: topK,
      });
      setResult(response);
      addClaimVerification(response);
    } catch (err: any) {
      setError(err.message || 'Verification failed. Please check backend connection.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      {showHeader && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-blue dark:text-cyan-300">
            <FileCheck2 className="h-4 w-4" />
            <span>Evidence-Based NLI Pipeline</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
            Single Claim Fact Verification
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Evaluates claim entailment against 126,000 indexed FEVER Wikipedia sentences using DeBERTa-v3 NLI on CPU.
          </p>
        </div>
      )}

      {/* Input Form Card (No Tilt on forms) */}
      <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs">
              <label htmlFor="claim-input" className="font-semibold text-foreground">
                News Claim or Assertion
              </label>
              <span className="text-slate-600 dark:text-slate-400 font-mono">
                {claim.length} / 2000 chars
              </span>
            </div>
            <textarea
              id="claim-input"
              rows={3}
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              placeholder="e.g. 19 Kids and Counting features the Duggar family..."
              className="glass-surface w-full rounded-2xl p-4 text-sm text-foreground placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 transition-all"
            />
          </div>

          {/* Sample Preset Buttons */}
          <div className="space-y-2">
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Quick Benchmarks:</span>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_CLAIMS.map((sample, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => setClaim(sample.claim)}
                  className="glass-surface rounded-lg px-2.5 py-1 text-xs text-slate-700 dark:text-slate-300 hover:border-cyan-400/50 hover:text-brand-blue dark:hover:text-cyan-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                >
                  {sample.label}
                </button>
              ))}
            </div>
          </div>

          {/* Controls: Top K slider & Submit */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-t border-border/70 pt-4">
            <div className="flex items-center gap-3">
              <Sliders className="h-4 w-4 text-slate-500 dark:text-slate-400" />
              <label htmlFor="top-k-slider" className="text-xs font-medium text-slate-700 dark:text-slate-300">
                Top Evidence Count (top_k):
              </label>
              <input
                id="top-k-slider"
                type="range"
                min="1"
                max="10"
                value={topK}
                onChange={(e) => setTopK(parseInt(e.target.value, 10))}
                className="w-24 accent-brand-cyan"
              />
              <span className="text-xs font-mono font-semibold text-brand-blue dark:text-cyan-300">
                {topK}
              </span>
            </div>

            <RippleButton
              type="submit"
              variant="primary"
              disabled={loading || !claim.trim()}
              className="rounded-xl px-6 py-2.5 text-sm"
            >
              <Send className="h-4 w-4" />
              <span>Verify Claim</span>
            </RippleButton>
          </div>
        </form>
      </div>

      {/* Loading State */}
      {loading && <LoadingSkeleton message="Scanning FEVER Index & Computing DeBERTa-v3 NLI Entailment..." />}

      {/* Error State */}
      {error && <ErrorBanner message={error} onRetry={() => handleSubmit({ preventDefault: () => {} } as React.FormEvent)} />}

      {/* Results View */}
      {result && !loading && (
        <div className="space-y-6">
          {/* Section Banner */}
          <div className="flex items-center justify-between border-b border-border/70 pb-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-500 dark:text-emerald-400" />
              <h2 className="font-bold text-foreground text-base tracking-tight">
                Evidence-Based Verification (FEVER + FAISS)
              </h2>
            </div>
            <span className="text-xs text-slate-600 dark:text-slate-400 font-mono">
              ID: {result.verification_id.slice(0, 8)}
            </span>
          </div>

          {/* Primary Verdict Card */}
          <div className={`glass-panel rounded-3xl p-6 sm:p-8 space-y-6 ${getVerdictPanelAccent(result.verdict)}`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1.5">
                <span className="text-xs uppercase tracking-wider text-slate-600 dark:text-slate-400 font-semibold">
                  Synthesized Six-Class Truth Verdict
                </span>
                <div>
                  <VerdictBadge verdict={result.verdict} size="lg" showDescription />
                </div>
              </div>

              {/* Alignment Gauge */}
              <div className="flex flex-col sm:items-end space-y-1">
                <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Alignment Score (Not Calibrated Truth Prob.)</span>
                <div className="flex items-center gap-2">
                  <div className="h-2.5 w-32 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-[#087BFF] to-[#00C8FF] transition-all duration-500"
                      style={{ width: `${Math.round(result.confidence_score * 100)}%` }}
                    />
                  </div>
                  <span className="font-mono text-sm font-bold text-foreground">
                    {(result.confidence_score * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            </div>

            {/* Grounding Explanation */}
            <div className="glass-surface rounded-2xl p-4 text-sm text-foreground leading-relaxed">
              <strong>Grounding Summary: </strong>
              <span>{result.explanation}</span>
            </div>

            {/* Uncertainty Explanation */}
            {result.uncertainty_explanation && (
              <div className="rounded-2xl bg-amber-500/10 border border-amber-500/25 p-4 text-xs text-amber-900 dark:text-amber-100/90 leading-relaxed flex items-start gap-2.5">
                <HelpCircle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <strong className="text-amber-800 dark:text-amber-300">Uncertainty &amp; Alignment Explanation: </strong>
                  <span>{result.uncertainty_explanation}</span>
                </div>
              </div>
            )}

            {/* Sub-Claim Breakdown */}
            {result.claim_verdicts && result.claim_verdicts.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-indigo-700 dark:text-indigo-300 flex items-center gap-1.5">
                  <Split className="h-3.5 w-3.5" />
                  <span>Claim-Level Breakdown ({result.claim_verdicts.length} Propositions)</span>
                </h3>
                <div className="space-y-2.5">
                  {result.claim_verdicts.map((sub, sIdx) => (
                    <div key={sIdx} className="glass-surface rounded-xl p-3.5 space-y-2">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-foreground">
                          #{sIdx + 1}: "{sub.claim}"
                        </span>
                        <VerdictBadge verdict={sub.verdict} size="sm" />
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">{sub.explanation}</p>
                      {sub.evidence_audit_trail && (
                        <div className="pt-1">
                          <EvidenceAuditTrailCard auditTrail={sub.evidence_audit_trail} compact />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Grouped Supporting vs Contradicting Evidence */}
            {(() => {
              const supportingEv = result.evidence.filter(
                (e) => e.evidence_role === 'supporting' || e.nli_label === 'SUPPORTS'
              );
              const contradictingEv = result.evidence.filter(
                (e) => e.evidence_role === 'contradicting' || e.nli_label === 'REFUTES'
              );
              const contextualEv = result.evidence.filter(
                (e) =>
                  e.evidence_role !== 'supporting' &&
                  e.evidence_role !== 'contradicting' &&
                  e.nli_label !== 'SUPPORTS' &&
                  e.nli_label !== 'REFUTES'
              );

              return (
                <div className="space-y-5">
                  <div className="flex items-center justify-between border-b border-border/70 pb-2">
                    <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
                      <Database className="h-3.5 w-3.5 text-brand-cyan" />
                      <span>Retrieved Knowledge Evidence ({result.evidence.length})</span>
                    </h3>
                    <span className="text-xs text-slate-600 dark:text-slate-400">
                      Ranked by Cosine Similarity (Local FEVER + Public Wikipedia)
                    </span>
                  </div>

                  {result.evidence.length === 0 ? (
                    <p className="text-xs text-slate-600 dark:text-slate-400 italic py-2">
                      No evidence sentences could be retrieved from available knowledge sources.
                    </p>
                  ) : (
                    <div className="space-y-5">
                      {supportingEv.length > 0 && (
                        <div className="space-y-2.5">
                          <h4 className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1.5">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            <span>Supporting Evidence ({supportingEv.length})</span>
                          </h4>
                          <div className="space-y-2.5">
                            {supportingEv.map((ev, idx) => (
                              <EvidenceCard key={`sup-${ev.doc_id}-${idx}`} evidence={ev} index={ev.rank - 1} />
                            ))}
                          </div>
                        </div>
                      )}

                      {contradictingEv.length > 0 && (
                        <div className="space-y-2.5">
                          <h4 className="text-xs font-semibold text-rose-700 dark:text-rose-400 flex items-center gap-1.5">
                            <XCircle className="h-3.5 w-3.5" />
                            <span>Contradicting Evidence ({contradictingEv.length})</span>
                          </h4>
                          <div className="space-y-2.5">
                            {contradictingEv.map((ev, idx) => (
                              <EvidenceCard key={`con-${ev.doc_id}-${idx}`} evidence={ev} index={ev.rank - 1} />
                            ))}
                          </div>
                        </div>
                      )}

                      {contextualEv.length > 0 && (
                        <div className="space-y-2.5">
                          <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
                            <HelpCircle className="h-3.5 w-3.5" />
                            <span>Contextual / Insufficient Evidence ({contextualEv.length})</span>
                          </h4>
                          <div className="space-y-2.5">
                            {contextualEv.map((ev, idx) => (
                              <EvidenceCard key={`ctx-${ev.doc_id}-${idx}`} evidence={ev} index={ev.rank - 1} />
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })()}

            {/* IEVE Evidence Audit Trail */}
            <EvidenceAuditTrailCard auditTrail={result.evidence_audit_trail} />

            {/* Supplementary External Fact Checks & GDELT News Coverage */}
            <ExternalEvidenceSection
              factCheckMatches={result.fact_check_matches}
              newsEvidence={result.news_evidence}
              externalStatus={result.external_source_status}
            />

            {/* Limitations Callout */}
            <LimitationsCallout limitations={result.limitations} />

            {/* Cryptographic Blockchain Anchoring */}
            <BlockchainAnchorCard
              verificationId={result.verification_id}
              recordHash={result.blockchain_hash?.record_hash}
              canonicalRecord={result.blockchain_hash?.canonical_record}
            />
          </div>
        </div>
      )}
    </div>
  );
};
