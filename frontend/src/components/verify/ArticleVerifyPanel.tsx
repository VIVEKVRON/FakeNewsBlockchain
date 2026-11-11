import React, { useState } from 'react';
import { FileText, Sliders, Send } from 'lucide-react';
import { verifyArticle } from '@/api/verify';
import type { ArticleVerificationResponse } from '@/types/verification';
import { LoadingSkeleton } from '@/components/ui/LoadingSkeleton';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { RippleButton } from '@/components/ui/RippleButton';
import { ArticleVerificationResult } from './ArticleVerificationResult';
import { useHistory } from '@/hooks/useHistory';

const SAMPLE_ARTICLES = [
  {
    label: 'Genuine Article',
    title: 'TLC Reality Series Follows Duggar Family',
    text:
      '19 Kids and Counting is an American reality television show featuring the Duggar family. ' +
      'The reality show focused on the life of the Duggar family who are devout Baptists.',
  },
  {
    label: 'Partially True Article',
    title: 'Mixed Apollo 11 & Duggar Facts',
    text:
      '19 Kids and Counting is an American reality television show featuring the Duggar family. ' +
      'However, 19 Kids and Counting was cancelled in 2030 after decades on air.',
  },
  {
    label: 'Fake Article',
    title: 'Television Show Cancellation Date Rumors',
    text:
      '19 Kids and Counting was cancelled in 2030. ' +
      'Industry analysts claimed that network executives delayed the official cancellation ' +
      'until the beginning of the next decade.',
  },
  {
    label: 'Misleading Broadcaster',
    title: 'Television Network Broadcasting History',
    text:
      '19 Kids and Counting aired on HBO. ' +
      'The show attracted millions of viewers across the country during its primetime weekend broadcast slot.',
  },
  {
    label: 'Unverified Futuristic',
    title: 'Alien Potatoes Discovered on Pluto',
    text:
      'Biologists discovered alien potatoes on Pluto in 2026. ' +
      'The extraterrestrial tubers supposedly survive in sub-zero atmospheric methane.',
  },
];

interface ArticleVerifyPanelProps {
  showHeader?: boolean;
}

export const ArticleVerifyPanel: React.FC<ArticleVerifyPanelProps> = ({
  showHeader = true,
}) => {
  const { addArticleVerification } = useHistory();

  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [maxClaims, setMaxClaims] = useState(3);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ArticleVerificationResponse | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || text.trim().length < 20) {
      setError('Article text must contain at least 20 characters.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await verifyArticle({
        title: title.trim() || undefined,
        text: text.trim(),
        max_claims: maxClaims,
      });
      setResult(response);
      addArticleVerification(response);
    } catch (err: any) {
      setError(err.message || 'Article verification failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleSelectSample = (sample: (typeof SAMPLE_ARTICLES)[0]) => {
    setTitle(sample.title);
    setText(sample.text);
  };

  return (
    <div className="space-y-8">
      {showHeader && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-indigo-600 dark:text-cyan-300">
            <FileText className="h-4 w-4" />
            <span>Full-Document Fact Verification</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
            Full Article Fact Verification
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Extracts declarative factual claims, retrieves Wikipedia evidence, scores stylistic patterns via ISOT BERT, and synthesizes overall truth.
          </p>
        </div>
      )}

      {/* Input Form Card (No Tilt on forms) */}
      <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6">
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-1.5">
            <label htmlFor="article-title" className="text-xs font-semibold text-foreground">
              Article Headline / Title <span className="text-slate-500 font-normal">(Optional)</span>
            </label>
            <input
              id="article-title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. TLC Reality Series Follows Duggar Family"
              className="glass-surface w-full rounded-xl px-4 py-2.5 text-sm text-foreground placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 transition-all"
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <label htmlFor="article-text" className="font-semibold text-foreground">
                Article Body Text
              </label>
              <span className="text-slate-600 dark:text-slate-400 font-mono">
                {text.length} / 50,000 chars
              </span>
            </div>
            <textarea
              id="article-text"
              rows={6}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste complete article text here to extract factual claims..."
              className="glass-surface w-full rounded-2xl p-4 text-sm text-foreground placeholder:text-slate-500 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 transition-all"
            />
          </div>

          <div className="space-y-2">
            <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Quick Benchmarks:</span>
            <div className="flex flex-wrap gap-2">
              {SAMPLE_ARTICLES.map((sample, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSelectSample(sample)}
                  className="glass-surface rounded-lg px-2.5 py-1 text-xs text-slate-700 dark:text-slate-300 hover:border-cyan-400/50 hover:text-brand-blue dark:hover:text-cyan-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                >
                  {sample.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-t border-border/70 pt-4">
            <div className="flex items-center gap-3">
              <Sliders className="h-4 w-4 text-slate-500 dark:text-slate-400" />
              <label htmlFor="max-claims-slider" className="text-xs font-medium text-slate-700 dark:text-slate-300">
                Max Claims to Extract:
              </label>
              <input
                id="max-claims-slider"
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
              disabled={loading || text.length < 20}
              className="rounded-xl px-6 py-2.5 text-sm"
            >
              <Send className="h-4 w-4" />
              <span>Verify Article</span>
            </RippleButton>
          </div>
        </form>
      </div>

      {loading && (
        <LoadingSkeleton message="Extracting Key Claims & Running Batched CPU Verification Pipeline..." />
      )}

      {error && <ErrorBanner message={error} onRetry={() => handleSubmit({ preventDefault: () => {} } as React.FormEvent)} />}

      {result && !loading && <ArticleVerificationResult result={result} />}
    </div>
  );
};
