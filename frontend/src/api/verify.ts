/**
 * frontend/src/api/verify.ts
 * Endpoints for text & article verification and health checks.
 */

import { apiFetch, ApiError } from './client';
import type {
  TextVerificationRequest,
  TextVerificationResponse,
  ArticleVerificationRequest,
  ArticleVerificationResponse,
  ImageAnalysisResponse,
  NewsListResponse,
  NewsSourcesResponse,
  NewsRefreshResponse,
  GdeltUsageStatus,
  BackendHealth,
  BlockchainStatus,
  AnchorRequest,
  AnchorResponse,
  VerifyHashResponse,
  OnChainRecordDetails
} from '@/types/verification';

export async function verifyText(data: TextVerificationRequest): Promise<TextVerificationResponse> {
  return apiFetch<TextVerificationResponse>('/verify/text', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function verifyArticle(data: ArticleVerificationRequest): Promise<ArticleVerificationResponse> {
  return apiFetch<ArticleVerificationResponse>('/verify/article', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function analyzeImage(file: File): Promise<ImageAnalysisResponse> {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/v1/analyze/image', {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      let errData;
      try {
        errData = await res.json();
      } catch {
        errData = { detail: await res.text() };
      }
      const msg = typeof errData.detail === 'string' ? errData.detail : res.statusText || 'Image analysis failed';
      throw new ApiError(msg, res.status, errData);
    }

    return await res.json();
  } catch (err: any) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(err.message || 'Image upload failed', 0);
  }
}

export async function checkBackendHealth(): Promise<BackendHealth> {
  // Hit root or health endpoint
  const url = '/api/v1/health';
  try {
    const res = await fetch(url);
    if (res.ok) {
      return await res.json();
    }
    // Fallback to root
    const rootRes = await fetch('/');
    return await rootRes.json();
  } catch (err) {
    throw new Error('Backend unreachable');
  }
}

export async function getNews(params?: {
  keyword?: string;
  publisher?: string;
  category?: string;
  limit?: number;
  offset?: number;
}): Promise<NewsListResponse> {
  const q = new URLSearchParams();
  if (params?.keyword) q.set('keyword', params.keyword);
  if (params?.publisher && params.publisher !== 'ALL') q.set('publisher', params.publisher);
  if (params?.category && params.category !== 'ALL') q.set('category', params.category);
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));

  const qs = q.toString();
  return apiFetch<NewsListResponse>(`/news${qs ? `?${qs}` : ''}`);
}

export async function getNewsSources(): Promise<NewsSourcesResponse> {
  return apiFetch<NewsSourcesResponse>('/news/sources');
}

export async function refreshNews(): Promise<NewsRefreshResponse> {
  return apiFetch<NewsRefreshResponse>('/news/refresh', {
    method: 'POST',
  });
}

export async function getExternalUsage(): Promise<GdeltUsageStatus> {
  return apiFetch<GdeltUsageStatus>('/news/gdelt-usage');
}

export async function verifyNewsArticle(articleId: string): Promise<ArticleVerificationResponse> {
  return apiFetch<ArticleVerificationResponse>(`/news/${articleId}/verify`, {
    method: 'POST',
  });
}

export async function getBlockchainStatus(): Promise<BlockchainStatus> {
  return apiFetch<BlockchainStatus>('/blockchain/status');
}

