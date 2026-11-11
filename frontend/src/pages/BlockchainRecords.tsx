import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'motion/react';
import { Blocks, QrCode, ShieldCheck, ExternalLink } from 'lucide-react';
import { AuditLedgerPanel } from '@/components/blockchain/AuditLedgerPanel';
import { CertificateVerifyPanel } from '@/components/blockchain/CertificateVerifyPanel';
import { cn } from '@/lib/utils';

type BlockchainTabKey = 'ledger' | 'certificate';

export const BlockchainRecords: React.FC = () => {
  const [activeTab, setActiveTab] = useState<BlockchainTabKey>('ledger');
  const [selectedCertId, setSelectedCertId] = useState('');
  const [selectedCertHash, setSelectedCertHash] = useState('');

  const handleInspectCertificate = (verificationId: string, recordHash: string) => {
    setSelectedCertId(verificationId);
    setSelectedCertHash(recordHash);
    setActiveTab('certificate');
  };

  return (
    <div className="space-y-6 p-4 sm:p-8 max-w-6xl mx-auto">
      {/* Unified Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-indigo-600 dark:text-cyan-300">
            <Blocks className="h-4 w-4" />
            <span>Ethereum Sepolia Integrity Ledger</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground mt-0.5">
            Blockchain Records &amp; Certificate Verification
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">
            Audit on-chain SHA-256 verification digests, download tamper-evident QR PDF certificates, or verify an existing certificate ID.
          </p>
        </div>

        <Link
          to="/verify-certificate"
          className="glass-surface inline-flex items-center gap-1.5 self-start sm:self-auto rounded-xl px-3 py-1.5 text-xs font-medium text-brand-blue dark:text-cyan-300 hover:border-cyan-400/45 transition-colors"
        >
          <QrCode className="h-3.5 w-3.5" />
          <span>Direct QR Verifier Route</span>
          <ExternalLink className="h-3 w-3" />
        </Link>
      </div>

      {/* Tab Switcher */}
      <div
        role="tablist"
        aria-label="Blockchain Views"
        className="glass-panel inline-grid grid-cols-2 gap-1.5 rounded-2xl p-1.5"
      >
        <button
          role="tab"
          type="button"
          aria-selected={activeTab === 'ledger'}
          onClick={() => setActiveTab('ledger')}
          className={cn(
            'relative flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
            activeTab === 'ledger'
              ? 'text-brand-blue dark:text-cyan-200'
              : 'text-slate-600 dark:text-slate-400 hover:text-foreground'
          )}
        >
          {activeTab === 'ledger' && (
            <motion.span
              layoutId="blockchain-tab-indicator"
              transition={{ type: 'spring', stiffness: 380, damping: 32 }}
              className="absolute inset-0 rounded-xl border border-cyan-500/40 bg-gradient-to-r from-[#087BFF]/15 to-[#00C8FF]/15"
            />
          )}
          <Blocks className="relative z-10 h-4 w-4 text-brand-cyan" />
          <span className="relative z-10">Anchored Ledger &amp; Live Audit</span>
        </button>

        <button
          role="tab"
          type="button"
          aria-selected={activeTab === 'certificate'}
          onClick={() => setActiveTab('certificate')}
          className={cn(
            'relative flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
            activeTab === 'certificate'
              ? 'text-brand-blue dark:text-cyan-200'
              : 'text-slate-600 dark:text-slate-400 hover:text-foreground'
          )}
        >
          {activeTab === 'certificate' && (
            <motion.span
              layoutId="blockchain-tab-indicator"
              transition={{ type: 'spring', stiffness: 380, damping: 32 }}
              className="absolute inset-0 rounded-xl border border-cyan-500/40 bg-gradient-to-r from-[#087BFF]/15 to-[#00C8FF]/15"
            />
          )}
          <ShieldCheck className="relative z-10 h-4 w-4 text-emerald-500 dark:text-emerald-400" />
          <span className="relative z-10">Certificate Verification</span>
        </button>
      </div>

      {/* Active View */}
      {activeTab === 'ledger' ? (
        <AuditLedgerPanel onSelectForCertificateVerify={handleInspectCertificate} />
      ) : (
        <div className="mx-auto max-w-3xl">
          <CertificateVerifyPanel
            initialId={selectedCertId}
            initialHash={selectedCertHash}
            syncSearchParams={false}
          />
        </div>
      )}
    </div>
  );
};
