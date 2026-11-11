import React, { useState, useEffect } from 'react';
import {
  Radio,
  Rss,
  Globe,
  RefreshCw,
  Search,
  ExternalLink,
  Clock,
  ShieldCheck,
  X,
  Database,
  CheckCircle2,
  Server
} from 'lucide-react';
import { getNews, refreshNews, getNewsSources, verifyNewsArticle, getExternalUsage, checkBackendHealth } from '@/api/verify';
import type { NewsArticle, NewsSource, ArticleVerificationResponse, GdeltUsageStatus } from '@/types/verification';
import { VerdictBadge } from '@/components/ui/VerdictBadge';
import { EvidenceCard } from '@/components/ui/EvidenceCard';
import { EvidenceAuditTrailCard } from '@/components/ui/EvidenceAuditTrailCard';
import { ExternalEvidenceSection } from '@/components/ui/ExternalEvidenceSection';
import { ExternalApiUsageCard } from '@/components/ui/ExternalApiUsageCard';
import { ModelSignalCard } from '@/components/ui/ModelSignalCard';
import { LimitationsCallout } from '@/components/ui/LimitationsCallout';
import { LoadingSkeleton } from '@/components/ui/LoadingSkeleton';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { GlassSelect } from '@/components/ui/GlassSelect';
import { RippleButton } from '@/components/ui/RippleButton';
import { getVerdictPanelAccent } from '@/lib/utils';

const PUBLISHER_OPTIONS = [
  { value: 'ALL', label: 'All Publishers' },
  { value: 'BBC', label: 'BBC News' },
  { value: 'NPR', label: 'NPR' },
  { value: 'New York Times', label: 'New York Times' },
  { value: 'Phys.org', label: 'Phys.org' },
  { value: 'GDELT', label: 'GDELT' },
];

