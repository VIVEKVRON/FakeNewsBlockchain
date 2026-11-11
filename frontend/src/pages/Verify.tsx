import React, { useState, useEffect } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  ShieldCheck,
  FileCheck2,
  FileText,
  Link2,
  Image as ImageIcon,
} from 'lucide-react';
import { TextVerifyPanel } from '@/components/verify/TextVerifyPanel';
import { ArticleVerifyPanel } from '@/components/verify/ArticleVerifyPanel';
import { ArticleUrlVerifyPanel } from '@/components/verify/ArticleUrlVerifyPanel';
import { ImageAnalysisPanel } from '@/components/verify/ImageAnalysisPanel';
import { cn } from '@/lib/utils';

type VerifyTabKey = 'text' | 'article' | 'url' | 'image';

const VERIFY_TABS: {
  key: VerifyTabKey;
  label: string;
  subtitle: string;
  icon: React.ElementType;
}[] = [
  { key: 'text', label: 'Text Claim', subtitle: 'FEVER + Wikipedia + NLI', icon: FileCheck2 },
  { key: 'article', label: 'Full Article', subtitle: 'Multi-claim + ISOT', icon: FileText },
  { key: 'url', label: 'Article URL', subtitle: 'source_url + Cached News', icon: Link2 },
  { key: 'image', label: 'Image OCR/ELA', subtitle: 'PaddleOCR + ELA Map', icon: ImageIcon },
];

const parseTabParam = (raw: string | null): VerifyTabKey => {
  if (raw === 'article' || raw === 'url' || raw === 'image') return raw;
  return 'text';
};

export const Verify: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<VerifyTabKey>(() =>
    parseTabParam(searchParams.get('tab'))
  );
  const [prefillClaim, setPrefillClaim] = useState<string>(
    (location.state as { prefillClaim?: string } | null)?.prefillClaim || ''
  );

  // Sync tab if query param updates via navigation
  useEffect(() => {
    const paramTab = searchParams.get('tab');
    if (paramTab) {
      setActiveTab(parseTabParam(paramTab));
    }
  }, [searchParams]);

  // Sync prefillClaim from router state (e.g., Home / Dashboard / Image routes)
  useEffect(() => {
    const incoming = (location.state as { prefillClaim?: string } | null)?.prefillClaim;
    if (incoming) {
      setPrefillClaim(incoming);
      setActiveTab('text');
    }
  }, [location.state]);

  const handleSelectTab = (tab: VerifyTabKey) => {
    setActiveTab(tab);
    setSearchParams({ tab }, { replace: true });
  };

  const handleTabKeyDown = (e: React.KeyboardEvent, idx: number) => {
    let nextIdx = idx;
    if (e.key === 'ArrowRight') nextIdx = (idx + 1) % VERIFY_TABS.length;
    else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + VERIFY_TABS.length) % VERIFY_TABS.length;
    else if (e.key === 'Home') nextIdx = 0;
    else if (e.key === 'End') nextIdx = VERIFY_TABS.length - 1;
    else return;

    e.preventDefault();
    const target = VERIFY_TABS[nextIdx];
    handleSelectTab(target.key);
    const el = document.getElementById(`verify-tab-${target.key}`);
    el?.focus();
  };

  const handleSendImageTextToVerify = (ocrText: string) => {
    setPrefillClaim(ocrText);
    handleSelectTab('text');
  };

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 sm:p-8">
      {/* Workspace Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-blue dark:text-cyan-300">
          <ShieldCheck className="h-4 w-4" />
          <span>Unified Verification Workspace</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
          Verify Claims, Articles, Source URLs &amp; Imagery
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Choose any verification pipeline below. All results preserve raw ML provenance, evidence audit trails, and optional Ethereum Sepolia anchoring.
        </p>
      </div>

      {/* Accessible Tab Switcher */}
      <div
        role="tablist"
        aria-label="Verification Modes"
        className="glass-panel grid grid-cols-2 md:grid-cols-4 gap-1.5 rounded-2xl p-1.5"
      >
        {VERIFY_TABS.map((tab, idx) => {
          const Icon = tab.icon;
          const isSelected = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              id={`verify-tab-${tab.key}`}
              role="tab"
              type="button"
              aria-selected={isSelected}
              aria-controls={`verify-tabpanel-${tab.key}`}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => handleSelectTab(tab.key)}
              onKeyDown={(e) => handleTabKeyDown(e, idx)}
              className={cn(
                'relative flex items-center gap-2.5 rounded-xl px-3.5 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
                isSelected
                  ? 'text-brand-blue dark:text-cyan-200'
                  : 'text-slate-600 dark:text-slate-400 hover:bg-cyan-500/10 hover:text-foreground'
              )}
            >
              {isSelected && (
                <motion.span
                  layoutId="verify-tab-indicator"
                  transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                  className="absolute inset-0 rounded-xl border border-cyan-500/40 bg-gradient-to-r from-[#087BFF]/15 to-[#00C8FF]/15 shadow-sm"
                />
              )}
              <Icon className={cn('relative z-10 h-4 w-4 shrink-0', isSelected ? 'text-brand-cyan' : '')} />
              <div className="relative z-10 min-w-0">
                <div className="text-xs font-bold truncate">{tab.label}</div>
                <div className="text-[10px] opacity-80 truncate">{tab.subtitle}</div>
              </div>
            </button>
          );
        })}
      </div>

      {/* Active Panel */}
      <div
        id={`verify-tabpanel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`verify-tab-${activeTab}`}
      >
        {activeTab === 'text' && (
          <TextVerifyPanel initialClaim={prefillClaim} showHeader={false} />
        )}
        {activeTab === 'article' && <ArticleVerifyPanel showHeader={false} />}
        {activeTab === 'url' && <ArticleUrlVerifyPanel />}
        {activeTab === 'image' && (
          <ImageAnalysisPanel
            showHeader={false}
            onVerifyExtractedText={handleSendImageTextToVerify}
          />
        )}
      </div>
    </div>
  );
};
