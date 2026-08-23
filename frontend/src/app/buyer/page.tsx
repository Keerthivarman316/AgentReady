"use client";

import { useState } from "react";
import Link from "next/link";
import { api, formatPaise, formatScore } from "@/lib/api";
import type { CheckoutResult, DecisionResult, IntentResult, RankedCandidate, TrustWeights } from "@/lib/types";
import { DEFAULT_WEIGHTS } from "@/lib/weights";
import WeightSliders from "@/components/WeightSliders";
import ScoreBar from "@/components/ScoreBar";

export default function BuyerPage() {
  const [consumerId] = useState("demo-consumer");
  const [goalText, setGoalText] = useState("wireless earbuds under 2000 within 3 days");
  const [mandate, setMandate] = useState<IntentResult | null>(null);
  const [weights, setWeights] = useState<TrustWeights>(DEFAULT_WEIGHTS);
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [checkout, setCheckout] = useState<CheckoutResult | null>(null);
  const [loading, setLoading] = useState<"intent" | "preview" | "purchase" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [simulateTopFailure, setSimulateTopFailure] = useState(false);
  const [buyingProductId, setBuyingProductId] = useState<string | null>(null);
  const [productCheckouts, setProductCheckouts] = useState<Record<string, CheckoutResult | null>>({});

  async function submitIntent() {
    setLoading("intent");
    setError(null);
    try {
      const result = await api.createIntent(consumerId, goalText);
      setMandate(result);
      setDecision(null);
      setCheckout(null);
      setProductCheckouts({});
      const preview = await api.rankPreview(result.mandate_id, toOverrides(weights));
      setDecision(preview.decision);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  async function previewRanking(nextWeights: TrustWeights) {
    setWeights(nextWeights);
    if (!mandate) return;
    setLoading("preview");
    setError(null);
    try {
      const preview = await api.rankPreview(mandate.mandate_id, toOverrides(nextWeights));
      setDecision(preview.decision);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  async function confirmPurchase() {
    if (!mandate) return;
    setLoading("purchase");
    setError(null);
    try {
      const result = await api.purchase(mandate.mandate_id, toOverrides(weights), simulateTopFailure ? 0 : undefined);
      setDecision(result.decision);
      setCheckout(result.checkout);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  async function buyProduct(productId: string) {
    if (!mandate) return;
    setBuyingProductId(productId);
    setError(null);
    try {
      const result = await api.purchase(mandate.mandate_id, toOverrides(weights), undefined, productId);
      setProductCheckouts((prev) => ({ ...prev, [productId]: result.checkout }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuyingProductId(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold text-gray-900">Buyer Agent</h1>
      <p className="mt-1 text-sm text-gray-600">
        Intent Agent issues a signed mandate; the Buyer Agent ranks candidates through
        hard constraints, weighted heuristics, and a real-time price tie-break — then
        checks out, falling back automatically if the top choice fails.
      </p>

      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
        <label className="block text-sm font-medium text-gray-700">Goal</label>
        <textarea
          className="mt-2 w-full rounded-md border border-gray-300 p-2 text-sm"
          rows={2}
          value={goalText}
          onChange={(e) => setGoalText(e.target.value)}
        />
        <button
          onClick={submitIntent}
          disabled={loading === "intent"}
          className="mt-3 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading === "intent" ? "Issuing mandate…" : "Issue mandate"}
        </button>
      </section>

      {error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {mandate && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">Mandate</h2>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
            <dt className="text-gray-500">Budget cap</dt>
            <dd className="text-gray-900">{formatPaise(mandate.budget_cap_paise)}</dd>
            <dt className="text-gray-500">Deadline</dt>
            <dd className="text-gray-900">{mandate.deadline_days}d</dd>
            <dt className="text-gray-500">Issued</dt>
            <dd className="text-gray-900">{new Date(mandate.issued_at).toLocaleTimeString()}</dd>
            <dt className="text-gray-500">Expires</dt>
            <dd className="text-gray-900">{new Date(mandate.expires_at).toLocaleTimeString()}</dd>
          </dl>
          <p className="mt-2 truncate text-xs text-gray-400" title={mandate.mandate_hash}>
            hash: {mandate.mandate_hash}
          </p>
          <Link href={`/audit?mandate_id=${mandate.mandate_id}`} className="mt-2 inline-block text-xs text-indigo-600 hover:underline">
            View full audit trail →
          </Link>
        </section>
      )}

      {mandate && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">Weights (layer 2: learned heuristics)</h2>
          <div className="mt-3">
            <WeightSliders weights={weights} onChange={previewRanking} />
          </div>
        </section>
      )}

      {decision && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900">
              Ranking {loading === "preview" && <span className="text-gray-400">(recomputing…)</span>}
            </h2>
            {decision.status === "ranked" && (
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-1.5 text-xs text-gray-500">
                  <input
                    type="checkbox"
                    checked={simulateTopFailure}
                    onChange={(e) => setSimulateTopFailure(e.target.checked)}
                  />
                  Simulate top-choice failure
                </label>
                <button
                  onClick={confirmPurchase}
                  disabled={loading === "purchase"}
                  className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {loading === "purchase" ? "Checking out…" : "Confirm purchase"}
                </button>
              </div>
            )}
          </div>

          {decision.status === "no_candidates" ? (
            <p className="mt-3 text-sm text-gray-500">No candidates survive the hard constraints for this mandate.</p>
          ) : (
            <div className="mt-3 flex flex-col gap-3">
              {decision.ranking.map((candidate, idx) => (
                <CandidateCard
                  key={candidate.product_id}
                  candidate={candidate}
                  rank={idx + 1}
                  onBuy={() => buyProduct(candidate.product_id)}
                  buying={buyingProductId === candidate.product_id}
                  result={productCheckouts[candidate.product_id]}
                />
              ))}
            </div>
          )}
        </section>
      )}

      {checkout && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">Checkout</h2>
          {checkout.status === "success" ? (
            <p className="mt-2 text-sm text-emerald-700">
              Success at rank {(checkout.rank ?? 0) + 1} — order {checkout.order?.id}.
              {(checkout.rank ?? 0) > 0 && " The top choice failed and the agent fell back automatically — see the audit trail."}
            </p>
          ) : (
            <p className="mt-2 text-sm text-red-700">Exhausted all {checkout.attempted} candidates — none completed checkout.</p>
          )}
        </section>
      )}
    </div>
  );
}

function CandidateCard({
  candidate,
  rank,
  onBuy,
  buying,
  result,
}: {
  candidate: RankedCandidate;
  rank: number;
  onBuy: () => void;
  buying: boolean;
  result: CheckoutResult | null | undefined;
}) {
  return (
    <div className="rounded-md border border-gray-200 p-3">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-gray-900">
          #{rank} {candidate.merchant_name} — {candidate.product_name}
        </span>
        <span className="text-sm text-gray-500">
          {formatPaise(candidate.live_price_paise ?? candidate.price_paise)}
          {candidate.composite_score !== undefined && (
            <span className="ml-2 tabular-nums text-gray-400">score {formatScore(candidate.composite_score)}</span>
          )}
        </span>
      </div>
      {candidate.trust_components && (
        <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <ScoreBar label="Payment" value={candidate.trust_components.payment_trust} />
          <ScoreBar label="Promise" value={candidate.trust_components.promise_keeping} />
          <ScoreBar label="Price" value={candidate.trust_components.price_fit} />
          <ScoreBar label="Reputation" value={candidate.trust_components.reputation} />
        </div>
      )}
      <div className="mt-2 flex items-center justify-between">
        <button
          onClick={onBuy}
          disabled={buying}
          className="rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          {buying ? "Buying…" : "Buy this"}
        </button>
        {result && (
          <span className={result.status === "success" ? "text-xs text-emerald-700" : "text-xs text-red-700"}>
            {result.status === "success" ? `Purchased — order ${result.order?.id}` : "Checkout failed"}
          </span>
        )}
      </div>
    </div>
  );
}

function toOverrides(weights: TrustWeights) {
  return {
    w_payment_trust: weights.payment_trust,
    w_promise_keeping: weights.promise_keeping,
    w_price_fit: weights.price_fit,
    w_reputation: weights.reputation,
  };
}
