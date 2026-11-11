import React, { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ShieldCheck,
  ShieldAlert,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  HelpCircle,
} from 'lucide-react';
import {
  verifyCertificatePublic,
  type PublicVerifyCertificateResponse,
} from '@/api/verify';
import { RippleButton } from '@/components/ui/RippleButton';

interface CertificateVerifyPanelProps {
  initialId?: string;
  initialHash?: string;
  syncSearchParams?: boolean;
}

export const CertificateVerifyPanel: React.FC<CertificateVerifyPanelProps> = ({
  initialId = '',
  initialHash = '',
  syncSearchParams = true,
}) => {
  const [searchParams] = useSearchParams();
  const [verificationId, setVerificationId] = useState(
    syncSearchParams ? searchParams.get('id') || initialId : initialId
  );
  const [recordHash, setRecordHash] = useState(
    syncSearchParams ? searchParams.get('hash') || initialHash : initialHash
  );
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PublicVerifyCertificateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const runAudit = useCallback(
    async (idToAudit?: string, hashToAudit?: string) => {
      const targetId = (idToAudit ?? verificationId).trim();
      const targetHash = (hashToAudit ?? recordHash).trim();

      if (!targetId) {
        setError('Please provide a Verification ID.');
        return;
      }

      setLoading(true);
      setError(null);
      setResult(null);

      try {
        const res = await verifyCertificatePublic(targetId, targetHash || undefined);
        setResult(res);
      } catch (err: any) {
        setError(err.message || 'Verification audit request failed.');
      } finally {
        setLoading(false);
      }
    },
    [verificationId, recordHash]
  );

  // Sync URL query params for direct QR links (/verify-certificate?id=...&hash=...)
  useEffect(() => {
    if (!syncSearchParams) return;
    const idParam = searchParams.get('id');
    const hashParam = searchParams.get('hash');
    if (idParam) {
      setVerificationId(idParam);
      if (hashParam) setRecordHash(hashParam);
      runAudit(idParam, hashParam || undefined);
    }
  }, [syncSearchParams, searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  // Sync programmatic prefill inside unified /blockchain view
  useEffect(() => {
    if (initialId) {
      setVerificationId(initialId);
      setRecordHash(initialHash || '');
      runAudit(initialId, initialHash || undefined);
    }
  }, [initialId, initialHash]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    runAudit();
  };

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit} className="glass-panel rounded-2xl p-6 space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="verif-id-input" className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
            Certificate Verification ID <span className="text-rose-500 dark:text-rose-400">*</span>
          </label>
          <input
            id="verif-id-input"
            type="text"
            required
            value={verificationId}
            onChange={(e) => setVerificationId(e.target.value)}
            placeholder="e.g. verif-2026-0001"
            className="glass-surface w-full rounded-xl px-4 py-2.5 text-sm font-mono text-foreground placeholder:text-slate-500 focus:outline-none focus:border-cyan-400 transition-colors"
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="verif-hash-input" className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
            SHA-256 Record Hash (Optional Tamper Check)
          </label>
          <input
            id="verif-hash-input"
            type="text"
            value={recordHash}
            onChange={(e) => setRecordHash(e.target.value)}
            placeholder="0x... or 64-character hex digest from certificate"
            className="glass-surface w-full rounded-xl px-4 py-2.5 text-xs sm:text-sm font-mono text-foreground placeholder:text-slate-500 focus:outline-none focus:border-cyan-400 transition-colors"
          />
        </div>

        <div className="pt-2">
          <RippleButton
            type="submit"
            variant="primary"
            disabled={loading || !verificationId.trim()}
            className="w-full rounded-xl py-2.5 px-4 text-sm font-semibold"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Querying Ethereum Sepolia Smart Contract...</span>
              </>
            ) : (
              <>
                <ShieldCheck className="h-4 w-4" />
                <span>Audit Certificate Authenticity</span>
              </>
            )}
          </RippleButton>
        </div>
      </form>

      {error && (
        <div className="glass-panel rounded-xl border-rose-500/35 bg-rose-500/10 p-4 text-xs text-rose-800 dark:text-rose-200 flex items-center space-x-2">
          <AlertTriangle className="h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div
          className={`glass-panel rounded-2xl p-6 space-y-5 border ${
            result.status === 'MATCH'
              ? 'border-emerald-500/35 bg-emerald-500/10 dark:bg-emerald-950/20'
              : result.status === 'MISMATCH'
              ? 'border-rose-500/35 bg-rose-500/10 dark:bg-rose-950/20'
              : 'border-amber-500/35 bg-amber-500/10 dark:bg-amber-950/20'
          }`}
        >
          <div className="flex items-start space-x-3 border-b border-border/60 pb-4">
            {result.status === 'MATCH' ? (
              <CheckCircle2 className="h-7 w-7 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
            ) : result.status === 'MISMATCH' ? (
              <ShieldAlert className="h-7 w-7 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="h-7 w-7 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            )}

            <div className="flex-1">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-lg font-bold text-foreground">
                  {result.status === 'MATCH'
                    ? 'Verified Authentic Certificate'
                    : result.status === 'MISMATCH'
                    ? 'Tamper Alert: Hash Mismatch Detected'
                    : 'Verification Record Status: ' + result.status}
                </h2>
                <span
                  className={`rounded-full px-3 py-0.5 text-xs font-mono font-bold border ${
                    result.status === 'MATCH'
                      ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                      : result.status === 'MISMATCH'
                      ? 'bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/30'
                      : 'bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-500/30'
                  }`}
                >
                  {result.status}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-slate-700 dark:text-slate-300">{result.message}</p>
            </div>
          </div>

          <div className="glass-surface grid grid-cols-1 gap-3 sm:grid-cols-2 rounded-xl p-4 text-xs font-mono">
            <div>
              <span className="text-slate-600 dark:text-slate-400 block text-[11px] font-sans">Verification Identifier</span>
              <span className="mt-0.5 text-foreground block break-all font-semibold">{result.verification_id}</span>
            </div>

            <div>
              <span className="text-slate-600 dark:text-slate-400 block text-[11px] font-sans">Blockchain Network</span>
              <span className="mt-0.5 text-foreground block">
                {result.network.toUpperCase()} (Chain ID: {result.chain_id || 11155111})
              </span>
            </div>

            {result.on_chain_hash && (
              <div className="sm:col-span-2">
                <span className="text-slate-600 dark:text-slate-400 block text-[11px] font-sans">On-Chain Anchored Hash</span>
                <span className="mt-0.5 text-brand-blue dark:text-cyan-300 block break-all select-all">
                  0x{result.on_chain_hash}
                </span>
              </div>
            )}

            {result.canonical_hash && (
              <div className="sm:col-span-2">
                <span className="text-slate-600 dark:text-slate-400 block text-[11px] font-sans">Certificate Provided Hash</span>
                <span
                  className={`mt-0.5 block break-all select-all ${
                    result.status === 'MATCH'
                      ? 'text-emerald-700 dark:text-emerald-300'
                      : 'text-rose-700 dark:text-rose-400 font-bold'
                  }`}
                >
                  0x{result.canonical_hash}
                </span>
              </div>
            )}

            {result.block_number && (
              <div>
                <span className="text-slate-600 dark:text-slate-400 block text-[11px] font-sans">Anchor Block Height</span>
                <span className="mt-0.5 text-foreground block">#{result.block_number}</span>
              </div>
            )}

            {result.block_datetime && (
              <div>
                <span className="text-slate-600 dark:text-slate-400 block text-[11px] font-sans">Anchor Timestamp (UTC)</span>
                <span className="mt-0.5 text-foreground block">{result.block_datetime}</span>
              </div>
            )}

            {result.submitter && (
              <div className="sm:col-span-2">
                <span className="text-slate-600 dark:text-slate-400 block text-[11px] font-sans">On-Chain Submitter</span>
                <span className="mt-0.5 text-foreground/90 block break-all">{result.submitter}</span>
              </div>
            )}

            {result.contract_address && (
              <div className="sm:col-span-2">
                <span className="text-slate-600 dark:text-slate-400 block text-[11px] font-sans">Smart Contract</span>
                <span className="mt-0.5 text-indigo-700 dark:text-indigo-300 block break-all">
                  {result.contract_address}
                </span>
              </div>
            )}
          </div>

          {result.etherscan_url && (
            <div className="pt-2">
              <a
                href={result.etherscan_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center space-x-1.5 text-xs text-brand-blue dark:text-cyan-300 hover:underline font-semibold"
              >
                <span>View Transaction on Sepolia Etherscan</span>
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </div>
          )}

          <div className="glass-surface flex items-start space-x-2 rounded-xl p-3 text-xs text-slate-600 dark:text-slate-400">
            <HelpCircle className="h-4 w-4 shrink-0 text-indigo-500 dark:text-cyan-400 mt-0.5" />
            <p>
              <strong className="text-foreground">Epistemological Principle:</strong> {result.epistemological_disclaimer}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
