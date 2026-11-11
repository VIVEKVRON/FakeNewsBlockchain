import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Layers } from 'lucide-react';
import { TextVerifyPanel } from '@/components/verify/TextVerifyPanel';

export const TextVerify: React.FC = () => {
  const location = useLocation();
  const initialClaim = (location.state as { prefillClaim?: string } | null)?.prefillClaim;

  return (
    <div className="space-y-4 p-4 sm:p-8 max-w-5xl mx-auto">
      <div className="flex justify-end">
        <Link
          to="/verify?tab=text"
          className="glass-surface inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium text-brand-blue dark:text-cyan-300 hover:border-cyan-400/45 transition-colors"
        >
          <Layers className="h-3.5 w-3.5" />
          <span>Open Unified /verify Workspace</span>
        </Link>
      </div>
      <TextVerifyPanel initialClaim={initialClaim} showHeader />
    </div>
  );
};
