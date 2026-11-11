import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  ShieldCheck,
  ShieldAlert,
  ExternalLink,
  FileDown,
  Search,
  RefreshCw,
  Copy,
  Check,
  CheckCircle2,
  HelpCircle,
  Database,
} from 'lucide-react';
import {
  getAuditExplorerRecords,
  compareAuditRecord,
  getCertificateDownloadUrl,
  type AuditExplorerResponse,
  type HistoryRecord,
  type AuditCompareResponse,
} from '@/api/verify';
import { VerdictBadge } from '@/components/ui/VerdictBadge';
import { RippleButton } from '@/components/ui/RippleButton';

interface AuditLedgerPanelProps {
  onSelectForCertificateVerify?: (verificationId: string, recordHash: string) => void;
  refreshTrigger?: number;
}

export const AuditLedgerPanel: React.FC<AuditLedgerPanelProps> = ({
  onSelectForCertificateVerify,
  refreshTrigger = 0,
}) => {
  const [data, setData] = useState<AuditExplorerResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [comparingId, setComparingId] = useState<string | null>(null);
  const [compareResults, setCompareResults] = useState<Record<string, AuditCompareResponse>>({});
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const fetchAuditData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getAuditExplorerRecords();
      setData(res);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch blockchain audit records.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditData();
  }, [refreshTrigger]);

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(id);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const handleLiveCompare = async (verificationId: string) => {
    setComparingId(verificationId);
    try {
      const comp = await compareAuditRecord(verificationId);
      setCompareResults((prev) => ({ ...prev, [verificationId]: comp }));
    } catch (err: any) {
      setCompareResults((prev) => ({
        ...prev,
        [verificationId]: {
          verification_id: verificationId,
          status: 'ERROR',
          matched: null,
          explanation: err.message || 'Failed to compare with Sepolia smart contract.',
        },
      }));
    } finally {
      setComparingId(null);
    }
  };

  const filteredRecords = (data?.records || []).filter((r: HistoryRecord) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      r.verification_id.toLowerCase().includes(q) ||
      (r.content_preview && r.content_preview.toLowerCase().includes(q)) ||
      (r.transaction_hash && r.transaction_hash.toLowerCase().includes(q)) ||
      (r.record_hash && r.record_hash.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-6">
      {/* Contract & Network Status Card */}
      <div className="glass-panel rounded-2xl border-cyan-500/25 p-5">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 flex-1">
            <div>
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Connected Network</div>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 dark:bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.65)]" />
                <span className="font-semibold text-sm text-foreground">
                  Ethereum {data?.network ? data.network.toUpperCase() : 'SEPOLIA'}
                </span>
                <span className="glass-surface rounded px-1.5 py-0.5 text-[11px] font-mono text-slate-700 dark:text-slate-300">
                  Chain {data?.chain_id || '—'}
                </span>
              </div>
            </div>

            <div>
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Smart Contract Address</div>
              <div className="mt-1 flex items-center space-x-1.5 font-mono text-xs text-indigo-700 dark:text-cyan-300 break-all">
                <span>{data?.contract_address || (loading ? 'Loading...' : 'Unavailable')}</span>
                {data?.contract_address && (
                  <a
                    href={`https://sepolia.etherscan.io/address/${data.contract_address}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-brand-blue dark:text-cyan-300 hover:underline shrink-0"
                    title="View Contract on Sepolia Etherscan"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            </div>

            <div>
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Contract Status</div>
              <div className="mt-1 flex items-center space-x-2">
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border ${
                    data?.contract_deployed
                      ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                      : 'glass-surface text-slate-600 dark:text-slate-400'
                  }`}
                >
                  {data ? (data.contract_deployed ? 'Active & Deployed' : 'Not Deployed / Offline') : loading ? 'Checking...' : 'Unavailable'}
                </span>
              </div>
            </div>

            <div>
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Total Anchored Records</div>
              <div className="mt-1 text-lg font-bold font-mono text-brand-blue dark:text-cyan-300">
                {data ? data.total_records : '—'}
              </div>
            </div>
          </div>

          <RippleButton
            variant="glass"
            onClick={fetchAuditData}
            disabled={loading}
            className="self-start rounded-xl px-3 py-1.5 text-xs shrink-0"
          >
            <RefreshCw className={`h-3.5 w-3.5 text-brand-cyan ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh Ledger</span>
          </RippleButton>
        </div>

        <div className="glass-surface mt-4 flex items-start space-x-2 rounded-xl p-2.5 text-[11px] text-slate-600 dark:text-slate-400">
          <HelpCircle className="h-3.5 w-3.5 shrink-0 text-indigo-500 dark:text-cyan-400 mt-0.5" />
          <p>
            <strong className="text-foreground">Epistemological Principle:</strong> All records below are cryptographically anchored to the Ethereum Sepolia smart contract. This proves mathematically that the exact AI verification result existed at that specific block timestamp and has not been modified. It does not certify that the underlying news is ground truth.
          </p>
        </div>
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by Verification ID, Claim Text, Record Hash, or Transaction Hash..."
          className="glass-panel w-full rounded-xl pl-10 pr-4 py-2.5 text-xs sm:text-sm text-foreground placeholder:text-slate-500 focus:outline-none focus:border-cyan-400 transition-colors"
        />
      </div>

      {error && (
        <div className="glass-panel rounded-xl border-rose-500/35 bg-rose-500/10 p-4 text-xs text-rose-800 dark:text-rose-200">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex flex-col items-center justify-center p-12 text-slate-600 dark:text-slate-400 space-y-3">
          <RefreshCw className="h-6 w-6 animate-spin text-brand-cyan" />
          <p className="text-sm">Querying Ethereum Sepolia ledger &amp; database records...</p>
        </div>
      ) : filteredRecords.length === 0 ? (
        <div className="glass-panel rounded-2xl p-12 text-center text-slate-600 dark:text-slate-400 space-y-2">
          <Database className="mx-auto h-8 w-8 text-slate-500" />
          <p className="text-sm font-medium text-foreground">No matching blockchain records found.</p>
          <p className="text-xs">Run a verification and click "Anchor to Blockchain" to anchor records to Ethereum Sepolia.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {filteredRecords.map((rec) => {
            const comp = compareResults[rec.verification_id];
            return (
              <div
                key={rec.verification_id}
                className="glass-panel rounded-xl p-5 space-y-4 hover:border-cyan-400/40 transition-colors"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <VerdictBadge verdict={rec.verdict} size="sm" />
                    <span className="font-mono text-xs font-semibold text-foreground">
                      {rec.verification_id}
                    </span>
                    <span className="glass-surface rounded px-2 py-0.5 text-[11px] uppercase tracking-wide text-slate-600 dark:text-slate-300 font-mono">
                      {rec.content_type}
                    </span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <RippleButton
                      variant="glass"
                      onClick={() => handleLiveCompare(rec.verification_id)}
                      disabled={comparingId === rec.verification_id}
                      className="rounded-lg px-2.5 py-1 text-xs"
                      title="Directly query Ethereum Sepolia smart contract to verify hash match"
                    >
                      <RefreshCw className={`h-3 w-3 text-brand-cyan ${comparingId === rec.verification_id ? 'animate-spin' : ''}`} />
                      <span>{comparingId === rec.verification_id ? 'Auditing...' : 'Live On-Chain Compare'}</span>
                    </RippleButton>

                    <a
                      href={getCertificateDownloadUrl(rec.verification_id)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center space-x-1 rounded-lg border border-indigo-500/35 bg-indigo-500/15 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300 hover:bg-indigo-500/25 transition-colors"
                      title="Download official vector PDF verification certificate with QR code"
                    >
                      <FileDown className="h-3 w-3" />
                      <span>PDF Certificate</span>
                    </a>

                    {onSelectForCertificateVerify ? (
                      <button
                        type="button"
                        onClick={() => onSelectForCertificateVerify(rec.verification_id, rec.record_hash)}
                        className="glass-surface flex items-center space-x-1 rounded-lg px-2.5 py-1 text-xs font-medium text-foreground/90 hover:border-cyan-400/45 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                        title="Audit this record in Certificate Verification"
                      >
                        <ShieldCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                        <span>Verify Online</span>
                      </button>
                    ) : (
                      <Link
                        to={`/verify-certificate?id=${encodeURIComponent(rec.verification_id)}&hash=${encodeURIComponent(rec.record_hash)}`}
                        className="glass-surface flex items-center space-x-1 rounded-lg px-2.5 py-1 text-xs font-medium text-foreground/90 hover:border-cyan-400/45 transition-colors"
                        title="Open public certificate verification audit view"
                      >
                        <ShieldCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                        <span>Verify Online</span>
                      </Link>
                    )}
                  </div>
                </div>

                <div className="text-xs sm:text-sm text-foreground/95 leading-relaxed font-sans">
                  {rec.content_preview}
                </div>

                <div className="glass-surface grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4 rounded-xl p-3 text-xs">
                  <div>
                    <span className="text-slate-600 dark:text-slate-400 block text-[11px]">Tx Hash</span>
                    <div className="mt-0.5 flex items-center space-x-1 font-mono text-brand-blue dark:text-cyan-300 break-all">
                      <span>{rec.transaction_hash ? `${rec.transaction_hash.slice(0, 14)}...` : 'N/A'}</span>
                      {rec.etherscan_url && (
                        <a
                          href={rec.etherscan_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-brand-blue dark:text-cyan-300 hover:underline shrink-0"
                          title="View Transaction on Etherscan"
                        >
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  </div>

                  <div>
                    <span className="text-slate-600 dark:text-slate-400 block text-[11px]">Block Height / Date</span>
                    <span className="mt-0.5 font-mono text-foreground block">
                      #{rec.block_number ?? 'Pending'} &nbsp;
                      <span className="text-slate-600 dark:text-slate-400 text-[10px]">({rec.block_datetime || rec.created_at})</span>
                    </span>
                  </div>

                  <div>
                    <span className="text-slate-600 dark:text-slate-400 block text-[11px]">Gas Used</span>
                    <span className="mt-0.5 font-mono text-foreground block">
                      {rec.gas_used ? rec.gas_used.toLocaleString() : 'N/A'}
                    </span>
                  </div>

                  <div>
                    <div className="flex items-center justify-between text-slate-600 dark:text-slate-400 text-[11px]">
                      <span>Deterministic SHA-256 Hash</span>
                      <button
                        type="button"
                        onClick={() => handleCopy(rec.record_hash, rec.verification_id)}
                        className="text-indigo-600 dark:text-cyan-300 hover:opacity-80 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                        title="Copy Hash"
                        aria-label="Copy SHA-256 hash"
                      >
                        {copiedHash === rec.verification_id ? (
                          <Check className="h-3 w-3 text-emerald-500 dark:text-emerald-400" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </button>
                    </div>
                    <span className="mt-0.5 font-mono text-indigo-700 dark:text-cyan-300 text-[11px] break-all block">
                      0x{rec.record_hash.slice(0, 16)}...
                    </span>
                  </div>
                </div>

                {comp && (
                  <div
                    className={`rounded-xl border p-3 text-xs ${
                      comp.status === 'VERIFIED_MATCH'
                        ? 'border-emerald-500/35 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200'
                        : comp.status === 'TAMPERED_MISMATCH'
                        ? 'border-rose-500/35 bg-rose-500/10 text-rose-900 dark:text-rose-200'
                        : 'glass-surface text-slate-700 dark:text-slate-300'
                    }`}
                  >
                    <div className="flex items-center space-x-2 font-semibold">
                      {comp.status === 'VERIFIED_MATCH' ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                      ) : (
                        <ShieldAlert className="h-4 w-4 text-rose-600 dark:text-rose-400" />
                      )}
                      <span>
                        {comp.status === 'VERIFIED_MATCH'
                          ? 'Live On-Chain Audit Passed: Verified Tamper-Free'
                          : 'Live Audit Alert: Hash Mismatch / Unverified'}
                      </span>
                    </div>
                    <p className="mt-1 opacity-90">{comp.explanation}</p>
                    {comp.on_chain_hash && (
                      <div className="mt-2 font-mono text-[11px] opacity-90 space-y-0.5 break-all">
                        <div>On-Chain Hash: 0x{comp.on_chain_hash}</div>
                        {comp.submitter && <div>On-Chain Submitter: {comp.submitter}</div>}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
