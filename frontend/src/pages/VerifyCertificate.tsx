/**
 * frontend/src/pages/VerifyCertificate.tsx
 * Preserved direct public certificate verification route (especially for QR code links).
 */

import React from 'react';
import { QrCode } from 'lucide-react';
import { CertificateVerifyPanel } from '@/components/blockchain/CertificateVerifyPanel';

export const VerifyCertificate: React.FC = () => {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4 sm:p-8">
      <div className="text-center space-y-2 border-b border-border/70 pb-6">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-500/15 text-brand-blue dark:text-cyan-300 border border-cyan-500/35 shadow-glow-cyan">
          <QrCode className="h-6 w-6" />
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
          Public Certificate Verification
        </h1>
        <p className="text-xs sm:text-sm text-slate-600 dark:text-slate-400 max-w-lg mx-auto">
          Independently verify cryptographic authenticity and detect tampering by auditing records directly against the Ethereum Sepolia blockchain.
        </p>
      </div>

      <CertificateVerifyPanel syncSearchParams />
    </div>
  );
};
