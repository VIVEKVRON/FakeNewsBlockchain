/**
 * frontend/src/types/verification.ts
 * TypeScript interfaces matching backend FastAPI schemas.
 */

export type VerdictType =
  | 'GENUINE'
  | 'FAKE'
  | 'MISLEADING'
  | 'PARTIALLY_TRUE'
  | 'UNVERIFIED'
  | 'OUTDATED'
  | 'LIKELY_GENUINE'
  | 'LIKELY_FAKE';

export type NLILabelType = 'SUPPORTS' | 'REFUTES' | 'NOT ENOUGH INFO';

export interface EvidenceSentence {
  rank: number;
  page: string;
  sentence_id: number;
  doc_id: string;
  text: string;
  retrieval_similarity: number;
  nli_label: NLILabelType;
  nli_confidence: number;
  nli_probabilities: {
    supports?: number;
    refutes?: number;
    not_enough_info?: number;
    SUPPORTS?: number;
    REFUTES?: number;
    'NOT ENOUGH INFO'?: number;
  };
  source_type?: string;
  source_url?: string | null;
  publication_date?: string | null;
  evidence_role?: 'supporting' | 'contradicting' | 'contextual';
  alignment_notes?: string | null;
  retrieval_direction?: string;
}

export interface ModelSignal {
  model_name: string;
  dataset_origin: string;
  applicable_input_type: string;
  applicable: boolean;
  prediction?: string | null;
  confidence?: number | null;
  probabilities: Record<string, number>;
  raw_logits: Record<string, number>;
  preliminary_verdict_tag?: string | null;
  disclaimer: string;
}

export interface InitialMLSignals {
  liar_signal: ModelSignal;
  isot_signal: ModelSignal;
  preliminary_verdict: string;
  note: string;
}

export interface DebertaNLISummary {
  model_name: string;
  evaluation_stage: string;
  pairs_evaluated: number;
  raw_label_counts: Record<string, number>;
  calibrated_label_counts: Record<string, number>;
  max_raw_probability: number;
  disclaimer: string;
}

export interface RetrievalAttempt {
  provider: string;
  direction: string;
  query: string;
  outcome: string;
  available: boolean;
  from_cache: boolean;
  items_retrieved: number;
  relevant_items: number;
  reason?: string | null;
  claim_text?: string | null;
  claim_id?: string | null;
}

export interface GdeltClaimSelection {
  claim: string;
  selected: boolean;
  reason: string;
  query?: string;
  status?: string;
}

export interface AuditSourceItem {
  source_type: string;
  source_name: string;
  title_or_page: string;
  text_excerpt: string;
  url?: string | null;
  publication_date?: string | null;
  retrieved_at: string;
  retrieval_direction: string;
  stance: string;
  is_relevant: boolean;
  rejection_reason?: string | null;
  relevance_score: number;
  subject_entity_alignment: number;
  predicate_alignment: number;
  temporal_relevance: number;
  temporal_status: string;
  geographic_relevance: number;
  geographic_status: string;
  source_reliability_tier: string;
  evidence_tier: string;
  meets_single_source_criteria: boolean;
  provenance_weight: number;
  evidence_specificity: number;
  independent_group_key: string;
  contradiction_strength: number;
  source_freshness: string;
  overall_quality_score: number;
  alignment_notes: string;
  ml_nli_label: string;
  ml_nli_confidence: number;
  ml_nli_probabilities: Record<string, number>;
}

export interface ProviderStatusItem {
  provider: string;
  status: string;
  available: boolean;
  items_retrieved: number;
  relevant_items: number;
  error_or_reason?: string | null;
}

export interface EvidenceQualitySummary {
  support_count: number;
  contradict_count: number;
  neutral_count: number;
  independent_supporting_sources: number;
  independent_contradicting_sources: number;
  rejected_irrelevant_count: number;
  syndicated_duplicates_collapsed: number;
  max_support_quality: number;
  max_contradict_quality: number;
  temporal_mismatch_detected: boolean;
  geographic_mismatch_detected: boolean;
  tier1_official_primary_count: number;
  tier2_encyclopedic_count: number;
  tier3_secondary_or_metadata_count: number;
  primary_official_sources_available: boolean;
  claim_requires_primary_record: boolean;
  primary_record_need_reason?: string | null;
  methodology_note: string;
}

