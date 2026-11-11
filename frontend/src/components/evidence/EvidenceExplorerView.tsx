import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  FileDown,
  ExternalLink,
  RefreshCw,
  Copy,
  Check,
  ShieldCheck,
  Database,
  ChevronDown,
  ChevronUp,
  Sparkles,
  FileText,
  Image as ImageIcon,
  Download,
  Trash2,
} from 'lucide-react';
import {
  getHistoryRecords,
  getHistoryRecord,
  getCertificateDownloadUrl,
  type HistoryRecord,
} from '@/api/verify';
import type {
  EvidenceSentence,
  EvidenceAuditTrail,
  FactCheckMatch,
  NewsEvidence,
  ExternalSourceStatus,
  TextVerificationResponse,
  ArticleVerificationResponse,
} from '@/types/verification';
import { VerdictBadge } from '@/components/ui/VerdictBadge';
import { EvidenceCard } from '@/components/ui/EvidenceCard';
import { EvidenceAuditTrailCard } from '@/components/ui/EvidenceAuditTrailCard';
import { ExternalEvidenceSection } from '@/components/ui/ExternalEvidenceSection';
import { GlassSelect } from '@/components/ui/GlassSelect';
import { RippleButton } from '@/components/ui/RippleButton';
import { useHistory } from '@/hooks/useHistory';
import { cn } from '@/lib/utils';

const TYPE_OPTIONS = [
  { value: 'all', label: 'All Content Types' },
  { value: 'text', label: 'Text Claim' },
  { value: 'article', label: 'Article' },
  { value: 'image', label: 'Image OCR' },
];

const VERDICT_OPTIONS = [
  { value: 'all', label: 'All Verdicts' },
  { value: 'GENUINE', label: 'Genuine' },
  { value: 'FAKE', label: 'Fake' },
  { value: 'MISLEADING', label: 'Misleading' },
  { value: 'PARTIALLY_TRUE', label: 'Partially True' },
  { value: 'OUTDATED', label: 'Outdated' },
  { value: 'UNVERIFIED', label: 'Unverified' },
];

const STATUS_OPTIONS = [
  { value: 'all', label: 'All Blockchain States' },
  { value: 'confirmed', label: 'Confirmed On-Chain' },
  { value: 'unanchored', label: 'Unanchored' },
];

function isEvidenceSentence(item: any): item is EvidenceSentence {
  return Boolean(item && typeof item === 'object' && typeof item.text === 'string' && 'page' in item);
}

function isArticleClaimItem(item: any): boolean {
  return Boolean(item && typeof item === 'object' && typeof item.claim === 'string' && 'verdict' in item);
}

interface EvidenceExplorerViewProps {
  enableSessionTab?: boolean;
}

