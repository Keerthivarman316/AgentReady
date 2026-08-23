export interface Merchant {
  id: string;
  name: string;
  category: string;
  declared_sla_days: number;
}

export interface TrustComponents {
  payment_trust: number;
  promise_keeping: number;
  price_fit: number;
  reputation: number;
}

export interface TrustWeights {
  payment_trust: number;
  promise_keeping: number;
  price_fit: number;
  reputation: number;
}

export interface TrustIntegrityResult {
  flagged: boolean;
  reputation: number;
  operational_average: number;
  gap: number;
  reason: string | null;
}

export interface TrustScoreResult {
  merchant_id: string;
  product_id: string | null;
  components: TrustComponents;
  weights: TrustWeights;
  composite_score: number;
  integrity: TrustIntegrityResult;
}

export interface TrustMirrorResult extends TrustScoreResult {
  contributions: TrustComponents;
  weakest_signal: keyof TrustComponents;
  strongest_signal: keyof TrustComponents;
}

export interface BenchmarkResult {
  merchant_id: string;
  composite_score: number | null;
  components: TrustComponents | null;
  category_median_score: number;
  gap_to_median: number | null;
  rank: number | null;
  total_in_category: number;
  component_medians: TrustComponents;
}

export interface GrowthFix {
  component: keyof TrustComponents;
  merchant_value: number;
  category_median: number;
  gap: number;
  impact: number;
  message: string;
}

export interface GrowthAdvisorResult {
  benchmark: BenchmarkResult;
  fixes: GrowthFix[];
}

export interface WhatIfResult {
  merchant_id: string;
  component: string;
  target_value: number;
  before_rank: number;
  after_rank: number;
  before_score: number;
  after_score: number;
  total_in_category: number;
}

export interface LostSaleSignalResult {
  sample_size: number;
  reason_breakdown: Record<string, number>;
}

export interface SlaAdvisorResult {
  current_declared_sla_days: number;
  recommended_sla_days: number;
  median_actual_delivery_days?: number;
  current_violation_rate?: number;
  projected_violation_rate?: number;
  assessment: "over_promising" | "under_promising" | "well_calibrated" | "insufficient_data";
  sample_size: number;
}

export interface ReadinessCheckItem {
  raw_text: string;
  extracted_price_paise: number | null;
  extracted_category: string | null;
  checks: { has_price: boolean; has_category: boolean; description_length_ok: boolean };
  readiness_score: number;
  gaps: string[];
}

export interface ReadinessResult {
  items: ReadinessCheckItem[];
  overall_readiness_score: number;
  item_count: number;
}

export interface IntentResult {
  mandate_id: string;
  category_id: string;
  budget_cap_paise: number;
  deadline_days: number;
  mandate_hash: string;
  issued_at: string;
  expires_at: string;
}

export interface RankedCandidate {
  product_id: string;
  merchant_id: string;
  merchant_name: string;
  product_name: string;
  price_paise: number;
  declared_sla_days: number;
  composite_score?: number;
  trust_components?: TrustComponents;
  weights_used?: TrustWeights;
  live_price_paise?: number;
  countered?: boolean;
  countered_against?: boolean;
}

export interface CounterOffer {
  merchant_id: string;
  merchant_name: string;
  product_id: string;
  product_name: string;
  original_price_paise: number;
  countered_price_paise: number;
  discount_pct: number;
  new_composite_score: number;
}

export interface DecisionResult {
  status: "ranked" | "no_candidates";
  ranking: RankedCandidate[];
  quarantined_count?: number;
  counter_offer?: CounterOffer | null;
}

export interface CheckoutResult {
  status: "success" | "exhausted";
  rank?: number;
  merchant_id?: string;
  product_id?: string;
  order?: { id: string; simulated?: boolean };
  attempted?: number;
}

export interface PurchaseResult {
  mandate_id: string;
  decision: DecisionResult;
  checkout: CheckoutResult | null;
}

export interface AuditEntry {
  layer: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface WeightOverrides {
  w_payment_trust?: number;
  w_promise_keeping?: number;
  w_price_fit?: number;
  w_reputation?: number;
}