export interface EvidenceAuditTrail {
  initial_ml_signals: InitialMLSignals;
  nli_evaluation: DebertaNLISummary;
  directions_executed: string[];
  queries_by_direction: Record<string, string>;
  retrieval_attempts: RetrievalAttempt[];
  gdelt_claim_selections?: GdeltClaimSelection[];
  supporting_evidence: AuditSourceItem[];
  contradicting_evidence: AuditSourceItem[];
  neutral_evidence: AuditSourceItem[];
  rejected_irrelevant_evidence: AuditSourceItem[];
  conflicts_detected: boolean;
  conflict_details: string[];
  provider_statuses: ProviderStatusItem[];
  unavailable_providers: string[];
  evidence_quality_summary: EvidenceQualitySummary;
  second_pass_decision: string;
  verdict_changed_from_initial: boolean;
  verdict_change_reason?: string | null;
  second_pass_reasoning: string;
  final_verdict: string;
  final_confidence: number;
  total_retrieval_attempts?: number;
  omitted_retrieval_attempts?: number;
}

export interface SubClaimVerdict {
  claim: string;
  verdict: VerdictType;
  confidence_score: number;
  explanation: string;
  uncertainty_explanation?: string;
  evidence: EvidenceSentence[];
  evidence_audit_trail?: EvidenceAuditTrail | null;
}

export interface FactCheckMatch {
  claim_text?: string | null;
  review_title?: string | null;
  publisher_name?: string | null;
  publisher_site?: string | null;
  reviewer_name?: string | null;
  rating_text?: string | null;
  review_url?: string | null;
  review_publication_date?: string | null;
  claim_appearance_date?: string | null;
  original_claim_author?: string | null;
  language_code?: string | null;
  retrieved_at: string;
  is_stale: boolean;
  stale_reason?: string | null;
  is_conflicting: boolean;
}

export interface NewsEvidence {
  title: string;
  url: string;
  domain: string;
  published_at?: string | null;
  language?: string | null;
  source_country?: string | null;
  search_query: string;
  search_window: string;
  retrieved_at: string;
  syndicated_count: number;
}

export interface GdeltUsageStatus {
  enabled: boolean;
  allowance_limit: number;
  requests_used: number;
  requests_remaining: number;
  warning_threshold: number;
  warning_active: boolean;
  limit_reached: boolean;
  cache_hits: number;
  failed_requests: number;
  last_request_at?: string | null;
  last_source?: string | null;
  last_status?: string | null;
  tracker_available: boolean;
  accounting_rule: string;
  google_fact_check_available?: boolean | null;
}

export interface ExternalSourceStatus {
  google_fact_check_status: string;
  google_fact_check_available: boolean;
  google_fact_check_error?: string | null;
  gdelt_status: string;
  gdelt_error?: string | null;
  has_conflicting_fact_checks: boolean;
  has_stale_fact_checks: boolean;
  gdelt_conflicting_coverage: boolean;
  duplicates_collapsed: number;
  gdelt_usage?: GdeltUsageStatus | null;
  supplementary_notes: string[];
}

export interface TextVerificationRequest {
  claim: string;
  top_k?: number;
}

export interface TextVerificationResponse {
  verification_id: string;
  claim: string;
  verdict: VerdictType;
  confidence_score: number;
  explanation: string;
  uncertainty_explanation?: string;
  conflicting_evidence_detected: boolean;
  strongest_evidence_page: string | null;
  evidence: EvidenceSentence[];
  claim_verdicts?: SubClaimVerdict[];
  fact_check_matches?: FactCheckMatch[];
  news_evidence?: NewsEvidence[];
  external_source_status?: ExternalSourceStatus | null;
  evidence_audit_trail?: EvidenceAuditTrail | null;
  limitations: string[];
  created_at: string;
  blockchain_hash?: VerificationHashSummary;
}

export interface ArticleClassifierSignal {
  model: string;
  prediction: 'FAKE' | 'REAL';
  confidence: number;
  probabilities: {
    FAKE: number;
    REAL: number;
  };
  distribution_shift_warning: string;
}

export interface LIARClassifierSignal {
  model: string;
  prediction: 'pants-fire' | 'false' | 'barely-true' | 'half-true' | 'mostly-true' | 'true';
  confidence: number;
  probabilities: Record<string, number>;
  disclaimer: string;
}

export interface ExtractedClaimVerification {
  claim: string;
  relevance_rank: number;
  verdict: VerdictType;
  confidence_score: number;
  explanation: string;
  uncertainty_explanation?: string;
  evidence: EvidenceSentence[];
  liar_signal?: LIARClassifierSignal;
  evidence_audit_trail?: EvidenceAuditTrail | null;
}

export interface ArticleVerificationRequest {
  title?: string;
  text: string;
  max_claims?: number;
  source_url?: string;
}

export interface ArticleVerificationResponse {
  article_id: string;
  title?: string;
  overall_verdict: VerdictType;
  overall_confidence: number;
  summary_explanation: string;
  uncertainty_explanation?: string;
  article_classifier: ArticleClassifierSignal;
  claims_analyzed: number;
  extracted_claims: ExtractedClaimVerification[];
  fact_check_matches?: FactCheckMatch[];
  news_evidence?: NewsEvidence[];
  external_source_status?: ExternalSourceStatus | null;
  evidence_audit_trail?: EvidenceAuditTrail | null;
  limitations: string[];
  created_at: string;
  blockchain_hash?: VerificationHashSummary;
}

