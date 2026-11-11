import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, Cpu } from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer className="glass-nav relative z-10 border-t py-6 px-4 sm:px-6 text-xs text-slate-600 dark:text-slate-400">
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 max-w-7xl mx-auto">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-brand-cyan shrink-0" />
          <span className="font-semibold text-foreground">FakeNewsBlockchain</span>
          <span>&mdash; Evidence-Grounded AI Verification &amp; Ethereum Auditability</span>
        </div>

        <div className="flex flex-wrap items-center justify-center gap-4 text-[11px]">
          <Link to="/verify" className="nav-link-underline hover:text-foreground transition-colors">
            Verify
          </Link>
          <Link to="/evidence" className="nav-link-underline hover:text-foreground transition-colors">
            Evidence Explorer
          </Link>
          <Link to="/blockchain" className="nav-link-underline hover:text-foreground transition-colors">
            Blockchain Records
          </Link>
          <Link to="/about" className="nav-link-underline hover:text-foreground transition-colors">
            About
          </Link>
          <span className="hidden sm:inline text-slate-400 dark:text-slate-600">|</span>
          <span className="flex items-center gap-1 text-slate-600 dark:text-slate-400">
            <Cpu className="h-3.5 w-3.5 text-indigo-500 dark:text-cyan-400" />
            <span>CPU Inference &middot; FEVER + Sepolia</span>
          </span>
        </div>
      </div>
    </footer>
  );
};
