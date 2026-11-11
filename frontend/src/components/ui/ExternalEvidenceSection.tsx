import React from 'react';
import {
  AlertTriangle,
  Calendar,
  ExternalLink,
  Globe,
  Info,
  Newspaper,
  Scale,
  ShieldAlert,
} from 'lucide-react';
import type {
  ExternalSourceStatus,
  FactCheckMatch,
  NewsEvidence,
} from '@/types/verification';
import { ExternalApiUsageCard } from '@/components/ui/ExternalApiUsageCard';
import { cn } from '@/lib/utils';

interface ExternalEvidenceSectionProps {
  factCheckMatches?: FactCheckMatch[];
  newsEvidence?: NewsEvidence[];
  externalStatus?: ExternalSourceStatus | null;
  compact?: boolean;
}

const formatGoogleStatusMessage = (status: string, err?: string | null): string => {
  switch (status) {
    case 'unavailable_no_api_key':
      return 'Google Fact Check Tools API key is not configured on the backend; third-party ClaimReview lookup was skipped safely.';
    case 'auth_error':
      return 'Google Fact Check Tools rejected backend credentials. Check backend server configuration.';
    case 'rate_limited':
      return 'Google Fact Check Tools API rate limit reached; continuing with available local and live sources.';
    case 'timeout':
    case 'http_error':
    case 'network_error':
    case 'invalid_response':
      return err || 'Google Fact Check Tools API was temporarily unreachable; local verification remains authoritative.';
    case 'no_results':
      return 'No prior third-party ClaimReview entries matched this claim. Absence of fact-check records is NOT proof of truth or falsehood.';
    case 'not_queried':
      return 'Google Fact Check lookup was not triggered for this request.';
    default:
      return err || 'No third-party fact-check matches available.';
  }
};

const formatGdeltStatusMessage = (status: string, err?: string | null): string => {
  switch (status) {
    case 'quota_exhausted':
      return 'Shared GDELT DOC 2.0 application allowance exhausted. Outbound GDELT queries are blocked fail-closed.';
    case 'tracker_unavailable':
      return 'Shared GDELT SQLite quota tracker unavailable; outbound GDELT query blocked fail-closed.';
    case 'disabled':
      return 'GDELT DOC 2.0 discovery is disabled in backend configuration.';
    case 'resolved_static_reference_fact':
    case 'skipped_static_reference_fact':
      return 'Skipped GDELT news query (skipped_static_reference_fact): elementary reference assertion excluded cleanly regardless of ML prediction to conserve GDELT quota.';
    case 'skipped_not_needed':
      return 'Skipped GDELT news lookup because local/encyclopedic evidence resolved the claim without news-cycle uncertainty.';
    case 'no_results':
      return 'No recent English GDELT coverage articles matched this query window. Lack of GDELT articles does not imply GENUINE or FAKE.';
    case 'not_queried':
      return 'GDELT news coverage discovery was not triggered.';
    default:
      return err || `GDELT discovery returned status '${status}'.`;
  }
};

