import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  FileCheck2,
  FileText,
  Image as ImageIcon,
  Radio,
  SearchCheck,
  ArrowRight,
  Cpu,
  Database,
  Layers,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Server,
  Activity,
  ExternalLink,
  Link2,
} from 'lucide-react';
import {
  checkBackendHealth,
  getBlockchainStatus,
  getExternalUsage,
  getHistoryRecords,
} from '@/api/verify';
import type {
  BackendHealth,
  BlockchainStatus,
  GdeltUsageStatus,
} from '@/types/verification';
import { useHistory } from '@/hooks/useHistory';
import { VerdictBadge } from '@/components/ui/VerdictBadge';
import { TiltCard } from '@/components/ui/TiltCard';
import { RippleButton } from '@/components/ui/RippleButton';
import { cn } from '@/lib/utils';

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const { history } = useHistory();
  const [quickClaim, setQuickClaim] = useState('');

  // Live backend, blockchain, SQLite & GDELT telemetry moved out of sidebar
  const [backendHealth, setBackendHealth] = useState<BackendHealth | null>(null);
  const [backendStatus, setBackendStatus] = useState<'online' | 'offline' | 'checking'>('checking');
  const [gdeltUsage, setGdeltUsage] = useState<GdeltUsageStatus | null>(null);
  const [chainStatus, setChainStatus] = useState<BlockchainStatus | null>(null);
  const [sqliteTotal, setSqliteTotal] = useState<number | null>(null);

  useEffect(() => {
    let mounted = true;
    const pollTelemetry = async () => {
      const [healthRes, usageRes, chainRes, histRes] = await Promise.allSettled([
        checkBackendHealth(),
        getExternalUsage(),
        getBlockchainStatus(),
        getHistoryRecords({ limit: 1 }),
      ]);
      if (!mounted) return;

      if (healthRes.status === 'fulfilled') {
        setBackendHealth(healthRes.value);
        setBackendStatus('online');
      } else {
        setBackendStatus('offline');
      }

      if (usageRes.status === 'fulfilled') {
        setGdeltUsage(usageRes.value);
      }

      if (chainRes.status === 'fulfilled') {
        setChainStatus(chainRes.value);
      }

      if (histRes.status === 'fulfilled') {
        setSqliteTotal(histRes.value.total);
      }
    };

    pollTelemetry();
    const interval = setInterval(pollTelemetry, 30000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  const handleQuickSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!quickClaim.trim()) return;
    navigate('/verify?tab=text', { state: { prefillClaim: quickClaim } });
  };

  // Compute metrics from actual localStorage session history
  const totalSessionVerified = history.length;
  const genuineCount = history.filter((h) => h.verdict === 'GENUINE' || h.verdict === 'LIKELY_GENUINE').length;
  const fakeCount = history.filter((h) => h.verdict === 'FAKE' || h.verdict === 'LIKELY_FAKE').length;

  const genuinePercent = totalSessionVerified > 0 ? Math.round((genuineCount / totalSessionVerified) * 100) : 0;
  const fakePercent = totalSessionVerified > 0 ? Math.round((fakeCount / totalSessionVerified) * 100) : 0;

  return (
    <div className="space-y-8 p-4 sm:p-8 max-w-7xl mx-auto">
      {/* Operational Hero */}
      <div className="glass-panel relative overflow-hidden rounded-3xl border-cyan-500/25 p-6 sm:p-10">
        <div className="relative z-10 max-w-3xl space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/35 bg-cyan-500/10 px-3 py-1 text-xs font-semibold text-brand-blue dark:text-cyan-300">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Intelligence Operations Dashboard</span>
          </div>

          <h1 className="text-2xl sm:text-4xl font-extrabold tracking-tight text-foreground leading-tight">
            Verification Operations &amp; System Telemetry
          </h1>

          <p className="text-sm sm:text-base text-slate-600 dark:text-slate-300/90 leading-relaxed">
            Dispatch single claims or documents through the DeBERTa-v3 NLI + 126k FEVER index pipeline,
            monitor real-time SQLite, Sepolia, and GDELT quota health, and review session checks.
          </p>

          <form onSubmit={handleQuickSubmit} className="pt-2">
            <div className="glass-surface flex flex-col sm:flex-row items-stretch gap-2.5 rounded-2xl p-2 shadow-sm">
              <input
                type="text"
                value={quickClaim}
                onChange={(e) => setQuickClaim(e.target.value)}
                placeholder="Enter a news claim to verify (e.g. '19 Kids and Counting features the Duggar family')..."
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
        </div>
      </div>

      {/* Session & Corpus Metrics Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <TiltCard className="p-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 font-medium">
              <span>Session Checks</span>
              <Database className="h-4 w-4 text-brand-cyan" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-foreground font-mono">
              {totalSessionVerified}
            </div>
            <div className="text-[11px] text-slate-600 dark:text-slate-400">
              Stored in local session
            </div>
          </div>
        </TiltCard>

        <TiltCard className="border-emerald-500/25 p-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-emerald-700 dark:text-emerald-400 font-medium">
              <span>Supported Ratio</span>
              <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-foreground font-mono">
              {genuinePercent}%
            </div>
            <div className="text-[11px] text-slate-600 dark:text-slate-400">
              {genuineCount} confirmed genuine
            </div>
          </div>
        </TiltCard>

        <TiltCard className="border-rose-500/25 p-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-rose-700 dark:text-rose-400 font-medium">
              <span>Refuted Ratio</span>
              <AlertTriangle className="h-4 w-4 text-rose-600 dark:text-rose-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-foreground font-mono">
              {fakePercent}%
            </div>
            <div className="text-[11px] text-slate-600 dark:text-slate-400">
              {fakeCount} refuted claims
            </div>
          </div>
        </TiltCard>

        <TiltCard className="p-5">
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 font-medium">
              <span>SQLite Ledger</span>
              <Cpu className="h-4 w-4 text-indigo-500 dark:text-cyan-400" />
            </div>
            <div className="text-2xl sm:text-3xl font-extrabold text-foreground font-mono">
              {sqliteTotal !== null ? sqliteTotal.toLocaleString() : '—'}
            </div>
            <div className="text-[11px] text-slate-600 dark:text-slate-400">
              Persistent verified records
            </div>
          </div>
        </TiltCard>
      </div>

      {/* Backend, Sepolia & GDELT Quota Telemetry Panel (Moved from Sidebar) */}
      <div className="glass-panel rounded-3xl p-6 space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/70 pb-4">
          <div className="flex items-center gap-2.5">
            <Server className="h-5 w-5 text-brand-cyan" />
            <div>
              <h2 className="text-base font-bold text-foreground">Backend &amp; External Quota Telemetry</h2>
              <p className="text-xs text-slate-600 dark:text-slate-400">
                Real-time service health, Sepolia smart-contract connection, and shared GDELT API allowance.
              </p>
            </div>
          </div>

          <a
            href="http://127.0.0.1:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="glass-surface inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-brand-blue dark:text-cyan-300 hover:border-cyan-400/45 transition-colors self-start sm:self-auto"
          >
            <Activity className="h-3.5 w-3.5" />
            <span>FastAPI Swagger Docs</span>
            <ExternalLink className="h-3 w-3" />
          </a>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
          {/* Backend Engine Status */}
          <div className="glass-surface rounded-2xl p-4 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground">FastAPI Inference Engine</span>
              <span
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold border',
                  backendStatus === 'online'
                    ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                    : backendStatus === 'checking'
                    ? 'bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-500/30'
                    : 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30'
                )}
              >
                <span
                  className={cn(
                    'h-1.5 w-1.5 rounded-full',
                    backendStatus === 'online'
                      ? 'bg-emerald-500 dark:bg-emerald-400'
                      : backendStatus === 'checking'
                      ? 'bg-amber-500 dark:bg-amber-400'
                      : 'bg-rose-500 dark:bg-rose-400'
                  )}
                />
                <span className="capitalize">{backendStatus}</span>
              </span>
            </div>
            <div className="space-y-1 text-[11px] text-slate-600 dark:text-slate-400 font-mono">
              <div className="flex justify-between">
                <span>Runtime:</span>
                <span className="text-foreground">
                  {backendHealth ? `v${backendHealth.version} (CPU 16 GB)` : '16 GB CPU Budget'}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Indexed Corpus:</span>
                <span className="text-foreground">126,000 Sentences</span>
              </div>
            </div>
          </div>

          {/* GDELT Quota Status */}
          <div className="glass-surface rounded-2xl p-4 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground">GDELT 2.0 Shared Allowance</span>
              <Link to="/live" className="nav-link-underline text-[11px] font-semibold text-brand-blue dark:text-cyan-300">
                Live Monitor &rarr;
              </Link>
            </div>
            {gdeltUsage ? (
              <div className="space-y-1 text-[11px] text-slate-600 dark:text-slate-400 font-mono">
                <div className="flex justify-between">
                  <span>Requests Used:</span>
                  <span
                    className={cn(
                      'font-semibold',
                      gdeltUsage.limit_reached
                        ? 'text-rose-600 dark:text-rose-400'
                        : gdeltUsage.warning_active
                        ? 'text-amber-600 dark:text-amber-400'
                        : 'text-foreground'
                    )}
                  >
                    {gdeltUsage.requests_used} / {gdeltUsage.allowance_limit} ({gdeltUsage.requests_remaining} left)
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Cache Hits / Failed:</span>
                  <span className="text-foreground">
                    {gdeltUsage.cache_hits} / {gdeltUsage.failed_requests}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-[11px] text-slate-600 dark:text-slate-400">
                Quota status unavailable while backend is unreachable.
              </p>
            )}
          </div>

          {/* Ethereum Sepolia Contract Telemetry */}
          <div className="glass-surface rounded-2xl p-4 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground">Sepolia Blockchain Anchor</span>
              <Link to="/blockchain" className="nav-link-underline text-[11px] font-semibold text-indigo-600 dark:text-indigo-300">
                Audit &rarr;
              </Link>
            </div>
            {chainStatus ? (
              <div className="space-y-1 text-[11px] text-slate-600 dark:text-slate-400 font-mono">
                <div className="flex justify-between">
                  <span>Network:</span>
                  <span className="text-foreground">
                    {chainStatus.network} ({chainStatus.connected ? 'Connected' : 'Disconnected'})
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>On-Chain Records:</span>
                  <span className="text-foreground">
                    {chainStatus.total_verifications ?? '—'}
                  </span>
                </div>
              </div>
            ) : (
              <p className="text-[11px] text-slate-600 dark:text-slate-400">
                Blockchain RPC status unavailable.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Module Navigation Grid */}
      <div className="space-y-4">
        <h2 className="text-lg font-bold text-foreground tracking-tight">
          System Verification Modules
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <Link to="/verify?tab=text" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-6">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-blue/15 text-brand-blue dark:text-cyan-300 transition-transform group-hover:scale-105">
                    <FileCheck2 className="h-6 w-6" />
                  </div>
                  <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                    Active &middot; FEVER
                  </span>
                </div>
                <h3 className="font-bold text-foreground text-base group-hover:text-brand-blue dark:group-hover:text-cyan-300 transition-colors">
                  Text Claim Verification
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Verify single news statements against the 126k FAISS index, live Wikipedia, and DeBERTa-v3 NLI engine.
                </p>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-brand-blue dark:text-cyan-300 pt-1">
                  <span>Launch Engine</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </TiltCard>
          </Link>

          <Link to="/verify?tab=article" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-6">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500/15 text-indigo-600 dark:text-indigo-300 transition-transform group-hover:scale-105">
                    <FileText className="h-6 w-6" />
                  </div>
                  <span className="rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2.5 py-0.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                    Active &middot; IEVE
                  </span>
                </div>
                <h3 className="font-bold text-foreground text-base group-hover:text-indigo-600 dark:group-hover:text-indigo-300 transition-colors">
                  Full Article &amp; URL Modes
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Extract key factual claims, attach source URLs, run ISOT stylistic detection, and synthesize truth.
                </p>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-300 pt-1">
                  <span>Open /verify</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </TiltCard>
          </Link>

          <Link to="/verify?tab=url" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-6">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 transition-transform group-hover:scale-105">
                    <Link2 className="h-6 w-6" />
                  </div>
                  <span className="glass-surface rounded-full px-2.5 py-0.5 text-xs font-mono text-slate-600 dark:text-slate-300">
                    Source + Cache
                  </span>
                </div>
                <h3 className="font-bold text-foreground text-base group-hover:text-cyan-700 dark:group-hover:text-cyan-300 transition-colors">
                  Article URL Workflow
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Verify pasted articles with source_url metadata or audit cached RSS/GDELT articles without SSRF risks.
                </p>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-700 dark:text-cyan-300 pt-1">
                  <span>Open URL Tab</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </TiltCard>
          </Link>

          <Link to="/verify?tab=image" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-6">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 transition-transform group-hover:scale-105">
                    <ImageIcon className="h-6 w-6" />
                  </div>
                  <span className="glass-surface rounded-full px-2.5 py-0.5 text-xs font-mono text-slate-600 dark:text-slate-300">
                    OCR + ELA
                  </span>
                </div>
                <h3 className="font-bold text-foreground text-base group-hover:text-cyan-700 dark:group-hover:text-cyan-300 transition-colors">
                  Multimodal Image Analysis
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  OCR text extraction via PaddleOCR and OpenCV Error Level Analysis (ELA) compression variance indicators.
                </p>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-700 dark:text-cyan-300 pt-1">
                  <span>Open Forensics</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </TiltCard>
          </Link>

          <Link to="/live" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-6">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 transition-transform group-hover:scale-105">
                    <Radio className="h-6 w-6" />
                  </div>
                  <span className="glass-surface rounded-full px-2.5 py-0.5 text-xs font-mono text-slate-600 dark:text-slate-300">
                    RSS / GDELT
                  </span>
                </div>
                <h3 className="font-bold text-foreground text-base group-hover:text-cyan-700 dark:group-hover:text-cyan-300 transition-colors">
                  Live Breaking News Monitor
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Ingest public RSS feeds and GDELT 2.0 events with SQLite deduplication and shared quota telemetry.
                </p>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-700 dark:text-cyan-300 pt-1">
                  <span>Open News Feed</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </TiltCard>
          </Link>

          <Link to="/evidence" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-6 border-indigo-500/25">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-cyan/15 text-cyan-700 dark:text-brand-cyan transition-transform group-hover:scale-105">
                    <SearchCheck className="h-6 w-6" />
                  </div>
                  <span className="glass-surface rounded-full px-2.5 py-0.5 text-xs font-mono text-slate-600 dark:text-slate-300">
                    SQLite + NLI
                  </span>
                </div>
                <h3 className="font-bold text-foreground text-base group-hover:text-cyan-700 dark:group-hover:text-cyan-300 transition-colors">
                  Evidence Explorer &amp; History
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Search historical checks, inspect evidence sentences, review session audit trails, and download certificates.
                </p>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-cyan-700 dark:text-cyan-300 pt-1">
                  <span>Explore Evidence ({sqliteTotal ?? totalSessionVerified})</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </TiltCard>
          </Link>

          <Link to="/blockchain" className="group block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70">
            <TiltCard className="h-full p-6 border-indigo-500/25">
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 transition-transform group-hover:scale-105">
                    <Layers className="h-6 w-6" />
                  </div>
                  <span className="rounded-full bg-indigo-500/15 border border-indigo-500/30 px-2.5 py-0.5 text-xs font-mono text-indigo-700 dark:text-indigo-300">
                    Sepolia Active
                  </span>
                </div>
                <h3 className="font-bold text-foreground text-base group-hover:text-indigo-600 dark:group-hover:text-indigo-300 transition-colors">
                  Blockchain Records &amp; Certificates
                </h3>
                <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                  Compare anchored SHA-256 verification digests on Sepolia and verify QR PDF certificates.
                </p>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-600 dark:text-indigo-300 pt-1">
                  <span>Open Ledger</span>
                  <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </TiltCard>
          </Link>
        </div>
      </div>

      {/* Preserved localStorage Session Verifications Table */}
      {history.length > 0 && (
        <div className="glass-panel rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-brand-cyan" />
              <h2 className="font-bold text-foreground text-base">Recent Session Verifications</h2>
            </div>
            <Link to="/evidence" className="nav-link-underline text-xs text-brand-blue dark:text-cyan-300 font-semibold">
              Inspect All in Evidence Explorer ({history.length})
            </Link>
          </div>

          <div className="divide-y divide-border/70">
            {history.slice(0, 5).map((item) => (
              <div
                key={item.id}
                className="py-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
              >
                <div className="space-y-1 max-w-2xl">
                  <div className="flex items-center gap-2">
                    <span className="glass-surface rounded px-1.5 py-0.5 text-[10px] font-mono text-slate-700 dark:text-slate-300 uppercase">
                      {item.type}
                    </span>
                    <span className="text-xs text-slate-600 dark:text-slate-400 font-mono">
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-foreground line-clamp-1">{item.preview}</p>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <VerdictBadge verdict={item.verdict} size="sm" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