export const EvidenceExplorerView: React.FC<EvidenceExplorerViewProps> = ({
  enableSessionTab = true,
}) => {
  const { history: sessionHistory, exportToJson, clearHistory } = useHistory();

  const [sourceTab, setSourceTab] = useState<'sqlite' | 'session'>('sqlite');
  const [records, setRecords] = useState<HistoryRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [filterVerdict, setFilterVerdict] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Inspectable record expansion state
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detailCache, setDetailCache] = useState<Record<string, HistoryRecord>>({});
  const [loadingDetailId, setLoadingDetailId] = useState<string | null>(null);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getHistoryRecords({
        content_type: filterType,
        verdict: filterVerdict,
        blockchain_status: filterStatus,
        search: search.trim() || undefined,
        limit: 50,
      });
      setRecords(res.records);
      setTotal(res.total);
    } catch (err: any) {
      setError(err.message || 'Failed to load verification history.');
    } finally {
      setLoading(false);
    }
  }, [filterType, filterVerdict, filterStatus, search]);

  useEffect(() => {
    fetchRecords();
  }, [filterType, filterVerdict, filterStatus]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchRecords();
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleToggleInspect = async (record: HistoryRecord) => {
    if (expandedId === record.verification_id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(record.verification_id);

    if (!detailCache[record.verification_id]) {
      setLoadingDetailId(record.verification_id);
      try {
        const detail = await getHistoryRecord(record.verification_id);
        setDetailCache((prev) => ({ ...prev, [record.verification_id]: detail }));
      } catch {
        // Fall back smoothly to list record already loaded
        setDetailCache((prev) => ({ ...prev, [record.verification_id]: record }));
      } finally {
        setLoadingDetailId(null);
      }
    }
  };

  const renderInspectableRecordBody = (record: HistoryRecord) => {
    const detailed = detailCache[record.verification_id] || record;
    const isFetchingDetail = loadingDetailId === record.verification_id;

    // Also inspect if this ID is in browser session cache with richer runtime telemetry
    const sessionMatch = sessionHistory.find((s) => s.id === detailed.verification_id);
    const sessionData = sessionMatch?.data as
      | (TextVerificationResponse & ArticleVerificationResponse)
      | undefined;

    const auditTrail: EvidenceAuditTrail | null | undefined =
      (detailed as any).evidence_audit_trail || sessionData?.evidence_audit_trail;
    const factChecks: FactCheckMatch[] | undefined = sessionData?.fact_check_matches;
    const newsEv: NewsEvidence[] | undefined = sessionData?.news_evidence;
    const externalStatus: ExternalSourceStatus | null | undefined =
      sessionData?.external_source_status;

    const evList = Array.isArray(detailed.evidence) ? detailed.evidence : [];

    return (
      <div className="glass-surface border-t border-x-0 border-b-0 rounded-b-xl mt-3 pt-4 p-4 space-y-4">
        {isFetchingDetail && (
          <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
            <RefreshCw className="h-3.5 w-3.5 animate-spin text-brand-cyan" />
            <span>Loading full SQLite record...</span>
          </div>
        )}

        {/* Full Content & Explanation */}
        <div className="space-y-2 text-xs">
          {detailed.original_content && (
            <div className="glass-panel rounded-xl p-3.5 space-y-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                Submitted Content
              </span>
              <p className="text-foreground/95 leading-relaxed whitespace-pre-wrap">
                {detailed.original_content}
              </p>
            </div>
          )}

          {detailed.explanation && (
            <div className="glass-panel rounded-xl p-3.5 space-y-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                Verification Explanation
              </span>
              <p className="text-slate-700 dark:text-slate-300 leading-relaxed">
                {detailed.explanation}
              </p>
            </div>
          )}
        </div>

        {/* Typed Evidence Rendering */}
        {evList.length > 0 && detailed.content_type === 'text' && (
          <div className="space-y-2.5">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5 text-brand-cyan" />
              <span>Retrieved Knowledge Evidence ({evList.length})</span>
            </h3>
            <div className="space-y-2.5">
              {evList.filter(isEvidenceSentence).map((ev, idx) => (
                <EvidenceCard key={`${ev.doc_id}-${idx}`} evidence={ev} index={idx} />
              ))}
            </div>
          </div>
        )}

        {evList.length > 0 && detailed.content_type === 'article' && (
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5 text-indigo-500 dark:text-cyan-300" />
              <span>Extracted Claim Verdicts &amp; Evidence ({evList.length})</span>
            </h3>
            <div className="space-y-3">
              {evList.filter(isArticleClaimItem).map((cl: any, idx: number) => (
                <div key={idx} className="glass-panel rounded-xl p-4 space-y-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-bold text-foreground">
                      #{cl.relevance_rank || idx + 1}: "{cl.claim}"
                    </span>
                    <VerdictBadge verdict={cl.verdict} size="sm" />
                  </div>
                  {cl.explanation && (
                    <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                      {cl.explanation}
                    </p>
                  )}
                  {Array.isArray(cl.evidence) && cl.evidence.length > 0 && (
                    <div className="space-y-2 pt-1">
                      {cl.evidence.filter(isEvidenceSentence).map((ev: EvidenceSentence, eIdx: number) => (
                        <EvidenceCard key={eIdx} evidence={ev} index={eIdx} />
                      ))}
                    </div>
                  )}
                  {cl.evidence_audit_trail && (
                    <EvidenceAuditTrailCard auditTrail={cl.evidence_audit_trail} compact />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {evList.length > 0 && detailed.content_type === 'image' && (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400 flex items-center gap-1.5">
              <ImageIcon className="h-3.5 w-3.5 text-brand-cyan" />
              <span>Image Forensics Summary ({evList.length})</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
              {evList.map((obs: any, idx: number) => (
                <div key={idx} className="glass-panel rounded-xl p-3 space-y-1">
                  <span className="font-mono text-[10px] uppercase text-brand-blue dark:text-cyan-300">
                    {obs.type || 'Forensic Observation'}
                  </span>
                  {obs.description && (
                    <p className="text-slate-700 dark:text-slate-300">{obs.description}</p>
                  )}
                  {obs.text && (
                    <p className="font-mono text-[11px] text-foreground italic">"{obs.text}"</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {evList.length === 0 && !auditTrail && (
          <p className="text-xs text-slate-600 dark:text-slate-400 italic">
            No retrieved evidence passages were recorded for this entry.
          </p>
        )}

        {/* Render IEVE Audit Trail when present in DB or matching browser session */}
        {auditTrail ? (
          <EvidenceAuditTrailCard auditTrail={auditTrail} compact />
        ) : (
          <div className="glass-panel rounded-xl p-3 text-[11px] text-slate-600 dark:text-slate-400">
            Stored SQLite history archives canonical hashes, verdicts, and ranked evidence passages above. Full IEVE multi-provider query-attempt telemetry is inspectable immediately after verification or via Session Audit Cache.
          </div>
        )}

        {(factChecks || newsEv || externalStatus) && (
          <ExternalEvidenceSection
            factCheckMatches={factChecks}
            newsEvidence={newsEv}
            externalStatus={externalStatus}
            compact
          />
        )}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Data Source Toggle (Persistent SQLite vs Browser Session Audit Trails) */}
      {enableSessionTab && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="glass-surface inline-flex rounded-xl p-1 gap-1">
            <button
              type="button"
              onClick={() => setSourceTab('sqlite')}
              className={cn(
                'rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
                sourceTab === 'sqlite'
                  ? 'btn-primary-glow text-white'
                  : 'text-slate-600 dark:text-slate-300 hover:text-foreground'
              )}
            >
              SQLite Persistent Ledger ({total})
            </button>
            <button
              type="button"
              onClick={() => setSourceTab('session')}
              className={cn(
                'rounded-lg px-3.5 py-1.5 text-xs font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70',
                sourceTab === 'session'
                  ? 'btn-primary-glow text-white'
                  : 'text-slate-600 dark:text-slate-300 hover:text-foreground'
              )}
            >
              Session Audit Cache ({sessionHistory.length})
            </button>
          </div>

          <div className="flex items-center gap-2">
            {sourceTab === 'session' && sessionHistory.length > 0 && (
              <>
                <RippleButton
                  variant="glass"
                  onClick={exportToJson}
                  className="rounded-xl px-3 py-1.5 text-xs"
                >
                  <Download className="h-3.5 w-3.5 text-brand-cyan" />
                  <span>Export JSON</span>
                </RippleButton>
                <RippleButton
                  variant="glass"
                  onClick={clearHistory}
                  className="rounded-xl px-3 py-1.5 text-xs text-rose-700 dark:text-rose-300"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span>Clear Session</span>
                </RippleButton>
              </>
            )}

            {sourceTab === 'sqlite' && (
              <RippleButton
                variant="glass"
                onClick={fetchRecords}
                disabled={loading}
                className="rounded-xl px-3 py-1.5 text-xs"
              >
                <RefreshCw className={`h-3.5 w-3.5 text-brand-cyan ${loading ? 'animate-spin' : ''}`} />
                <span>Refresh</span>
              </RippleButton>
            )}
          </div>
        </div>
      )}

      {/* SQLite Ledger View */}
      {sourceTab === 'sqlite' && (
        <>
          <div className="glass-panel rounded-2xl p-4 space-y-3">
            <form onSubmit={handleSearchSubmit} className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-slate-400" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search claim, verification ID, title, or tx hash..."
                  className="glass-surface w-full rounded-xl pl-10 pr-4 py-2 text-xs sm:text-sm text-foreground placeholder:text-slate-500 focus:outline-none focus:border-cyan-400 transition-colors"
                />
              </div>
              <RippleButton type="submit" variant="primary" className="rounded-xl px-4 py-2 text-xs">
                Search
              </RippleButton>
            </form>

            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border/60">
              <span className="text-[11px] font-semibold uppercase text-slate-600 dark:text-slate-400 mr-1">
                Filters:
              </span>

              <GlassSelect
                value={filterType}
                onChange={setFilterType}
                options={TYPE_OPTIONS}
                ariaLabel="Filter by content type"
              />

              <GlassSelect
                value={filterVerdict}
                onChange={setFilterVerdict}
                options={VERDICT_OPTIONS}
                ariaLabel="Filter by verdict"
              />

              <GlassSelect
                value={filterStatus}
                onChange={setFilterStatus}
                options={STATUS_OPTIONS}
                ariaLabel="Filter by blockchain status"
              />

              <span className="ml-auto text-xs text-slate-600 dark:text-slate-400 font-mono">
                Total Records: <strong className="text-foreground">{total}</strong>
              </span>
            </div>
          </div>

          {error && (
            <div className="glass-panel rounded-xl border-rose-500/35 bg-rose-500/10 p-4 text-xs text-rose-800 dark:text-rose-200">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex flex-col items-center justify-center p-12 text-slate-600 dark:text-slate-400 space-y-3">
              <RefreshCw className="h-6 w-6 animate-spin text-brand-cyan" />
              <p className="text-sm">Loading persistent verification records from SQLite...</p>
            </div>
          ) : records.length === 0 ? (
            <div className="glass-panel rounded-2xl p-12 text-center text-slate-600 dark:text-slate-400 space-y-2">
              <Database className="mx-auto h-8 w-8 text-slate-500" />
              <p className="text-sm font-medium text-foreground">No verification records found.</p>
              <p className="text-xs">Verify a text claim or article to begin building your audit trail.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {records.map((item) => {
                const isExpanded = expandedId === item.verification_id;
                return (
                  <div
                    key={item.verification_id}
                    className="glass-panel rounded-xl p-5 space-y-3 hover:border-cyan-400/35 transition-colors"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="flex flex-wrap items-center gap-2.5">
                        <VerdictBadge verdict={item.verdict} size="sm" />
                        <span className="font-mono text-xs font-semibold text-foreground">
                          {item.verification_id}
                        </span>
                        <span className="glass-surface rounded px-2 py-0.5 text-[11px] uppercase tracking-wide text-slate-600 dark:text-slate-300 font-mono">
                          {item.content_type}
                        </span>

                        {item.blockchain_status === 'confirmed' ? (
                          <span className="inline-flex items-center space-x-1 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
                            <ShieldCheck className="h-3 w-3" />
                            <span>Sepolia Confirmed {item.block_number ? `(#${item.block_number})` : ''}</span>
                          </span>
                        ) : (
                          <span className="glass-surface rounded-full px-2.5 py-0.5 text-[11px] font-medium text-slate-600 dark:text-slate-400">
                            Unanchored
                          </span>
                        )}
                      </div>

                      <div className="flex items-center space-x-2 text-xs text-slate-600 dark:text-slate-400">
                        <span>Confidence:</span>
                        <span className="font-mono font-bold text-foreground">
                          {item.content_type === 'image'
                            ? 'N/A (Visual Forensics)'
                            : `${(item.confidence_score * 100).toFixed(0)}%`}
                        </span>
                        <span>&middot;</span>
                        <span>{item.created_at ? new Date(item.created_at).toLocaleDateString() : 'N/A'}</span>
                      </div>
                    </div>

                    <p className="text-xs sm:text-sm text-foreground/95 font-medium leading-relaxed">
                      {item.content_preview}
                    </p>

                    <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-border/60 text-xs">
                      <div className="flex items-center space-x-2 font-mono text-slate-600 dark:text-slate-400 text-[11px]">
                        <span>SHA-256:</span>
                        <span className="text-indigo-700 dark:text-cyan-300">
                          0x{item.record_hash ? item.record_hash.slice(0, 16) : ''}...
                        </span>
                        <button
                          type="button"
                          onClick={() => handleCopy(item.record_hash, item.verification_id)}
                          className="text-slate-500 hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70 rounded"
                          title="Copy full hash"
                          aria-label="Copy SHA-256 hash"
                        >
                          {copiedId === item.verification_id ? (
                            <Check className="h-3 w-3 text-emerald-500 dark:text-emerald-400" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                        </button>
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handleToggleInspect(item)}
                          aria-expanded={isExpanded}
                          className="glass-surface flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold text-brand-blue dark:text-cyan-300 hover:border-cyan-400/45 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400/70"
                        >
                          <span>{isExpanded ? 'Hide Evidence' : 'Inspect Evidence'}</span>
                          {isExpanded ? (
                            <ChevronUp className="h-3.5 w-3.5" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5" />
                          )}
                        </button>

                        {item.blockchain_status === 'confirmed' ? (
                          <>
                            <a
                              href={getCertificateDownloadUrl(item.verification_id)}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center space-x-1 rounded-lg border border-indigo-500/35 bg-indigo-500/15 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300 hover:bg-indigo-500/25 transition-colors"
                              title="Download official PDF certificate"
                            >
                              <FileDown className="h-3 w-3" />
                              <span>Download Certificate</span>
                            </a>

                            <Link
                              to={`/verify-certificate?id=${encodeURIComponent(item.verification_id)}&hash=${encodeURIComponent(item.record_hash)}`}
                              className="glass-surface flex items-center space-x-1 rounded-lg px-2.5 py-1 text-xs font-medium text-foreground/90 hover:border-cyan-400/45 transition-colors"
                            >
                              <ShieldCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                              <span>Audit Certificate</span>
                            </Link>

                            {item.etherscan_url && (
                              <a
                                href={item.etherscan_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center space-x-1 text-brand-blue dark:text-cyan-300 hover:underline text-xs"
                                title="View on Sepolia Etherscan"
                              >
                                <span>Etherscan</span>
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                          </>
                        ) : (
                          <Link
                            to="/verify?tab=text"
                            className="glass-surface rounded-lg px-2.5 py-1 text-xs font-medium text-foreground/90 hover:border-cyan-400/45 transition-colors"
                          >
                            New Check
                          </Link>
                        )}
                      </div>
                    </div>

                    {isExpanded && renderInspectableRecordBody(item)}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Session Cache View (localStorage with full IEVE Audit Trails) */}
      {sourceTab === 'session' && (
        <div className="space-y-4">
          {sessionHistory.length === 0 ? (
            <div className="glass-panel rounded-2xl p-12 text-center text-slate-600 dark:text-slate-400 space-y-2">
              <Sparkles className="mx-auto h-8 w-8 text-brand-cyan" />
              <p className="text-sm font-medium text-foreground">No session verifications stored yet.</p>
              <p className="text-xs">
                Run a verification in <strong>/verify</strong> to inspect full multi-direction retrieval and NLI audit trails here.
              </p>
            </div>
          ) : (
            sessionHistory.map((item) => {
              const data = item.data as TextVerificationResponse & ArticleVerificationResponse;
              const isExpanded = expandedId === item.id;
              return (
                <div key={item.id} className="glass-panel rounded-xl p-5 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <VerdictBadge verdict={item.verdict} size="sm" />
                      <span className="glass-surface rounded px-2 py-0.5 text-[11px] font-mono uppercase text-slate-700 dark:text-slate-300">
                        {item.type}
                      </span>
                      <span className="text-xs font-mono text-slate-600 dark:text-slate-400">
                        {new Date(item.timestamp).toLocaleString()}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={() => setExpandedId(isExpanded ? null : item.id)}
                      className="glass-surface flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold text-brand-blue dark:text-cyan-300 hover:border-cyan-400/45"
                    >
                      <span>{isExpanded ? 'Hide Audit Trail' : 'Inspect Evidence & Trail'}</span>
                      {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                    </button>
                  </div>

                  <p className="text-xs sm:text-sm text-foreground font-medium">{item.preview}</p>

                  {isExpanded && (
                    <div className="glass-surface border-t border-x-0 border-b-0 rounded-b-xl pt-4 p-4 space-y-4">
                      {Array.isArray(data.evidence) && data.evidence.length > 0 && (
                        <div className="space-y-2">
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-400">
                            Evidence Sentences ({data.evidence.length})
                          </h3>
                          {data.evidence.map((ev, idx) => (
                            <EvidenceCard key={idx} evidence={ev} index={idx} />
                          ))}
                        </div>
                      )}
                      <EvidenceAuditTrailCard auditTrail={data.evidence_audit_trail} compact />
                      <ExternalEvidenceSection
                        factCheckMatches={data.fact_check_matches}
                        newsEvidence={data.news_evidence}
                        externalStatus={data.external_source_status}
                        compact
                      />
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      )}
    </div>
  );
};