export interface HistoryItem {
  id: string;
  type: 'claim' | 'article';
  title?: string;
  preview: string;
  verdict: VerdictType;
  confidence: number;
  timestamp: string;
  data: TextVerificationResponse | ArticleVerificationResponse;
}

export interface BackendHealth {
  status: string;
  project: string;
  version: string;
  timestamp: string;
}

export interface ImageMetadata {
  filename: string;
  content_type: string;
  format: string;
  width: number;
  height: number;
  aspect_ratio: number;
  file_size_bytes: number;
}

export interface OCRTextBlock {
  text: string;
  confidence: number;
  box: number[][];
}

export interface OCRResult {
  has_text: boolean;
  full_text: string;
  word_count: number;
  average_confidence: number;
  text_blocks: OCRTextBlock[];
}

export interface ELAResult {
  mean_error: number;
  max_error: number;
  std_error: number;
  variance_score: number;
  quality_tested: number;
  potential_compression_anomalies: boolean;
  anomaly_regions_detected: number;
  ela_image_base64: string | null;
}

export interface ImageAnalysisResponse {
  analysis_id: string;
  verdict?: VerdictType;
  factual_verification_status?: string;
  metadata: ImageMetadata;
  ocr: OCRResult;
  ela: ELAResult;
  observations: string[];
  limitations: string[];
  created_at: string;
  blockchain_hash?: VerificationHashSummary;
}

export interface NewsArticle {
  id: string;
  canonical_url: string;
  title: string;
  description?: string;
  content?: string;
  publisher: string;
  source_type: 'rss' | 'gdelt';
  category: string;
  published_at?: string;
  ingested_at: string;
  verified_verdict?: VerdictType;
  verification_summary?: string;
  is_new?: boolean;
}

export interface NewsListResponse {
  total: number;
  limit: number;
  offset: number;
  articles: NewsArticle[];
}

export interface NewsSource {
  id: string;
  name: string;
  feed_url: string;
  source_type: string;
  category: string;
  is_active: boolean;
  last_fetched_at?: string;
  last_status?: string;
}

export interface NewsSourcesResponse {
  sources: NewsSource[];
}

export interface NewsRefreshResponse {
  status: string;
  articles_fetched: number;
  new_articles_saved: number;
  duplicates_skipped: number;
  sources_contacted: number;
  sources_succeeded: number;
  errors: string[];
  refreshed_at: string;
  gdelt_usage?: GdeltUsageStatus | null;
}

export interface CanonicalVerificationRecord {
  schema_version: string;
  verification_id: string;
  original_content_hash: string;
  primary_verdict: string;
  confidence_score: number;
  evidence_hashes: string[];
  timestamp: string;
}

export interface VerificationHashSummary {
  schema_version: string;
  verification_id: string;
  canonical_record: CanonicalVerificationRecord;
  canonical_json: string;
  record_hash: string;
  record_hash_bytes32: string;
  blockchain_anchored: boolean;
  network?: string;
  transaction_hash?: string;
  contract_address?: string;
}

export interface BlockchainStatus {
  enabled: boolean;
  connected: boolean;
  network: string;
  chain_id?: number | null;
  contract_address?: string | null;
  contract_deployed: boolean;
  is_paused?: boolean | null;
  owner?: string | null;
  total_verifications?: number | null;
  latest_block?: number | null;
  rpc_endpoint_configured: boolean;
  epistemological_disclaimer: string;
}

export interface AnchorRequest {
  verification_id: string;
  record_hash: string;
  canonical_record?: CanonicalVerificationRecord;
}

export interface AnchorResponse {
  success: boolean;
  verification_id: string;
  record_hash: string;
  transaction_hash?: string | null;
  contract_address: string;
  block_number?: number | null;
  block_timestamp?: number | null;
  block_datetime?: string | null;
  submitter_address?: string | null;
  gas_used?: number | null;
  network: string;
  chain_id: number;
  etherscan_url?: string | null;
  already_registered: boolean;
  message: string;
  epistemological_disclaimer: string;
}

export interface OnChainRecordDetails {
  verification_id: string;
  record_hash: string;
  record_hash_bytes32: string;
  submitter: string;
  block_timestamp: number;
  block_datetime: string;
  is_registered: boolean;
}

export interface VerifyHashResponse {
  verification_id: string;
  is_registered_on_chain: boolean;
  hash_matched?: boolean | null;
  on_chain_record?: OnChainRecordDetails | null;
  network: string;
  contract_address?: string | null;
  integrity_status: string;
  explanation: string;
}

