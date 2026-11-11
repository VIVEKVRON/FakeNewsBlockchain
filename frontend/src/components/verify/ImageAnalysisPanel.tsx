import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Image as ImageIcon,
  UploadCloud,
  AlertTriangle,
  FileCheck2,
  Cpu,
  Layers,
  ArrowRight,
  FileText,
  HelpCircle,
} from 'lucide-react';
import { analyzeImage } from '@/api/verify';
import type { ImageAnalysisResponse } from '@/types/verification';
import { LimitationsCallout } from '@/components/ui/LimitationsCallout';
import { LoadingSkeleton } from '@/components/ui/LoadingSkeleton';
import { ErrorBanner } from '@/components/ui/ErrorBanner';
import { RippleButton } from '@/components/ui/RippleButton';

interface ImageAnalysisPanelProps {
  showHeader?: boolean;
  onVerifyExtractedText?: (text: string) => void;
}

export const ImageAnalysisPanel: React.FC<ImageAnalysisPanelProps> = ({
  showHeader = true,
  onVerifyExtractedText,
}) => {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImageAnalysisResponse | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleFileSelect = (file: File) => {
    const allowed = ['image/jpeg', 'image/png', 'image/webp'];
    if (!allowed.includes(file.type)) {
      setError('Please select a JPG, PNG, or WEBP image.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('File size exceeds the 10 MB limit.');
      return;
    }

    setError(null);
    setSelectedFile(file);
    setResult(null);

    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handleAnalyze = async () => {
    if (!selectedFile) return;

    setLoading(true);
    setError(null);

    try {
      const response = await analyzeImage(selectedFile);
      setResult(response);
    } catch (err: any) {
      setError(err.message || 'Image analysis failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyInTextPipeline = () => {
    if (!result?.ocr.full_text) return;
    if (onVerifyExtractedText) {
      onVerifyExtractedText(result.ocr.full_text);
      return;
    }
    navigate('/verify?tab=text', { state: { prefillClaim: result.ocr.full_text } });
  };

  return (
    <div className="space-y-8">
      {showHeader && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-brand-blue dark:text-cyan-300">
            <ImageIcon className="h-4 w-4" />
            <span>Multimodal Forensics &middot; OCR &amp; ELA</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
            Multimodal Image Analysis (OCR &amp; ELA)
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Extract text embedded in news imagery using PaddleOCR and compute compression variance indicators using OpenCV Error Level Analysis (ELA).
          </p>
        </div>
      )}

      {/* Critical Epistemological Disclaimer */}
      <div className="glass-panel rounded-2xl border-amber-500/30 bg-amber-500/10 dark:bg-amber-950/20 p-5 text-xs text-amber-900 dark:text-amber-200/90 leading-relaxed flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <h2 className="font-bold text-amber-800 dark:text-amber-300">Methodology &amp; Authenticity Notice</h2>
          <p>
            Error Level Analysis (ELA) and Optical Character Recognition (OCR) are visual and forensic indicators,
            <strong> not definitive proof of image forgery or synthetic AI generation</strong>.
            Resaving, resizing, or social-media re-encoding generates compression artifacts that must never be presented as proof of manipulation.
          </p>
        </div>
      </div>

      {/* Upload Dropzone */}
      <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-6">
        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files[0]) {
              handleFileSelect(e.target.files[0]);
            }
          }}
        />

        {!selectedFile ? (
          <div
            role="button"
            tabIndex={0}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            className={`glass-surface cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 ${
              dragActive ? 'border-cyan-400 bg-cyan-500/10' : 'hover:border-cyan-400/60'
            }`}
          >
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan-500/15 text-brand-blue dark:text-cyan-300 mx-auto border border-cyan-500/30 mb-3">
              <UploadCloud className="h-7 w-7" />
            </div>
            <h3 className="text-sm font-bold text-foreground">
              Drop news graphic or screenshot here, or click to browse
            </h3>
            <p className="text-xs text-slate-600 dark:text-slate-400 mt-1">
              Supports JPEG, PNG, WEBP up to 10 MB &middot; Local CPU processing only
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
              <div className="flex items-center gap-3">
                {previewUrl && (
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="h-16 w-16 object-cover rounded-xl border border-border shadow-sm"
                  />
                )}
                <div>
                  <h3 className="text-sm font-bold text-foreground">{selectedFile.name}</h3>
                  <p className="text-xs text-slate-600 dark:text-slate-400 font-mono">
                    {(selectedFile.size / 1024).toFixed(1)} KB &middot; {selectedFile.type || 'image/jpeg'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <RippleButton
                  variant="glass"
                  onClick={() => {
                    setSelectedFile(null);
                    setPreviewUrl(null);
                    setResult(null);
                  }}
                  className="rounded-xl px-3.5 py-2 text-xs text-slate-700 dark:text-slate-300"
                >
                  Change Image
                </RippleButton>

                <RippleButton
                  variant="primary"
                  onClick={handleAnalyze}
                  disabled={loading}
                  className="rounded-xl px-5 py-2 text-xs"
                >
                  <Cpu className="h-3.5 w-3.5" />
                  <span>Analyze Image</span>
                </RippleButton>
              </div>
            </div>
          </div>
        )}
      </div>

      {loading && (
        <LoadingSkeleton message="Running OpenCV ELA Compression Analysis & PaddleOCR Extraction on CPU..." />
      )}

      {error && <ErrorBanner message={error} onRetry={handleAnalyze} />}

      {result && !loading && (
        <div className="space-y-8">
          <div className="glass-panel rounded-2xl border-amber-500/30 bg-amber-500/10 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="rounded-md bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-500/35 px-2.5 py-1 text-xs font-bold uppercase tracking-wide">
                Factual Verdict: UNVERIFIED
              </span>
              <span className="text-xs text-slate-700 dark:text-slate-300">
                Visual Forensics &amp; Text Extraction Only &middot; OCR recognition fidelity is strictly separate from factual truth
              </span>
            </div>
            <div className="text-xs font-mono text-slate-600 dark:text-slate-400">
              ID: {result.analysis_id}
            </div>
          </div>

          <div className="glass-panel rounded-2xl p-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
            <div className="space-y-0.5">
              <span className="text-slate-600 dark:text-slate-400">Resolution</span>
              <p className="font-mono font-bold text-foreground">
                {result.metadata.width} &times; {result.metadata.height}
              </p>
            </div>
            <div className="space-y-0.5">
              <span className="text-slate-600 dark:text-slate-400">Format</span>
              <p className="font-mono font-bold text-foreground">{result.metadata.format}</p>
            </div>
            <div className="space-y-0.5">
              <span className="text-slate-600 dark:text-slate-400">Aspect Ratio</span>
              <p className="font-mono font-bold text-foreground">{result.metadata.aspect_ratio} : 1</p>
            </div>
            <div className="space-y-0.5">
              <span className="text-slate-600 dark:text-slate-400">File Size</span>
              <p className="font-mono font-bold text-foreground">
                {(result.metadata.file_size_bytes / 1024).toFixed(1)} KB
              </p>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-foreground flex items-center gap-2">
                <Layers className="h-4 w-4 text-brand-cyan" />
                <span>Error Level Analysis (ELA) Compression Map</span>
              </h2>
              <span className="text-xs text-slate-600 dark:text-slate-400 font-mono">
                Quality Tested: {result.ela.quality_tested}%
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="glass-panel rounded-2xl p-4 space-y-2">
                <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">Original Upload</span>
                <div className="rounded-xl overflow-hidden bg-slate-950/90 flex items-center justify-center min-h-[220px] border border-border/50">
                  {previewUrl && (
                    <img src={previewUrl} alt="Original Upload" className="max-h-[300px] w-auto object-contain" />
                  )}
                </div>
              </div>

              <div className="glass-panel rounded-2xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-600 dark:text-slate-400">Enhanced ELA Difference Map</span>
                  <span className="text-[11px] font-mono text-brand-blue dark:text-cyan-300">15x Contrast Boost</span>
                </div>
                <div className="rounded-xl overflow-hidden bg-slate-950/90 flex items-center justify-center min-h-[220px] border border-border/50">
                  {result.ela.ela_image_base64 && (
                    <img
                      src={result.ela.ela_image_base64}
                      alt="ELA Enhanced Difference Map"
                      className="max-h-[300px] w-auto object-contain"
                    />
                  )}
                </div>
              </div>
            </div>

            <div className="glass-panel rounded-2xl p-5 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                  Compression Variance Metrics
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-bold border ${
                    result.ela.potential_compression_anomalies
                      ? 'bg-amber-500/15 text-amber-800 dark:text-amber-300 border-amber-500/30'
                      : 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/30'
                  }`}
                >
                  {result.ela.potential_compression_anomalies
                    ? 'Localized Discrepancies Noted'
                    : 'Uniform Compression Distribution'}
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="glass-surface rounded-lg p-2.5">
                  <span className="text-slate-600 dark:text-slate-400">Mean Delta Error:</span>
                  <p className="font-mono text-sm font-bold text-foreground mt-0.5">
                    {result.ela.mean_error.toFixed(2)}
                  </p>
                </div>
                <div className="glass-surface rounded-lg p-2.5">
                  <span className="text-slate-600 dark:text-slate-400">Max Delta Error:</span>
                  <p className="font-mono text-sm font-bold text-foreground mt-0.5">{result.ela.max_error}</p>
                </div>
                <div className="glass-surface rounded-lg p-2.5">
                  <span className="text-slate-600 dark:text-slate-400">Standard Deviation:</span>
                  <p className="font-mono text-sm font-bold text-foreground mt-0.5">
                    {result.ela.std_error.toFixed(2)}
                  </p>
                </div>
                <div className="glass-surface rounded-lg p-2.5">
                  <span className="text-slate-600 dark:text-slate-400">Variance Score:</span>
                  <p className="font-mono text-sm font-bold text-foreground mt-0.5">
                    {result.ela.variance_score.toFixed(2)}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="glass-panel rounded-3xl p-6 sm:p-8 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-border/70 pb-4">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-brand-blue dark:text-cyan-300" />
                <h2 className="text-base font-bold text-foreground">
                  Extracted Typography &amp; Claims (PaddleOCR)
                </h2>
              </div>

              {result.ocr.has_text && (
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-brand-blue/15 border border-brand-blue/30 px-2.5 py-0.5 text-xs font-mono text-brand-blue dark:text-cyan-300">
                    Avg Confidence: {(result.ocr.average_confidence * 100).toFixed(1)}%
                  </span>
                  <span className="glass-surface rounded-full px-2.5 py-0.5 text-xs font-mono text-slate-700 dark:text-slate-300">
                    {result.ocr.word_count} words
                  </span>
                </div>
              )}
            </div>

            {!result.ocr.has_text ? (
              <div className="glass-surface rounded-2xl p-6 text-center text-xs text-slate-600 dark:text-slate-400 space-y-1">
                <HelpCircle className="h-8 w-8 text-slate-500 mx-auto mb-2" />
                <p className="font-medium text-foreground">No Text Detected in Image</p>
                <p>The OCR engine scanned the image pixels but found no readable Latin typography.</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
                    Full Transcribed Text
                  </label>
                  <blockquote className="glass-surface rounded-2xl border-l-2 border-l-cyan-500 p-4 text-sm text-foreground leading-relaxed italic">
                    "{result.ocr.full_text}"
                  </blockquote>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider">
                    Detected Text Blocks ({result.ocr.text_blocks.length})
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {result.ocr.text_blocks.map((block, bIdx) => (
                      <div
                        key={bIdx}
                        className="glass-surface rounded-xl p-3 flex items-center justify-between gap-3 text-xs"
                      >
                        <span className="font-medium text-foreground truncate">{block.text}</span>
                        <span className="font-mono text-[11px] text-brand-blue dark:text-cyan-300 bg-cyan-500/10 rounded px-1.5 py-0.5 shrink-0">
                          {(block.confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="glass-surface pt-4 p-4 flex flex-col sm:flex-row items-center justify-between gap-3 rounded-2xl border-cyan-500/30 bg-gradient-to-r from-[#087BFF]/10 to-[#00C8FF]/10">
                  <div className="space-y-0.5">
                    <h3 className="text-sm font-bold text-foreground">Verify Extracted Factual Claims</h3>
                    <p className="text-xs text-slate-600 dark:text-slate-400">
                      Send the transcribed text directly to the DeBERTa + FAISS claim verification pipeline.
                    </p>
                  </div>
                  <RippleButton
                    variant="primary"
                    onClick={handleVerifyInTextPipeline}
                    className="rounded-xl px-4 py-2 text-xs shrink-0"
                  >
                    <FileCheck2 className="h-4 w-4" />
                    <span>Verify with Fact Engine</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </RippleButton>
                </div>
              </div>
            )}
          </div>

          <div className="glass-panel rounded-2xl p-5 space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
              System Forensic Observations
            </h3>
            <ul className="space-y-1.5 text-xs text-slate-700 dark:text-slate-300 list-disc list-inside">
              {result.observations.map((obs, oIdx) => (
                <li key={oIdx} className="leading-relaxed">
                  <span>{obs}</span>
                </li>
              ))}
            </ul>
          </div>

          <LimitationsCallout limitations={result.limitations} />
        </div>
      )}
    </div>
  );
};
