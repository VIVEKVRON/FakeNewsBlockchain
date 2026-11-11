import React, { useState } from 'react';
import {
  Link2,
  Info,
  Sliders,
  Send,
  Search,
  Database,
  ShieldCheck,
  ExternalLink,
  RefreshCw,
} from 'lucide-react';
import { verifyArticle, getNews, verifyNewsArticle } from '@/api/verify';
import type { ArticleVerificationResponse, NewsArticle } from '@/types/verification';
import { VerdictBadge } from '@/components/ui/VerdictBadge';
import { LoadingSkeleton } from '@/components/ui/LoadingSkeleton';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { RippleButton } from '@/components/ui/RippleButton';
import { ArticleVerificationResult } from './ArticleVerificationResult';
import { useHistory } from '@/hooks/useHistory';
import { cn } from '@/lib/utils';

export const ArticleUrlVerifyPanel: React.FC = () => {
  const { addArticleVerification } = useHistory();

  const [mode, setMode] = useState<'url_with_text' | 'cached_news'>('url_with_text');

  // Mode 1: Source URL metadata + pasted article text -> POST /api/v1/verify/article
  const [sourceUrl, setSourceUrl] = useState('');
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [maxClaims, setMaxClaims] = useState(3);

  // Mode 2: Cached news lookup & verify -> GET /api/v1/news + POST /api/v1/news/{id}/verify
  const [cachedQuery, setCachedQuery] = useState('');
  const [cachedArticles, setCachedArticles] = useState<NewsArticle[]>([]);
  const [cachedLoaded, setCachedLoaded] = useState(false);
  const [cachedLoading, setCachedLoading] = useState(false);

  const [loading, setLoading] = useState(false);
  const [verifyingCachedId, setVerifyingCachedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ArticleVerificationResponse | null>(null);

  const handleSubmitUrlWithText = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedUrl = sourceUrl.trim();
    if (trimmedUrl && !/^https?:\/\/\S+/i.test(trimmedUrl)) {
      setError('Please enter a valid http:// or https:// URL, or leave Source URL blank.');
      return;
    }
    if (!text.trim() || text.trim().length < 20) {
      setError(
        'Arbitrary URL scraping is not enabled by a backend endpoint. Please paste at least 20 characters of article text alongside the URL, or switch to Cached Live News lookup.'
      );
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await verifyArticle({
        source_url: trimmedUrl || undefined,
        title: title.trim() || undefined,
        text: text.trim(),
        max_claims: maxClaims,
      });
      setResult(response);
      addArticleVerification(response);
    } catch (err: any) {
      setError(err.message || 'Verification with source URL failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleLoadCachedNews = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setCachedLoading(true);
    setError(null);
    try {
      const res = await getNews({
        keyword: cachedQuery.trim() || undefined,
        limit: 12,
      });
      setCachedArticles(res.articles);
      setCachedLoaded(true);
    } catch (err: any) {
      setError(err.message || 'Failed to read cached news repository.');
    } finally {
      setCachedLoading(false);
    }
  };

  const handleVerifyCached = async (article: NewsArticle) => {
    setVerifyingCachedId(article.id);
    setLoading(true);
    setError(null);
    try {
      const res = await verifyNewsArticle(article.id);
      setResult(res);
      addArticleVerification(res);
      setCachedArticles((prev) =>
        prev.map((a) => (a.id === article.id ? { ...a, verified_verdict: res.overall_verdict } : a))
      );
    } catch (err: any) {
      setError(err.message || 'Failed to verify cached news article.');
    } finally {
      setLoading(false);
      setVerifyingCachedId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Honest API Limitation Notice */}
      <div className="glass-panel rounded-2xl border-cyan-500/30 bg-cyan-500/10 dark:bg-cyan-950/20 p-5 text-xs leading-relaxed flex items-start gap-3">
        <Info className="h-5 w-5 text-brand-blue dark:text-cyan-300 shrink-0 mt-0.5" />
        <div className="space-y-1.5 text-slate-700 dark:text-slate-300">
          <h2 className="font-bold text-foreground text-sm">
            Article URL Verification Scope &amp; API Boundaries
          </h2>
          <p>
            Arbitrary external URL fetching and web scraping are <strong>not supported</strong> by a standalone backend endpoint to uphold strict SSRF isolation and zero-cost execution.
            To verify URL-referenced reporting using existing APIs, choose either:
          </p>
          <ul className="list-disc list-inside space-y-0.5 text-[11px] text-slate-600 dark:text-slate-400">
            <li>
              <strong>Source URL + Pasted Article Text:</strong> Attach an optional <code className="font-mono text-foreground">source_url</code> reference alongside the article body via <code className="font-mono text-foreground">POST /api/v1/verify/article</code>.
            </li>
            <li>
              <strong>Cached Feed Article Verification:</strong> Select an already-ingested RSS or GDELT article from local SQLite storage and run <code className="font-mono text-foreground">POST /api/v1/news/&#123;article_id&#125;/verify</code>.
            </li>
          </ul>
        </div>
      </div>

      {/* Mode Switcher */}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => {
            setMode('url_with_text');
            setError(null);
          }}
          className={cn(
            'rounded-xl px-4 py-2 text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
            mode === 'url_with_text'
              ? 'btn-primary-glow text-white'
              : 'glass-surface text-slate-700 dark:text-slate-300 hover:border-cyan-400/45 hover:text-foreground'
          )}
        >
          1. Source URL + Pasted Text
        </button>

        <button
          type="button"
          onClick={() => {
            setMode('cached_news');
            setError(null);
            if (!cachedLoaded) {
              handleLoadCachedNews();
            }
          }}
          className={cn(
            'rounded-xl px-4 py-2 text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
            mode === 'cached_news'
              ? 'btn-primary-glow text-white'
              : 'glass-surface text-slate-700 dark:text-slate-300 hover:border-cyan-400/45 hover:text-foreground'
          )}
        >
          2. Verify Cached Live News Article
        </button>
      </div>

      {/* Mode 1 Form */}
      {mode === 'url_with_text' && (
        <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-5">
          <form onSubmit={handleSubmitUrlWithText} className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label htmlFor="source-url-input" className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                  <Link2 className="h-3.5 w-3.5 text-brand-cyan" />
                  <span>Article Source URL</span>
                  <span className="text-slate-500 font-normal">(Optional metadata)</span>
                </label>
                <input
                  id="source-url-input"
                  type="url"
                  value={sourceUrl}
                  onChange={(e) => setSourceUrl(e.target.value)}
                  placeholder="https://example.com/news/article"
                  className="glass-surface w-full rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 transition-all"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="url-article-title" className="text-xs font-semibold text-foreground">
                  Article Title <span className="text-slate-500 font-normal">(Optional)</span>
                </label>
                <input
                  id="url-article-title"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Optional headline from the referenced article"
                  className="glass-surface w-full rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 transition-all"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between items-center text-xs">
                <label htmlFor="url-article-text" className="font-semibold text-foreground">
                  Article Body Text <span className="text-rose-500 dark:text-rose-400">*</span>
                </label>
                <span className="text-slate-600 dark:text-slate-400 font-mono">
                  {text.length} / 50,000 chars
                </span>
              </div>
              <textarea
                id="url-article-text"
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste the text content from the URL above (minimum 20 characters; backend does not scrape external URLs)..."
                className="glass-surface w-full rounded-2xl p-4 text-sm text-foreground placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 transition-all"
              />
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-t border-border/70 pt-4">
              <div className="flex items-center gap-3">
                <Sliders className="h-4 w-4 text-slate-500 dark:text-slate-400" />
                <label htmlFor="url-max-claims" className="text-xs font-medium text-slate-700 dark:text-slate-300">
                  Max Claims to Extract:
                </label>
                <input
                  id="url-max-claims"
                  type="range"
                  min="1"
                  max="5"
                  value={maxClaims}
                  onChange={(e) => setMaxClaims(parseInt(e.target.value, 10))}
                  className="w-24 accent-brand-cyan"
                />
                <span className="text-xs font-mono font-semibold text-indigo-600 dark:text-cyan-300">
                  {maxClaims}
                </span>
              </div>

              <RippleButton
                type="submit"
                variant="primary"
                disabled={loading || !text.trim()}
                className="rounded-xl px-6 py-2.5 text-sm"
              >
                <Send className="h-4 w-4" />
                <span>Verify Source Article</span>
              </RippleButton>
            </div>
          </form>
        </div>
      )}

      {/* Mode 2: Cached News Verification */}
      {mode === 'cached_news' && (
        <div className="glass-panel rounded-3xl p-6 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
              <Database className="h-4 w-4 text-brand-cyan" />
              <span>Queries local SQLite news cache only (no live GDELT quota spent on lookup).</span>
            </div>
          </div>

          <form onSubmit={handleLoadCachedNews} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-500 dark:text-slate-400" />
              <input
                type="text"
                value={cachedQuery}
                onChange={(e) => setCachedQuery(e.target.value)}
                placeholder="Search cached article headlines or URLs..."
                className="glass-surface w-full rounded-xl pl-10 pr-4 py-2 text-xs sm:text-sm text-foreground placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none"
              />
            </div>
            <RippleButton type="submit" variant="primary" disabled={cachedLoading} className="rounded-xl px-4 py-2 text-xs">
              <RefreshCw className={`h-3.5 w-3.5 ${cachedLoading ? 'animate-spin' : ''}`} />
              <span>Search Cache</span>
            </RippleButton>
          </form>

          {cachedLoading ? (
            <LoadingSkeleton message="Searching local SQLite news cache..." />
          ) : cachedArticles.length === 0 ? (
            <div className="glass-surface rounded-2xl p-8 text-center text-xs text-slate-600 dark:text-slate-400">
              No cached articles matched. Visit <strong>Live News</strong> to refresh ingested feeds.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[360px] overflow-y-auto pr-1">
              {cachedArticles.map((art) => (
                <div
                  key={art.id}
                  className="glass-surface rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:border-cyan-400/40 transition-colors"
                >
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-600 dark:text-slate-400">
                      <span className="font-semibold text-brand-blue dark:text-cyan-300">{art.publisher}</span>
                      <span>&middot;</span>
                      <span className="uppercase font-mono">{art.source_type}</span>
                      {art.verified_verdict && <VerdictBadge verdict={art.verified_verdict} size="sm" />}
                    </div>
                    <p className="text-xs sm:text-sm font-semibold text-foreground truncate">{art.title}</p>
                    <a
                      href={art.canonical_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] font-mono text-indigo-700 dark:text-cyan-300/90 hover:underline truncate max-w-full"
                    >
                      <span className="truncate">{art.canonical_url}</span>
                      <ExternalLink className="h-3 w-3 shrink-0" />
                    </a>
                  </div>

                  <RippleButton
                    variant="glass"
                    onClick={() => handleVerifyCached(art)}
                    disabled={loading}
                    className="rounded-lg px-3 py-1.5 text-xs shrink-0"
                  >
                    <ShieldCheck className="h-3.5 w-3.5 text-brand-cyan" />
                    <span>{verifyingCachedId === art.id ? 'Verifying...' : 'Verify Article'}</span>
                  </RippleButton>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {loading && (
        <LoadingSkeleton message="Extracting Claims & Running Fact Verification Pipeline on CPU..." />
      )}

      {error && <ErrorBanner message={error} />}

      {result && !loading && <ArticleVerificationResult result={result} />}
    </div>
  );
};
