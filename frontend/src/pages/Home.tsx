import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  Blocks,
  Cpu,
  Database,
  FileCheck2,
  FileText,
  Image as ImageIcon,
  Link2,
  Radio,
  SearchCheck,
  Server,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import {
  checkBackendHealth,
  getHistoryRecords,
} from '@/api/verify';
import type { BackendHealth } from '@/types/verification';
import { TiltCard } from '@/components/ui/TiltCard';
import { RippleButton } from '@/components/ui/RippleButton';
import { VerdictBadge } from '@/components/ui/VerdictBadge';

export const Home: React.FC = () => {
  const navigate = useNavigate();
  const [quickClaim, setQuickClaim] = useState('');

  const [health, setHealth] = useState<BackendHealth | null>(null);
  const [backendOffline, setBackendOffline] = useState(false);
  const [historyTotal, setHistoryTotal] = useState<number | null>(null);
  const [confirmedCount, setConfirmedCount] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const loadTelemetry = async () => {
      const [healthRes, histRes, anchoredRes] = await Promise.allSettled([
        checkBackendHealth(),
        getHistoryRecords({ limit: 1 }),
        getHistoryRecords({ limit: 1, blockchain_status: 'confirmed' }),
      ]);

      if (!mounted) return;
      if (healthRes.status === 'fulfilled') {
        setHealth(healthRes.value);
        setBackendOffline(false);
      } else {
        setBackendOffline(true);
      }

      if (histRes.status === 'fulfilled') {
        setHistoryTotal(histRes.value.total);
      }

      if (anchoredRes.status === 'fulfilled') {
        setConfirmedCount(anchoredRes.value.total);
      }
    };
    loadTelemetry();
    return () => {
      mounted = false;
    };
  }, []);

  const handleQuickVerify = (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickClaim.trim()) {
      navigate('/verify');
      return;
    }
    navigate('/verify?tab=text', { state: { prefillClaim: quickClaim.trim() } });
  };

  return (
    <div className="mx-auto max-w-7xl space-y-12 px-4 py-8 sm:px-6 sm:py-12">
      {/* Hero Banner */}
      <section className="glass-panel relative overflow-hidden rounded-3xl border-cyan-500/25 p-6 sm:p-12">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-28 -right-24 h-80 w-80 rounded-full opacity-50 dark:opacity-80"
          style={{
            background:
              'radial-gradient(circle, rgba(0, 200, 255, 0.16) 0%, rgba(8, 123, 255, 0.05) 55%, transparent 74%)',
          }}
        />

        <div className="relative z-10 max-w-3xl space-y-6">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/35 bg-cyan-500/10 px-3.5 py-1 text-xs font-semibold text-brand-blue dark:text-cyan-300">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Evidence-First AI Verification &amp; Ethereum Sepolia Auditability</span>
          </div>

          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-foreground leading-[1.1]">
            Truth deserves verification.
          </h1>

          <p className="text-sm sm:text-base text-slate-600 dark:text-slate-300/90 leading-relaxed max-w-2xl">
            Evaluate claims and full news articles against a 126,000-sentence FEVER FAISS index,
            live Wikipedia retrieval, DeBERTa-v3 NLI alignment gating, Google Fact Check, and
            GDELT coverage &mdash; anchored cryptographically with verifiable PDF certificates.
          </p>

          {/* Hero Quick Claim Dispatch */}
          <form onSubmit={handleQuickVerify} className="pt-1">
            <div className="glass-surface flex flex-col sm:flex-row items-stretch gap-2.5 rounded-2xl p-2 shadow-sm">
              <input
                type="text"
                value={quickClaim}
                onChange={(e) => setQuickClaim(e.target.value)}
                placeholder="Paste a factual news claim to verify in the unified workspace..."
                aria-label="Quick claim input"
                className="flex-1 bg-transparent px-4 py-2.5 text-sm text-foreground placeholder:text-slate-500 focus:outline-none"
              />
              <RippleButton
                type="submit"
                variant="primary"
                className="rounded-xl px-6 py-2.5 text-sm shrink-0"
              >
                <span>Verify Now</span>
                <ArrowRight className="h-4 w-4" />
              </RippleButton>
            </div>
          </form>

          {/* Secondary Action Row */}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Link
              to="/dashboard"
              className="glass-surface inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold text-foreground hover:border-cyan-400/45 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
            >
              <span>Open Operations Dashboard</span>
              <ArrowRight className="h-3.5 w-3.5 text-brand-cyan" />
            </Link>

            <Link
              to="/blockchain"
              className="glass-surface inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold text-foreground hover:border-cyan-400/45 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
            >
              <Blocks className="h-3.5 w-3.5 text-indigo-500 dark:text-indigo-300" />
              <span>Verify a Certificate</span>
            </Link>
          </div>
        </div>
      </section>

      {/* Real Backend Telemetry Metrics (Zero hardcoded fake statistics) */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold tracking-tight text-foreground">
            Live Platform Telemetry
          </h2>
          <span className="text-xs font-mono text-slate-600 dark:text-slate-400">
            Fetched live from local FastAPI &amp; Sepolia endpoints
          </span>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <TiltCard className="p-5">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 font-medium">
                <span>Backend Engine</span>
                <Server className="h-4 w-4 text-brand-cyan" />
              </div>
              <div className="text-xl sm:text-2xl font-extrabold font-mono text-foreground">
                {health ? 'Online' : backendOffline ? 'Offline' : 'Checking...'}
              </div>
              <div className="text-[11px] text-slate-600 dark:text-slate-400">
                {health ? `FastAPI v${health.version}` : 'Local CPU verification node'}
              </div>
            </div>
          </TiltCard>

          <TiltCard className="p-5">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 font-medium">
                <span>Stored Checks</span>
                <Database className="h-4 w-4 text-brand-blue dark:text-cyan-300" />
              </div>
              <div className="text-xl sm:text-2xl font-extrabold font-mono text-foreground">
                {historyTotal !== null ? historyTotal.toLocaleString() : '—'}
              </div>
              <div className="text-[11px] text-slate-600 dark:text-slate-400">
                Persistent SQLite records
              </div>
            </div>
          </TiltCard>

          <TiltCard className="border-indigo-500/25 p-5">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-indigo-700 dark:text-indigo-300 font-medium">
                <span>On-Chain Proofs</span>
                <Blocks className="h-4 w-4 text-indigo-500 dark:text-indigo-300" />
              </div>
              <div className="text-xl sm:text-2xl font-extrabold font-mono text-foreground">
                {confirmedCount !== null ? confirmedCount.toLocaleString() : '—'}
              </div>
              <div className="text-[11px] text-slate-600 dark:text-slate-400">
                Ethereum Sepolia confirmed
              </div>
            </div>
          </TiltCard>

          <TiltCard className="p-5">
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 font-medium">
                <span>FEVER Index</span>
                <Cpu className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="text-xl sm:text-2xl font-extrabold font-mono text-foreground">
                126,000
              </div>
              <div className="text-[11px] text-slate-600 dark:text-slate-400">
                Indexed Wikipedia vectors
              </div>
            </div>
          </TiltCard>
        </div>
      </section>

      {/* Core Platform Pillars */}
      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-bold tracking-tight text-foreground">
            Unified Verification Workspace
          </h2>
          <Link
            to="/verify"
            className="nav-link-underline text-xs font-semibold text-brand-blue dark:text-cyan-300"
          >
            Open /verify &rarr;
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <Link to="/verify?tab=text" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-5">
              <div className="space-y-2.5">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-blue/15 text-brand-blue dark:text-cyan-300">
                  <FileCheck2 className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-bold text-foreground group-hover:text-brand-blue dark:group-hover:text-cyan-300 transition-colors">
                  Text Claim Engine
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Decompose claims and validate entailment against FEVER + live Wikipedia + DeBERTa NLI.
                </p>
              </div>
            </TiltCard>
          </Link>

          <Link to="/verify?tab=article" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-5">
              <div className="space-y-2.5">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/15 text-indigo-600 dark:text-indigo-300">
                  <FileText className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-bold text-foreground group-hover:text-indigo-600 dark:group-hover:text-indigo-300 transition-colors">
                  Full Article Synthesis
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Extract multi-sentence factual claims with ISOT stylistic context and claim-by-claim verdicts.
                </p>
              </div>
            </TiltCard>
          </Link>

          <Link to="/verify?tab=url" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-5">
              <div className="space-y-2.5">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-700 dark:text-cyan-300">
                  <Link2 className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-bold text-foreground group-hover:text-cyan-700 dark:group-hover:text-cyan-300 transition-colors">
                  Source URL &amp; Cache
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Attach source URLs alongside article body text or verify cached RSS / GDELT headlines.
                </p>
              </div>
            </TiltCard>
          </Link>

          <Link to="/verify?tab=image" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-5">
              <div className="space-y-2.5">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/15 text-emerald-700 dark:text-emerald-300">
                  <ImageIcon className="h-5 w-5" />
                </div>
                <h3 className="text-sm font-bold text-foreground group-hover:text-emerald-700 dark:group-hover:text-emerald-300 transition-colors">
                  Image OCR &amp; ELA
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Transcribe embedded news text via PaddleOCR and inspect JPEG compression variance maps.
                </p>
              </div>
            </TiltCard>
          </Link>
        </div>
      </section>

      {/* Auditability & Verdict Standards */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel rounded-3xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-brand-cyan" />
              <h2 className="text-base font-bold text-foreground">Six-Class Verdict Standard</h2>
            </div>
            <Link to="/about" className="nav-link-underline text-xs font-semibold text-brand-blue dark:text-cyan-300">
              Methodology &rarr;
            </Link>
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            Every claim is graded strictly on independently retrieved evidence &mdash; never treating missing retrieval as falsification.
          </p>
          <div className="flex flex-wrap gap-2">
            <VerdictBadge verdict="GENUINE" size="sm" />
            <VerdictBadge verdict="FAKE" size="sm" />
            <VerdictBadge verdict="MISLEADING" size="sm" />
            <VerdictBadge verdict="PARTIALLY_TRUE" size="sm" />
            <VerdictBadge verdict="OUTDATED" size="sm" />
            <VerdictBadge verdict="UNVERIFIED" size="sm" />
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <SearchCheck className="h-5 w-5 text-indigo-500 dark:text-indigo-300" />
              <h2 className="text-base font-bold text-foreground">Explore Evidence &amp; On-Chain Proofs</h2>
            </div>
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            Inspect historical NLI evidence passages in SQLite, track live RSS/GDELT ingestion, or verify QR-coded certificates directly against Ethereum Sepolia.
          </p>
          <div className="flex flex-wrap gap-2.5">
            <Link
              to="/evidence"
              className="glass-surface inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold text-foreground hover:border-cyan-400/45 transition-colors"
            >
              <SearchCheck className="h-3.5 w-3.5 text-brand-cyan" />
              <span>Evidence Explorer</span>
            </Link>
            <Link
              to="/live"
              className="glass-surface inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold text-foreground hover:border-cyan-400/45 transition-colors"
            >
              <Radio className="h-3.5 w-3.5 text-brand-blue dark:text-cyan-300" />
              <span>Live News Monitor</span>
            </Link>
            <Link
              to="/blockchain"
              className="glass-surface inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold text-foreground hover:border-cyan-400/45 transition-colors"
            >
              <Blocks className="h-3.5 w-3.5 text-indigo-500 dark:text-indigo-300" />
              <span>Blockchain Records</span>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
};
