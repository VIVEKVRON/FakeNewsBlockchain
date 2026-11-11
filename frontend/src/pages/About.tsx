import React from 'react';
import {
  ShieldCheck,
  Layers,
  AlertTriangle,
  BookOpen
} from 'lucide-react';

export const About: React.FC = () => {
  return (
    <div className="space-y-8 p-4 sm:p-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-blue dark:text-cyan-300">
          <BookOpen className="h-4 w-4" />
          <span>Technical Reference</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
          Architecture & Methodology Specifications
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Scientific principles, dataset provenance, model configurations, and boundary conditions for FakeNewsBlockchain.
        </p>
      </div>

      {/* Critical Epistemological Delimitation */}
      <div className="glass-panel rounded-2xl border-amber-500/30 bg-amber-500/10 dark:bg-amber-950/20 p-6 space-y-3">
        <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300 font-bold text-sm">
          <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 shrink-0" />
          <span>Core Epistemological Principle: ML Classification vs. Factual Verification</span>
        </div>
        <p className="text-xs text-amber-900 dark:text-amber-200/90 leading-relaxed">
          A machine learning model prediction alone <strong>never proves whether news is true or false</strong>.
          Linguistic models evaluate stylistic and lexical patterns within their training distributions.
          In contrast, <strong>evidence-based fact verification</strong> grounds factual assertions against independently retrieved, verified documentary evidence.
          Absence of evidence in the knowledge base is never treated as evidence of falsehood.
        </p>
      </div>

      {/* Verification Pipeline Architecture */}
      <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6">
        <h3 className="text-lg font-bold text-foreground">
          Dual-Tier Verification Pipeline
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Primary Tier */}
          <div className="glass-surface rounded-2xl border-emerald-500/30 p-5 space-y-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
              <h4 className="font-bold text-foreground text-sm">
                1. Evidence-Based Verification (Primary)
              </h4>
            </div>
            <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
              Extracts declarative factual claims, retrieves candidate sentences from the normalized 126,000-sentence FEVER FAISS index (with conditional read-only Wikipedia API fallback for sparse or current-state queries), applies entity/predicate/temporal alignment gating, and evaluates entailment using Microsoft DeBERTa-v3 NLI on CPU.
            </p>
            <div className="space-y-1.5 pt-2 text-[11px] text-slate-600 dark:text-slate-400 font-mono">
              <div className="flex justify-between border-b border-border/70 pb-1">
                <span>Embedding Model:</span>
                <span className="text-foreground">all-MiniLM-L6-v2 (384d)</span>
              </div>
              <div className="flex justify-between border-b border-border/70 pb-1">
                <span>Index + Fallback:</span>
                <span className="text-foreground">FAISS FlatIP + Public Wikipedia API</span>
              </div>
              <div className="flex justify-between border-b border-border/70 pb-1">
                <span>NLI + Alignment:</span>
                <span className="text-foreground">DeBERTa-v3 + NEI Calibration Gate</span>
              </div>
              <div className="flex justify-between pt-1">
                <span>Evaluation Note:</span>
                <span className="text-amber-700 dark:text-amber-300">FEVER Oracle Acc: 97.25%</span>
              </div>
            </div>
          </div>

          {/* Secondary Tier */}
          <div className="glass-surface rounded-2xl border-amber-500/30 p-5 space-y-3">
            <div className="flex items-center gap-2">
              <Layers className="h-5 w-5 text-amber-600 dark:text-amber-400" />
              <h4 className="font-bold text-foreground text-sm">
                2. Experimental ML Signals (Supplementary)
              </h4>
            </div>
            <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
              Provides supplementary stylistic classifications from models trained on historical benchmark corpora. These serve as indicators only and carry explicit distribution-shift warnings.
            </p>
            <div className="space-y-1.5 pt-2 text-[11px] text-slate-600 dark:text-slate-400 font-mono">
              <div className="flex justify-between border-b border-border/70 pb-1">
                <span>Article Classifier:</span>
                <span className="text-foreground">BERT ISOT Temporal (Binary)</span>
              </div>
              <div className="flex justify-between border-b border-border/70 pb-1">
                <span>Claim Classifier:</span>
                <span className="text-foreground">BERT LIAR Final (6-class)</span>
              </div>
              <div className="flex justify-between border-b border-border/70 pb-1">
                <span>ISOT Limitation:</span>
                <span className="text-amber-700 dark:text-amber-300">Publisher & Date Shifts</span>
              </div>
              <div className="flex justify-between pt-1">
                <span>LIAR Accuracy:</span>
                <span className="text-foreground/90">~26.84% Benchmark Test</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Six-Class Verdict Policy Reference */}
      <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4">
        <h3 className="text-lg font-bold text-foreground">
          Six-Class Verdict Taxonomy
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-xs">
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 space-y-1">
            <span className="font-bold text-emerald-700 dark:text-emerald-300">GENUINE</span>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed">Strong, relevant supporting evidence matching claim entities and predicates without material contradiction.</p>
          </div>
          <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-3.5 space-y-1">
            <span className="font-bold text-rose-700 dark:text-rose-300">FAKE</span>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed">Directly refuted by relevant evidence containing verified factual, numerical, or entity contradictions.</p>
          </div>
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 space-y-1">
            <span className="font-bold text-amber-800 dark:text-amber-300">MISLEADING</span>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed">Material contextual distortion, attribution substitution, exaggeration, or resolved tension on real events.</p>
          </div>
          <div className="rounded-xl border border-indigo-500/35 bg-indigo-500/10 p-3.5 space-y-1">
            <span className="font-bold text-indigo-700 dark:text-indigo-300">PARTIALLY_TRUE</span>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed">Compound claims or multi-claim articles mixing corroborated assertions with refuted or outdated parts.</p>
          </div>
          <div className="rounded-xl border border-orange-500/35 bg-orange-500/10 p-3.5 space-y-1">
            <span className="font-bold text-orange-800 dark:text-orange-300">OUTDATED</span>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed">Historically true status or tenure framed in the present despite documented end dates or rebranding.</p>
          </div>
          <div className="glass-surface rounded-xl p-3.5 space-y-1">
            <span className="font-bold text-slate-700 dark:text-slate-300">UNVERIFIED</span>
            <p className="text-slate-700 dark:text-slate-300 leading-relaxed">Safe abstention when evidence is absent, unrelated, or insufficient; never treated as proof of falsehood.</p>
          </div>
        </div>
      </div>

      {/* Constraints & Specs Table */}
      <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-4">
        <h3 className="text-lg font-bold text-foreground">
          Engineering Constraints & System Specs
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
          <div className="glass-surface rounded-xl p-4 space-y-1">
            <span className="text-slate-600 dark:text-slate-400 font-medium">Compute Environment</span>
            <p className="font-mono font-bold text-foreground">Local CPU Only (4 Threads)</p>
            <p className="text-[11px] text-slate-600 dark:text-slate-400">Strictly respects 16 GB RAM laptop limit</p>
          </div>

          <div className="glass-surface rounded-xl p-4 space-y-1">
            <span className="text-slate-600 dark:text-slate-400 font-medium">Budget & Cloud APIs</span>
            <p className="font-mono font-bold text-foreground">₹0 ($0.00 USD)</p>
            <p className="text-[11px] text-slate-600 dark:text-slate-400">No proprietary LLM or paid search APIs</p>
          </div>

          <div className="glass-surface rounded-xl p-4 space-y-1">
            <span className="text-slate-600 dark:text-slate-400 font-medium">Blockchain Anchoring</span>
            <p className="font-mono font-bold text-foreground">Ethereum Sepolia</p>
            <p className="text-[11px] text-slate-600 dark:text-slate-400">SHA-256 result hash immutability</p>
          </div>
        </div>
      </div>
    </div>
  );
};
