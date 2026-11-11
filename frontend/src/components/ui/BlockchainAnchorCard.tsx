/**
 * frontend/src/components/ui/BlockchainAnchorCard.tsx
 * Professional user-triggered Ethereum cryptographic anchoring and on-chain
 * integrity verification card.
 */

import React, { useState } from 'react';
import {
  Blocks,
  Link,
  ShieldCheck,
  ShieldAlert,
  ExternalLink,
  Copy,
  Check,
  Loader2,
  AlertCircle,
  HelpCircle,
  Database
} from 'lucide-react';
import { RippleButton } from '@/components/ui/RippleButton';
import { anchorVerificationOnChain, verifyRecordHash } from '@/api/verify';
import type {
  CanonicalVerificationRecord,
  AnchorResponse,
  VerifyHashResponse
} from '@/types/verification';

interface BlockchainAnchorCardProps {
  verificationId: string;
  recordHash?: string;
  canonicalRecord?: CanonicalVerificationRecord;
  className?: string;
}

export const BlockchainAnchorCard: React.FC<BlockchainAnchorCardProps> = ({
  verificationId,
  recordHash = '',
  canonicalRecord,
  className = '',
}) => {
  const [anchoring, setAnchoring] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [anchorResult, setAnchorResult] = useState<AnchorResponse | null>(null);
  const [integrityResult, setIntegrityResult] = useState<VerifyHashResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Fallback hash if not passed directly but present in canonical record
  const effectiveHash = recordHash || canonicalRecord?.original_content_hash || '';

  const handleCopyHash = () => {
    if (effectiveHash) {
      navigator.clipboard.writeText(effectiveHash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleAnchor = async () => {
    if (!effectiveHash) {
      setErrorMsg('No record hash available to anchor.');
      return;
    }

    setAnchoring(true);
    setErrorMsg(null);

    try {
      const res = await anchorVerificationOnChain({
        verification_id: verificationId,
        record_hash: effectiveHash,
        canonical_record: canonicalRecord,
      });

      setAnchorResult(res);
      // Automatically re-query integrity after anchoring
      try {
        const verifyRes = await verifyRecordHash(verificationId, effectiveHash);
        setIntegrityResult(verifyRes);
      } catch {
        // Soft fallback
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to anchor verification to blockchain.');
    } finally {
      setAnchoring(false);
    }
  };

  const handleVerifyIntegrity = async () => {
    setVerifying(true);
    setErrorMsg(null);

    try {
      const res = await verifyRecordHash(verificationId, effectiveHash);
      setIntegrityResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Integrity check failed. RPC or contract may be unavailable.');
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div
      className={`glass-panel rounded-2xl p-5 border-cyan-500/25 ${className}`}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 pb-4">
        <div className="flex items-center space-x-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/15 text-brand-blue dark:text-cyan-300 border border-cyan-500/30">
            <Blocks className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h4 className="font-semibold text-foreground">Ethereum Cryptographic Anchoring</h4>
              <span className="glass-surface rounded-full px-2.5 py-0.5 text-xs font-medium text-indigo-700 dark:text-cyan-300">
                Sepolia / Hardhat
              </span>
            </div>
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Immutable SHA-256 fingerprint for non-repudiation and tamper detection
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          <RippleButton
            variant="glass"
            onClick={handleVerifyIntegrity}
            disabled={verifying || anchoring}
            className="rounded-xl px-3 py-1.5 text-xs"
          >
            {verifying ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-500 dark:text-cyan-400" />
            ) : (
              <ShieldCheck className="h-3.5 w-3.5 text-cyan-600 dark:text-cyan-400" />
            )}
            <span>{verifying ? 'Verifying...' : 'Verify On-Chain'}</span>
          </RippleButton>

          <RippleButton
            variant="primary"
            onClick={handleAnchor}
            disabled={anchoring || verifying || Boolean(anchorResult?.already_registered)}
            className="rounded-xl px-3.5 py-1.5 text-xs"
          >
            {anchoring ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Link className="h-3.5 w-3.5" />
            )}
            <span>
              {anchoring
                ? 'Submitting Tx...'
                : anchorResult?.already_registered
                ? 'Already Anchored'
                : 'Anchor to Blockchain'}
            </span>
          </RippleButton>
        </div>
      </div>

      {/* Record Hash & Verification ID */}
      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className="glass-surface rounded-xl p-3">
          <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Verification Identifier</div>
          <div className="mt-1 font-mono text-xs text-foreground break-all">{verificationId}</div>
        </div>

        <div className="glass-surface rounded-xl p-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-600 dark:text-slate-400">Deterministic SHA-256 Hash</span>
            <button
              type="button"
              onClick={handleCopyHash}
              className="flex items-center space-x-1 text-xs text-brand-blue dark:text-cyan-300 hover:underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
              title="Copy 64-character hex hash"
            >
              {copied ? <Check className="h-3.5 w-3.5 text-emerald-500 dark:text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
          <div className="mt-1 font-mono text-xs text-indigo-700 dark:text-cyan-300 break-all select-all">
            {effectiveHash ? `0x${effectiveHash}` : 'Computing hash...'}
          </div>
        </div>
      </div>

      {/* Live Error Alert */}
      {errorMsg && (
        <div className="mt-3 flex items-start space-x-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-800 dark:text-rose-200">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400 mt-0.5" />
          <div className="flex-1">
            <p className="font-semibold">Anchoring Notification</p>
            <p className="mt-0.5">{errorMsg}</p>
          </div>
        </div>
      )}

      {/* Anchoring Result Banner */}
      {anchorResult && (
        <div
          className={`mt-4 rounded-xl border p-4 text-xs ${
            anchorResult.already_registered
              ? 'border-amber-500/30 bg-amber-500/10 text-amber-900 dark:text-amber-200'
              : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200'
          }`}
        >
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center space-x-2 font-semibold">
              <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
              <span>
                {anchorResult.already_registered
                  ? 'Record Already Anchored On-Chain'
                  : 'Successfully Anchored to Ethereum'}
              </span>
            </div>
            <span className="glass-surface rounded px-2 py-0.5 text-[11px] font-mono text-foreground">
              {anchorResult.network.toUpperCase()} (Chain ID: {anchorResult.chain_id})
            </span>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 text-foreground/90">
            {anchorResult.transaction_hash && (
              <div>
                <span className="text-slate-600 dark:text-slate-400">Tx Hash:</span>{' '}
                <span className="font-mono break-all">{anchorResult.transaction_hash}</span>
              </div>
            )}
            {anchorResult.block_number && (
              <div>
                <span className="text-slate-600 dark:text-slate-400">Block Number:</span>{' '}
                <span className="font-mono">#{anchorResult.block_number}</span>
              </div>
            )}
            {anchorResult.block_datetime && (
              <div>
                <span className="text-slate-600 dark:text-slate-400">Block Timestamp:</span>{' '}
                <span className="font-mono">{anchorResult.block_datetime}</span>
              </div>
            )}
            {anchorResult.gas_used && (
              <div>
                <span className="text-slate-600 dark:text-slate-400">Gas Used:</span>{' '}
                <span className="font-mono">{anchorResult.gas_used.toLocaleString()}</span>
              </div>
            )}
          </div>

          {anchorResult.etherscan_url && (
            <div className="mt-3 pt-2 border-t border-border/60">
              <a
                href={anchorResult.etherscan_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center space-x-1.5 text-brand-blue dark:text-cyan-300 hover:underline font-medium"
              >
                <span>View on Explorer</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          )}
        </div>
      )}

      {/* On-Chain Integrity Verification Status */}
      {integrityResult && (
        <div
          className={`mt-3 rounded-xl border p-3.5 text-xs ${
            integrityResult.integrity_status === 'VERIFIED_TAMPER_FREE'
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-900 dark:text-emerald-200'
              : integrityResult.integrity_status === 'HASH_MISMATCH_TAMPERED'
              ? 'border-rose-500/30 bg-rose-500/10 text-rose-900 dark:text-rose-200'
              : 'glass-surface text-slate-700 dark:text-slate-300'
          }`}
        >
          <div className="flex items-center space-x-2 font-semibold">
            {integrityResult.integrity_status === 'VERIFIED_TAMPER_FREE' ? (
              <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            ) : integrityResult.integrity_status === 'HASH_MISMATCH_TAMPERED' ? (
              <ShieldAlert className="h-4 w-4 text-rose-600 dark:text-rose-400" />
            ) : (
              <Database className="h-4 w-4 text-slate-500 dark:text-slate-400" />
            )}
            <span>
              {integrityResult.integrity_status === 'VERIFIED_TAMPER_FREE'
                ? 'Integrity Verified: Tamper-Free Record'
                : integrityResult.integrity_status === 'HASH_MISMATCH_TAMPERED'
                ? 'CRITICAL INTEGRITY ALERT: Tampering Detected'
                : 'On-Chain Status'}
            </span>
          </div>

          <p className="mt-1 opacity-90">{integrityResult.explanation}</p>

          {integrityResult.on_chain_record && (
            <div className="glass-surface mt-2.5 rounded-lg p-2 font-mono text-[11px] text-foreground/90 space-y-1">
              <div>On-Chain Submitter: {integrityResult.on_chain_record.submitter}</div>
              <div>Block Datetime: {integrityResult.on_chain_record.block_datetime}</div>
              <div>Anchored Hash: 0x{integrityResult.on_chain_record.record_hash}</div>
            </div>
          )}
        </div>
      )}

      {/* Epistemological Principle Footer */}
      <div className="glass-surface mt-4 flex items-start space-x-2 rounded-xl p-2.5 text-[11px] text-slate-600 dark:text-slate-400">
        <HelpCircle className="h-3.5 w-3.5 shrink-0 text-indigo-500 dark:text-cyan-400 mt-0.5" />
        <p>
          <strong className="text-foreground">Epistemological Principle:</strong> Blockchain anchoring provides
          mathematical non-repudiation and anti-tampering proof for this verification record. It proves that this
          exact AI result existed at this block timestamp—not that the news claim or AI verdict is infallible truth.
        </p>
      </div>
    </div>
  );
};
