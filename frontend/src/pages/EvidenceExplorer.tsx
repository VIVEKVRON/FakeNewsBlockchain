import React from 'react';
import { Link } from 'react-router-dom';
import { SearchCheck, Blocks, ShieldCheck } from 'lucide-react';
import { EvidenceExplorerView } from '@/components/evidence/EvidenceExplorerView';

export const EvidenceExplorer: React.FC = () => {
  return (
    <div className="space-y-6 p-4 sm:p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
        <div>
          <div className="flex items-center space-x-2 text-xs font-semibold uppercase tracking-wider text-brand-blue dark:text-cyan-300">
            <SearchCheck className="h-4 w-4" />
            <span>Evidence &amp; Provenance Explorer</span>
          </div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground mt-0.5">
            Evidence Explorer &amp; Verification Archive
          </h1>
          <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400">
            Search verified claims and articles, inspect retrieved FEVER &amp; Wikipedia evidence sentences, audit NLI trails, and download certificates.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <Link
            to="/blockchain"
            className="flex items-center space-x-1.5 rounded-xl border border-indigo-500/35 bg-indigo-500/15 hover:bg-indigo-500/25 px-3 py-1.5 text-xs font-medium text-indigo-700 dark:text-indigo-300 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            <Blocks className="h-3.5 w-3.5" />
            <span>Blockchain Records</span>
          </Link>

          <Link
            to="/verify"
            className="glass-surface flex items-center space-x-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-foreground hover:border-cyan-400/45 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
          >
            <ShieldCheck className="h-3.5 w-3.5 text-brand-cyan" />
            <span>New Verification</span>
          </Link>
        </div>
      </div>

      <EvidenceExplorerView enableSessionTab />
    </div>
  );
};