export async function anchorVerificationOnChain(data: AnchorRequest): Promise<AnchorResponse> {
  return apiFetch<AnchorResponse>('/blockchain/anchor', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function verifyRecordHash(verificationId: string, recordHash?: string): Promise<VerifyHashResponse> {
  return apiFetch<VerifyHashResponse>('/blockchain/verify-hash', {
    method: 'POST',
    body: JSON.stringify({
      verification_id: verificationId,
      record_hash: recordHash,
    }),
  });
}

export async function getOnChainRecord(verificationId: string): Promise<OnChainRecordDetails> {
  return apiFetch<OnChainRecordDetails>(`/blockchain/records/${encodeURIComponent(verificationId)}`);
}

export interface HistoryRecord {
  verification_id: string;
  content_type: string;
  title?: string | null;
  content_preview: string;
  original_content: string;
  verdict: any;
  confidence_score: number;
  explanation: string;
  evidence: any[];
  canonical_record: any;
  record_hash: string;
  blockchain_anchored: boolean;
  blockchain_status: 'unanchored' | 'confirmed' | 'failed' | 'pending';
  network?: string | null;
  chain_id?: number | null;
  contract_address?: string | null;
  transaction_hash?: string | null;
  block_number?: number | null;
  block_timestamp?: number | null;
  block_datetime?: string | null;
  submitter_address?: string | null;
  gas_used?: number | null;
  etherscan_url?: string | null;
  created_at: string;
  updated_at: string;
}

export interface HistoryListResponse {
  total: number;
  limit: number;
  offset: number;
  records: HistoryRecord[];
}

export interface AuditExplorerResponse {
  network: string;
  chain_id: number;
  contract_address: string;
  contract_deployed: boolean;
  total_records: number;
  records: HistoryRecord[];
}

export interface AuditCompareResponse {
  verification_id: string;
  status: string;
  matched: boolean | null;
  local_hash?: string;
  on_chain_hash?: string;
  submitter?: string;
  block_timestamp?: number;
  block_datetime?: string;
  contract_address?: string;
  transaction_hash?: string;
  etherscan_url?: string;
  explanation: string;
}

export interface PublicVerifyCertificateResponse {
  verification_id: string;
  status: 'MATCH' | 'MISMATCH' | 'NOT_FOUND' | 'NETWORK_UNAVAILABLE';
  is_authentic: boolean;
  canonical_hash?: string;
  on_chain_hash?: string;
  contract_address?: string;
  transaction_hash?: string;
  block_number?: number;
  block_datetime?: string;
  submitter?: string;
  network: string;
  chain_id?: number;
  etherscan_url?: string;
  message: string;
  epistemological_disclaimer: string;
}

export async function getHistoryRecords(params?: {
  content_type?: string;
  verdict?: string;
  blockchain_status?: string;
  search?: string;
  limit?: number;
  offset?: number;
  sort_by?: string;
  order?: string;
}): Promise<HistoryListResponse> {
  const q = new URLSearchParams();
  if (params?.content_type && params.content_type !== 'all') q.set('content_type', params.content_type);
  if (params?.verdict && params.verdict !== 'all') q.set('verdict', params.verdict);
  if (params?.blockchain_status && params.blockchain_status !== 'all') q.set('blockchain_status', params.blockchain_status);
  if (params?.search) q.set('search', params.search);
  if (params?.limit) q.set('limit', String(params.limit));
  if (params?.offset) q.set('offset', String(params.offset));
  if (params?.sort_by) q.set('sort_by', params.sort_by);
  if (params?.order) q.set('order', params.order);

  const qs = q.toString();
  return apiFetch<HistoryListResponse>(`/history${qs ? `?${qs}` : ''}`);
}

export async function getHistoryRecord(verificationId: string): Promise<HistoryRecord> {
  return apiFetch<HistoryRecord>(`/history/${encodeURIComponent(verificationId)}`);
}

export async function getAuditExplorerRecords(): Promise<AuditExplorerResponse> {
  return apiFetch<AuditExplorerResponse>('/blockchain/audit');
}

export async function compareAuditRecord(verificationId: string): Promise<AuditCompareResponse> {
  return apiFetch<AuditCompareResponse>(`/blockchain/audit/${encodeURIComponent(verificationId)}/compare`);
}

export async function verifyCertificatePublic(
  verificationId: string,
  recordHash?: string
): Promise<PublicVerifyCertificateResponse> {
  return apiFetch<PublicVerifyCertificateResponse>('/certificates/verify', {
    method: 'POST',
    body: JSON.stringify({
      verification_id: verificationId,
      record_hash: recordHash || undefined,
    }),
  });
}

export function getCertificateDownloadUrl(verificationId: string): string {
  return `/api/v1/certificates/${encodeURIComponent(verificationId)}/download`;
}


