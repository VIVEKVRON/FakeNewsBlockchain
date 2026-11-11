/**
 * frontend/src/pages/AuditExplorer.tsx
 * Preserved direct route for Ethereum Sepolia Blockchain Audit Explorer.
 */

import React from 'react';
import { Link } from 'react-router-dom';
import { Blocks, ShieldCheck } from 'lucide-react';
import { AuditLedgerPanel } from '@/components/blockchain/AuditLedgerPanel';

export const AuditExplorer: React.FC = () => {
  return (
    <div className="space-y-6 p-4 sm:p-8 max-w-6xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-500/15 text-brand-blue dark:text-cyan-300 border border-cyan-500/30">
              <Blocks className="h-5 w-5" />
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">
              Blockchain Audit Explorer
            </h1>
          </div>
          <p className="mt-1 text-xs sm:text-sm text-slate-600 dark:text-slate-400">
            Immutable Ethereum cryptographic ledger &amp; verifiable proof audit trail
          </p>
        </div>

        <Link
          to="/blockchain"
          className="glass-surface self-start sm:self-auto flex items-center space-x-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-brand-blue dark:text-cyan-300 hover:border-cyan-400/45 transition-colors"
        >
          <ShieldCheck className="h-3.5 w-3.5" />
          <span>Open Blockchain Records</span>
        </Link>
      </div>

      <AuditLedgerPanel />
    </div>
  );
};