export const LiveNews: React.FC = () => {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [sources, setSources] = useState<NewsSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('ALL');
  const [selectedPublisher, setSelectedPublisher] = useState('ALL');

  // Verification modal & shared external usage state
  const [verifyingId, setVerifyingId] = useState<string | null>(null);
  const [verificationResult, setVerificationResult] = useState<ArticleVerificationResponse | null>(null);
  const [activeArticleForModal, setActiveArticleForModal] = useState<NewsArticle | null>(null);
  const [gdeltUsage, setGdeltUsage] = useState<GdeltUsageStatus | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  const fetchExternalUsage = async () => {
    setUsageLoading(true);
    try {
      const usage = await getExternalUsage();
      setGdeltUsage(usage);
    } catch {
      // Usage fetch non-critical
    } finally {
      setUsageLoading(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    checkBackendHealth()
      .then(() => {
        if (mounted) setBackendOnline(true);
      })
      .catch(() => {
        if (mounted) setBackendOnline(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const fetchNews = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getNews({
        keyword: search.trim() || undefined,
        category: selectedCategory !== 'ALL' ? selectedCategory : undefined,
        publisher: selectedPublisher !== 'ALL' ? selectedPublisher : undefined,
        limit: 30,
      });
      setArticles(res.articles);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch cached news articles.');
    } finally {
      setLoading(false);
    }
  };

  const fetchSources = async () => {
    try {
      const sRes = await getNewsSources();
      setSources(sRes.sources);
    } catch {
      // Sources fetch non-critical
    }
  };

  useEffect(() => {
    fetchNews();
    fetchSources();
    fetchExternalUsage();
  }, [selectedCategory, selectedPublisher]);

  useEffect(() => {
    if (!activeArticleForModal) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setActiveArticleForModal(null);
        setVerificationResult(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [activeArticleForModal]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchNews();
  };

  const handleRefreshFeeds = async () => {
    setRefreshing(true);
    setRefreshMsg(null);
    setError(null);
    try {
      const res = await refreshNews();
      const errSuffix =
        res.errors && res.errors.length > 0
          ? ` Warnings: ${res.errors.join(' | ')}`
          : '';
      setRefreshMsg(
        `Ingested ${res.new_articles_saved} new articles (${res.duplicates_skipped} duplicates skipped across ${res.sources_succeeded} sources).${errSuffix}`
      );
      if (res.gdelt_usage) {
        setGdeltUsage(res.gdelt_usage);
      } else {
        await fetchExternalUsage();
      }
      await fetchNews();
      await fetchSources();
    } catch (err: any) {
      setError(err.message || 'Feed refresh failed.');
    } finally {
      setRefreshing(false);
    }
  };

  const handleVerifyArticle = async (article: NewsArticle) => {
    setVerifyingId(article.id);
    setActiveArticleForModal(article);
    setVerificationResult(null);
    setError(null);

    try {
      const res = await verifyNewsArticle(article.id);
      setVerificationResult(res);
      if (res.external_source_status?.gdelt_usage) {
        setGdeltUsage(res.external_source_status.gdelt_usage);
      } else {
        fetchExternalUsage();
      }

      // Update local article list with verified verdict
      setArticles((prev) =>
        prev.map((a) =>
          a.id === article.id ? { ...a, verified_verdict: res.overall_verdict } : a
        )
      );
    } catch (err: any) {
      setError(err.message || 'Article verification failed.');
    } finally {
      setVerifyingId(null);
    }
  };

  const categories = ['ALL', 'World', 'Top Stories', 'International', 'Science', 'Global'];

  return (
    <div className="space-y-8 p-4 sm:p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-blue dark:text-cyan-300">
            <Radio className="h-4 w-4" />
            <span>Real-Time Ingestion &middot; RSS &amp; GDELT 2.0</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
            Live Breaking News Monitor
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Ingests public RSS feeds and GDELT 2.0 with local SQLite deduplication and one-click factual verification.
          </p>
        </div>

        {/* Action: Refresh Feeds Button */}
        <RippleButton
          variant="primary"
          onClick={handleRefreshFeeds}
          disabled={refreshing}
          className="rounded-xl px-4 py-2.5 text-xs shrink-0"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
          <span>{refreshing ? 'Refreshing Feeds...' : 'Refresh Feeds'}</span>
        </RippleButton>
      </div>

      {/* Sources & Status Bar */}
      <div className="glass-panel rounded-2xl p-4 flex flex-col md:flex-row items-start md:items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-3 text-slate-600 dark:text-slate-400">
          <span className="flex items-center gap-1.5 font-semibold text-foreground">
            <Database className="h-4 w-4 text-brand-cyan" />
            <span>Local Cache: {articles.length} articles</span>
          </span>
          <span>&middot;</span>
          <span className="flex items-center gap-1.5">
            <Rss className="h-3.5 w-3.5 text-brand-blue dark:text-cyan-400" />
            <span>{sources.length} Monitored Feeds (BBC, NPR, NYT, Phys, GDELT)</span>
          </span>
          <span>&middot;</span>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold border ${
              backendOnline === true
                ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                : backendOnline === false
                ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30'
                : 'glass-surface text-slate-600 dark:text-slate-400'
            }`}
          >
            <Server className="h-3 w-3" />
            <span>
              Backend: {backendOnline === true ? 'Online' : backendOnline === false ? 'Offline' : 'Checking'}
            </span>
          </span>
        </div>

        <div className="text-[11px] font-mono text-slate-600 dark:text-slate-400">
          {refreshMsg ? (
            <span className="text-emerald-700 dark:text-emerald-400 font-semibold">{refreshMsg}</span>
          ) : (
            <span>SSRF Safe &middot; Zero Paid APIs &middot; ₹0 Budget</span>
          )}
        </div>
      </div>

      {/* Shared External API Usage & Quota Panel */}
      <ExternalApiUsageCard
        usage={gdeltUsage}
        onRefresh={fetchExternalUsage}
        refreshing={usageLoading}
        compact
      />

      {/* Search & Filter Controls */}
      <div className="space-y-3">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          {/* Keyword Search */}
          <form onSubmit={handleSearchSubmit} className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 dark:text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search breaking headlines or keywords..."
              className="glass-surface w-full rounded-xl pl-10 pr-24 py-2 text-xs text-foreground placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none"
            />
            <button
              type="submit"
              className="glass-panel absolute right-1.5 top-1/2 -translate-y-1/2 rounded-lg px-3 py-1 text-[11px] font-semibold text-foreground hover:border-cyan-400/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
            >
              Search
            </button>
          </form>

          {/* Category & Publisher Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-1.5">
              {categories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSelectedCategory(cat)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 ${
                    selectedCategory === cat
                      ? 'btn-primary-glow text-white'
                      : 'glass-surface text-slate-600 dark:text-slate-300 hover:border-cyan-400/45 hover:text-foreground'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>

            <GlassSelect
              value={selectedPublisher}
              onChange={setSelectedPublisher}
              options={PUBLISHER_OPTIONS}
              ariaLabel="Filter by publisher"
            />
          </div>
        </div>
      </div>

      {/* Error state */}
      {error && <ErrorBanner message={error} onRetry={fetchNews} />}

      {/* Loading state */}
      {loading && <LoadingSkeleton message="Retrieving cached live news and running deduplication..." />}

      {/* Articles Grid */}
      {!loading && articles.length === 0 ? (
        <div className="glass-panel rounded-3xl border-dashed p-12 text-center space-y-3">
          <Rss className="h-10 w-10 text-slate-500 mx-auto" />
          <h4 className="text-base font-bold text-foreground">No News Articles Found</h4>
          <p className="text-xs text-slate-600 dark:text-slate-400 max-w-sm mx-auto">
            Click <strong>"Refresh Feeds"</strong> above to ingest the latest live headlines from BBC, NPR, NYTimes, Phys.org, and GDELT 2.0.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {articles.map((art) => (
            <div
              key={art.id}
              className="glass-panel rounded-2xl p-5 flex flex-col justify-between gap-4 transition-all hover:border-cyan-400/40"
            >
              <div className="space-y-3">
                {/* Meta header */}
                <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400">
                  <div className="flex items-center gap-1.5 font-semibold text-brand-blue dark:text-cyan-300">
                    <Globe className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate max-w-[180px]">{art.publisher}</span>
                    <span className="glass-surface rounded px-1.5 py-0.5 text-[9px] font-mono text-slate-700 dark:text-slate-300 uppercase">
                      {art.source_type}
                    </span>
                  </div>

                  <span className="flex items-center gap-1 font-mono text-[11px] text-slate-600 dark:text-slate-400 shrink-0">
                    <Clock className="h-3 w-3" />
                    <span>
                      {art.published_at
                        ? new Date(art.published_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                        : 'Recent'}
                    </span>
                  </span>
                </div>

                {/* Headline */}
                <h4 className="text-sm sm:text-base font-bold text-foreground leading-snug">
                  <a
                    href={art.canonical_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-brand-blue dark:hover:text-cyan-300 transition-colors flex items-start gap-1.5 group"
                  >
                    <span>{art.title}</span>
                    <ExternalLink className="h-3.5 w-3.5 text-slate-500 group-hover:text-brand-blue dark:group-hover:text-cyan-300 shrink-0 mt-1" />
                  </a>
                </h4>

                {/* Snippet */}
                {art.description && (
                  <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-2 leading-relaxed">
                    {art.description}
                  </p>
                )}
              </div>

              {/* Card Footer: Category badge & Verification Action */}
              <div className="pt-3 border-t border-border/70 flex items-center justify-between gap-2">
                <span className="glass-surface rounded-md px-2 py-0.5 text-[10px] font-mono text-slate-600 dark:text-slate-400">
                  {art.category}
                </span>

                <div className="flex items-center gap-2">
                  {art.verified_verdict ? (
                    <VerdictBadge verdict={art.verified_verdict} size="sm" />
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleVerifyArticle(art)}
                      disabled={verifyingId === art.id}
                      className="flex items-center gap-1.5 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/35 px-3 py-1 text-xs font-semibold text-brand-blue dark:text-cyan-300 transition-colors disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                    >
                      <ShieldCheck className="h-3.5 w-3.5" />
                      <span>{verifyingId === art.id ? 'Verifying...' : 'Verify Article'}</span>
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Verification Detail Modal */}
      {(activeArticleForModal && (verificationResult || verifyingId)) && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Fact Verification Audit"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy-950/75 backdrop-blur-md"
        >
          <div className="glass-dropdown relative w-full max-w-4xl rounded-3xl p-6 space-y-5 max-h-[90vh] flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-border/70 pb-3">
              <div className="flex items-center gap-2 min-w-0">
                <ShieldCheck className="h-5 w-5 text-brand-blue dark:text-cyan-300 shrink-0" />
                <h3 className="font-bold text-foreground text-sm truncate">
                  Fact Verification Audit: {activeArticleForModal.title}
                </h3>
              </div>
              <button
                type="button"
                aria-label="Close modal"
                onClick={() => {
                  setActiveArticleForModal(null);
                  setVerificationResult(null);
                }}
                className="rounded-lg p-1.5 text-slate-500 dark:text-slate-400 hover:bg-cyan-500/10 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="flex-1 overflow-y-auto space-y-6 pr-1">
              {verifyingId && !verificationResult ? (
                <LoadingSkeleton message="Extracting claims and verifying against 126k FEVER Wikipedia index on CPU..." />
              ) : verificationResult ? (
                <div className="space-y-6">
                  {/* Overall truth verdict */}
                  <div className={`glass-surface rounded-2xl p-5 space-y-3 ${getVerdictPanelAccent(verificationResult.overall_verdict)}`}>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs uppercase tracking-wider text-slate-600 dark:text-slate-400 font-semibold">
                        Article Truth Verdict
                      </span>
                      <VerdictBadge verdict={verificationResult.overall_verdict} size="md" showDescription />
                    </div>
                    <p className="text-xs text-foreground leading-relaxed">
                      {verificationResult.summary_explanation}
                    </p>
                    {verificationResult.uncertainty_explanation && (
                      <p className="text-[11px] text-amber-900 dark:text-amber-200/85 bg-amber-500/10 border border-amber-500/25 rounded-lg p-2.5 leading-relaxed">
                        <strong>Uncertainty Note: </strong>
                        {verificationResult.uncertainty_explanation}
                      </p>
                    )}
                  </div>

                  {/* Secondary section: Experimental ML Signals */}
                  <ModelSignalCard
                    isotSignal={verificationResult.article_classifier}
                    className="border-amber-500/30"
                  />

                  {/* Primary section: Evidence-Based Verification */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between border-b border-border/70 pb-2">
                      <h4 className="text-xs font-bold text-foreground uppercase tracking-wider flex items-center gap-1.5">
                        <CheckCircle2 className="h-4 w-4 text-emerald-500 dark:text-emerald-400" />
                        <span>Evidence-Based Verification (FEVER + FAISS)</span>
                      </h4>
                      <span className="text-xs text-slate-600 dark:text-slate-400 font-mono">
                        {verificationResult.claims_analyzed} Claims Extracted
                      </span>
                    </div>

                    <div className="space-y-3">
                      {verificationResult.extracted_claims.map((cl, idx) => (
                        <div key={idx} className="glass-surface rounded-xl p-4 space-y-3">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-bold text-foreground">
                              Claim #{cl.relevance_rank}: "{cl.claim}"
                            </span>
                            <VerdictBadge verdict={cl.verdict} size="sm" />
                          </div>
                          <p className="text-xs text-slate-600 dark:text-slate-400">
                            {cl.explanation}
                          </p>

                          {cl.evidence.length > 0 && (
                            <div className="space-y-2 pt-1">
                              <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
                                Grounding Evidence
                              </span>
                              {cl.evidence.slice(0, 2).map((ev, eIdx) => (
                                <EvidenceCard key={eIdx} evidence={ev} index={eIdx} />
                              ))}
                            </div>
                          )}

                          {cl.evidence_audit_trail && (
                            <div className="pt-1">
                              <EvidenceAuditTrailCard auditTrail={cl.evidence_audit_trail} compact />
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* IEVE Audit Trail inside Modal */}
                  <EvidenceAuditTrailCard auditTrail={verificationResult.evidence_audit_trail} compact />

                  {/* External Supplementary Evidence inside Modal */}
                  <ExternalEvidenceSection
                    factCheckMatches={verificationResult.fact_check_matches}
                    newsEvidence={verificationResult.news_evidence}
                    externalStatus={verificationResult.external_source_status}
                    compact
                  />

                  {/* Limitations */}
                  <LimitationsCallout limitations={verificationResult.limitations} />
                </div>
              ) : null}
            </div>

            <div className="flex justify-end pt-2 border-t border-border/70">
              <RippleButton
                variant="glass"
                onClick={() => {
                  setActiveArticleForModal(null);
                  setVerificationResult(null);
                }}
                className="rounded-xl px-4 py-2 text-xs"
              >
                Close
              </RippleButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
