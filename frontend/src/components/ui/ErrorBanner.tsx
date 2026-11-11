import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';
import { RippleButton } from '@/components/ui/RippleButton';

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export const ErrorBanner: React.FC<ErrorBannerProps> = ({ message, onRetry }) => {
  return (
    <div className="glass-panel rounded-2xl border-rose-500/35 bg-rose-500/10 p-5 text-rose-900 dark:text-rose-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-glow-rose">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-rose-600 dark:text-rose-400 shrink-0 mt-0.5" />
        <div>
          <h4 className="text-sm font-semibold text-rose-800 dark:text-rose-200">Verification Request Failed</h4>
          <p className="text-xs text-rose-700/90 dark:text-rose-300/85 mt-1 leading-relaxed">{message}</p>
        </div>
      </div>
      {onRetry && (
        <RippleButton
          variant="glass"
          onClick={onRetry}
          className="rounded-lg border-rose-500/35 bg-rose-500/15 hover:bg-rose-500/25 px-3 py-1.5 text-xs text-rose-800 dark:text-rose-200 shrink-0"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Retry</span>
        </RippleButton>
      )}
    </div>
  );
};
