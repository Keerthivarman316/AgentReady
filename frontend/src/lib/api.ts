import type {
  AuditEntry,
  BenchmarkResult,
  DecisionResult,
  GrowthAdvisorResult,
  IntentResult,
  Merchant,
  PurchaseResult,
  ReadinessResult,
  SlaAdvisorResult,
  TrustMirrorResult,
  WeightOverrides,
  WhatIfResult,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json() as Promise<T>;
}

function weightsQuery(weights?: WeightOverrides): string {
  if (!weights) return "";
  const params = new URLSearchParams();
  if (weights.w_payment_trust !== undefined) params.set("w_payment_trust", String(weights.w_payment_trust));
  if (weights.w_promise_keeping !== undefined) params.set("w_promise_keeping", String(weights.w_promise_keeping));
  if (weights.w_price_fit !== undefined) params.set("w_price_fit", String(weights.w_price_fit));
  if (weights.w_reputation !== undefined) params.set("w_reputation", String(weights.w_reputation));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  listMerchants: () => apiFetch<Merchant[]>("/merchants"),

  createIntent: (consumer_id: string, goal_text: string) =>
    apiFetch<IntentResult>("/intent", { method: "POST", body: JSON.stringify({ consumer_id, goal_text }) }),

  rankPreview: (mandate_id: string, weights?: WeightOverrides) =>
    apiFetch<{ mandate_id: string; decision: DecisionResult }>("/buyer/rank-preview", {
      method: "POST",
      body: JSON.stringify({ mandate_id, ...weights }),
    }),

  purchase: (mandate_id: string, weights?: WeightOverrides, simulateFailureRank?: number) =>
    apiFetch<PurchaseResult>("/buyer/purchase", {
      method: "POST",
      body: JSON.stringify({ mandate_id, ...weights, simulate_failure_rank: simulateFailureRank ?? null }),
    }),

  getAuditTrail: (mandate_id: string) => apiFetch<AuditEntry[]>(`/audit/${mandate_id}`),

  getTrustMirror: (merchantId: string, weights?: WeightOverrides) =>
    apiFetch<TrustMirrorResult>(`/merchants/${merchantId}/trust-mirror${weightsQuery(weights)}`),

  getBenchmark: (merchantId: string, weights?: WeightOverrides) =>
    apiFetch<BenchmarkResult>(`/merchants/${merchantId}/benchmark${weightsQuery(weights)}`),

  getGrowthAdvisor: (merchantId: string, weights?: WeightOverrides) =>
    apiFetch<GrowthAdvisorResult>(`/merchants/${merchantId}/growth-advisor${weightsQuery(weights)}`),

  postWhatIf: (merchantId: string, component: string, target_value: number, weights?: WeightOverrides) =>
    apiFetch<WhatIfResult>(`/merchants/${merchantId}/growth-advisor/what-if`, {
      method: "POST",
      body: JSON.stringify({ component, target_value, ...weights }),
    }),

  getSlaAdvisor: (merchantId: string) => apiFetch<SlaAdvisorResult>(`/merchants/${merchantId}/sla-advisor`),

  postReadiness: (merchantId: string, items: string[]) =>
    apiFetch<ReadinessResult>(`/merchants/${merchantId}/readiness`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
};

export function formatPaise(paise: number): string {
  return `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function formatScore(score: number): string {
  return score.toFixed(3);
}

export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}