export const ExternalEvidenceSection: React.FC<ExternalEvidenceSectionProps> = ({
  factCheckMatches = [],
  newsEvidence = [],
  externalStatus,
  compact = false,
}) => {
  if (
    !externalStatus &&
    factCheckMatches.length === 0 &&
    newsEvidence.length === 0
  ) {
    return null;
  }

  const googleStatus = externalStatus?.google_fact_check_status || 'not_queried';
  const gdeltStatus = externalStatus?.gdelt_status || 'not_queried';

  return (
    <div className="space-y-6">
      {/* 1. Google Fact Check Tools API (Third-Party ClaimReviews) */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
          <div className="space-y-0.5">
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-2">
              <Scale className="h-4 w-4 text-brand-violet" />
              <span>Google Fact Check Tools ({factCheckMatches.length})</span>
            </h4>
            <p className="text-[11px] text-slate-600 dark:text-slate-400">
              Third-party ClaimReview publications attributed directly to independent fact-checking publishers with original ratings verbatim.
            </p>
          </div>
          <span className="rounded-md border border-border bg-slate-100 dark:bg-slate-800/80 px-2.5 py-0.5 font-mono text-[11px] text-slate-700 dark:text-slate-300">
            Status: {googleStatus}
          </span>
        </div>

        {/* Attribution & Epistemic Notice */}
        <div className="flex items-start gap-2 rounded-xl border border-sky-200 dark:border-cyan-500/25 bg-sky-50/80 dark:bg-cyan-950/20 px-3 py-2 text-[11px] text-sky-900 dark:text-cyan-200">
          <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>
            Ratings below belong exclusively to the cited fact-checking publishers and are shown verbatim without inference or endorsement by Google or this tool.
          </span>
        </div>

        {/* Conflict / Staleness Warnings */}
        {externalStatus?.has_conflicting_fact_checks && (
          <div className="flex items-start gap-2 rounded-xl border border-rose-300 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-950/30 p-3 text-xs text-rose-900 dark:text-rose-200">
            <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-rose-600 dark:text-rose-400" />
            <span>
              <strong>Conflicting External Fact-Checks Detected:</strong> Cited reviewers assigned disagreeing ratings for related claims. Inspect individual review contexts and dates carefully.
            </span>
          </div>
        )}

        {externalStatus?.has_stale_fact_checks && (
          <div className="flex items-start gap-2 rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs text-amber-900 dark:text-amber-200">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
            <span>
              <strong>Stale Review Notice:</strong> One or more matched ClaimReviews may predate post-review events or current-officeholder changes.
            </span>
          </div>
        )}

        {factCheckMatches.length === 0 ? (
          <p className="text-xs italic text-slate-600 dark:text-slate-400 py-1">
            {formatGoogleStatusMessage(googleStatus, externalStatus?.google_fact_check_error)}
          </p>
        ) : (
          <div className="space-y-3">
            {factCheckMatches.map((fc, idx) => (
              <div
                key={`${fc.review_url || 'fc'}-${idx}`}
                className="rounded-xl border border-border bg-slate-50/80 dark:bg-slate-900/40 p-4 space-y-2.5"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-xs text-foreground">
                        {fc.publisher_name || fc.publisher_site || 'Independent Reviewer'}
                      </span>
                      {fc.reviewer_name && fc.reviewer_name !== fc.publisher_name && (
                        <span className="text-[11px] text-slate-600 dark:text-slate-400">
                          (Reviewer: {fc.reviewer_name})
                        </span>
                      )}
                      {fc.is_conflicting && (
                        <span className="rounded border border-rose-300 dark:border-rose-500/30 bg-rose-50 dark:bg-rose-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-rose-700 dark:text-rose-300">
                          Conflicting Rating
                        </span>
                      )}
                      {fc.is_stale && (
                        <span
                          title={fc.stale_reason || 'Possibly outdated relative to current claim context'}
                          className="rounded border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-800 dark:text-amber-300"
                        >
                          Potentially Stale
                        </span>
                      )}
                    </div>
                    {fc.review_title && (
                      <div className="text-xs font-medium text-slate-800 dark:text-slate-200">
                        {fc.review_title}
                      </div>
                    )}
                  </div>

                  {/* Original Rating Verbatim Badge */}
                  <span
                    className={cn(
                      'rounded-full border px-3 py-1 text-xs font-bold tracking-wide shrink-0',
                      fc.rating_text
                        ? 'bg-violet-50 dark:bg-brand-violet/15 text-violet-800 dark:text-violet-200 border-violet-300 dark:border-brand-violet/40'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-border'
                    )}
                  >
                    Publisher Rating: "{fc.rating_text || 'Not Provided'}"
                  </span>
                </div>

                {fc.claim_text && (
                  <p className="text-xs text-slate-700 dark:text-slate-300 rounded-lg border-l-2 border-brand-violet/60 bg-white/70 dark:bg-slate-950/40 px-3 py-2">
                    <span className="font-semibold">Reviewed Claim: </span>
                    "{fc.claim_text}"
                  </p>
                )}

                {fc.is_stale && fc.stale_reason && (
                  <p className="text-[11px] text-amber-800 dark:text-amber-300">
                    {fc.stale_reason}
                  </p>
                )}

                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-600 dark:text-slate-400 pt-1">
                  <div className="flex flex-wrap items-center gap-3 font-mono">
                    {fc.review_publication_date && (
                      <span className="inline-flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        <span>Reviewed: {fc.review_publication_date}</span>
                      </span>
                    )}
                    {fc.claim_appearance_date && (
                      <span>Claim Date: {fc.claim_appearance_date}</span>
                    )}
                    {fc.original_claim_author && (
                      <span>Claimant: {fc.original_claim_author}</span>
                    )}
                  </div>

                  {fc.review_url && (
                    <a
                      href={fc.review_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 font-medium text-brand-blue hover:underline"
                    >
                      <span>Read Publisher Review</span>
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 2. GDELT DOC 2.0 Global News Coverage Discovery */}
      <div className="glass-panel rounded-2xl p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
          <div className="space-y-0.5">
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-2">
              <Newspaper className="h-4 w-4 text-brand-cyan" />
              <span>GDELT News Coverage Discovery ({newsEvidence.length})</span>
            </h4>
            <p className="text-[11px] text-slate-600 dark:text-slate-400">
              Recent English-language news coverage metadata from GDELT DOC 2.0 (`ArtList`) for context discovery.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {(externalStatus?.duplicates_collapsed ?? 0) > 0 && (
              <span className="rounded-md border border-border bg-slate-100 dark:bg-slate-800/70 px-2 py-0.5 font-mono text-[10px] text-slate-700 dark:text-slate-300">
                {externalStatus?.duplicates_collapsed} syndicated/dupes collapsed
              </span>
            )}
            <span className="rounded-md border border-border bg-slate-100 dark:bg-slate-800/80 px-2.5 py-0.5 font-mono text-[11px] text-slate-700 dark:text-slate-300">
              Status: {gdeltStatus}
            </span>
          </div>
        </div>

        {/* Epistemic Discovery Non-Proof Banner */}
        <div className="flex items-start gap-2 rounded-xl border border-sky-200 dark:border-cyan-500/25 bg-sky-50/80 dark:bg-cyan-950/20 px-3 py-2 text-[11px] text-sky-900 dark:text-cyan-200">
          <Globe className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          <span>
            <strong>Discovery Context Only:</strong> News headline matches, article volume, and syndicated counts do NOT establish factual truth or falsehood and never alter the six-class verification verdict by popularity.
          </span>
        </div>

        {externalStatus?.gdelt_conflicting_coverage && (
          <div className="flex items-start gap-2 rounded-xl border border-amber-300 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-950/30 p-3 text-xs text-amber-900 dark:text-amber-200">
            <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
            <span>
              <strong>Mixed News Framing Detected:</strong> Retrieved coverage contains both affirmative and skeptical/denying headline signals.
            </span>
          </div>
        )}

        {newsEvidence.length === 0 ? (
          <p className="text-xs italic text-slate-600 dark:text-slate-400 py-1">
            {formatGdeltStatusMessage(gdeltStatus, externalStatus?.gdelt_error)}
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {newsEvidence.map((item, idx) => (
              <div
                key={`${item.url}-${idx}`}
                className="rounded-xl border border-border bg-slate-50/80 dark:bg-slate-900/40 p-3.5 flex flex-col justify-between gap-2.5"
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2 text-[11px] text-slate-600 dark:text-slate-400">
                    <span className="font-semibold text-brand-blue truncate">
                      {item.domain}
                    </span>
                    {item.syndicated_count > 1 && (
                      <span className="rounded bg-slate-200/80 dark:bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-700 dark:text-slate-300 shrink-0">
                        {item.syndicated_count} copies collapsed
                      </span>
                    )}
                  </div>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group inline-flex items-start gap-1.5 text-xs font-semibold text-foreground hover:text-brand-blue leading-snug"
                  >
                    <span>{item.title}</span>
                    <ExternalLink className="h-3 w-3 shrink-0 mt-0.5 text-slate-400 group-hover:text-brand-blue" />
                  </a>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-slate-600 dark:text-slate-400 pt-1 border-t border-border/70">
                  <span>{item.published_at || 'Date not supplied'}</span>
                  <span>
                    {[item.language, item.source_country].filter(Boolean).join(' · ') || item.search_window}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 3. Shared External API Usage & Quota Indicator */}
      {externalStatus?.gdelt_usage && (
        <ExternalApiUsageCard
          usage={externalStatus.gdelt_usage}
          googleAvailable={externalStatus.google_fact_check_available}
          compact={compact}
        />
      )}
    </div>
  );
};
