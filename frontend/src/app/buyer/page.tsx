"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ShoppingBag, FlaskConical } from "lucide-react";
import { api, formatPaise, formatScore } from "@/lib/api";
import type { CheckoutResult, DecisionResult, IntentResult, RankedCandidate, TrustWeights } from "@/lib/types";
import { DEFAULT_WEIGHTS } from "@/lib/weights";
import WeightSliders from "@/components/WeightSliders";
import ScoreBar from "@/components/ScoreBar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

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
      if (result.checkout?.status === "success") {
        toast.success(`Purchased at rank ${(result.checkout.rank ?? 0) + 1}`, {
          description: (result.checkout.rank ?? 0) > 0 ? "Top choice failed — agent fell back automatically." : undefined,
        });
      } else if (result.checkout) {
        toast.error(`Checkout exhausted all ${result.checkout.attempted} candidates`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(null);
    }
  }

  async function buyProduct(productId: string, productName: string) {
    if (!mandate) return;
    setBuyingProductId(productId);
    setError(null);
    try {
      const result = await api.purchase(mandate.mandate_id, toOverrides(weights), undefined, productId);
      setProductCheckouts((prev) => ({ ...prev, [productId]: result.checkout }));
      if (result.checkout?.status === "success") {
        toast.success(`Purchased ${productName}`, { description: `Order ${result.checkout.order?.id}` });
      } else {
        toast.error(`Checkout failed for ${productName}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuyingProductId(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
        <ShoppingBag className="size-6 text-primary" />
        Buyer Agent
      </h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Intent Agent issues a signed mandate; the Buyer Agent ranks candidates through
        hard constraints, weighted heuristics, and a real-time price tie-break — then
        checks out, falling back automatically if the top choice fails.
      </p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Goal</CardTitle>
        </CardHeader>
        <CardContent>
          <Textarea rows={2} value={goalText} onChange={(e) => setGoalText(e.target.value)} />
          <Button onClick={submitIntent} disabled={loading === "intent"} className="mt-3">
            {loading === "intent" ? "Issuing mandate…" : "Issue mandate"}
          </Button>
        </CardContent>
      </Card>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {mandate && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Mandate</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4">
              <dt className="text-muted-foreground">Budget cap</dt>
              <dd className="text-foreground">{formatPaise(mandate.budget_cap_paise)}</dd>
              <dt className="text-muted-foreground">Deadline</dt>
              <dd className="text-foreground">{mandate.deadline_days}d</dd>
              <dt className="text-muted-foreground">Issued</dt>
              <dd className="text-foreground">{new Date(mandate.issued_at).toLocaleTimeString()}</dd>
              <dt className="text-muted-foreground">Expires</dt>
              <dd className="text-foreground">{new Date(mandate.expires_at).toLocaleTimeString()}</dd>
            </dl>
            <p className="mt-2 truncate text-xs text-muted-foreground/70" title={mandate.mandate_hash}>
              hash: {mandate.mandate_hash}
            </p>
            <Link href={`/audit?mandate_id=${mandate.mandate_id}`} className="mt-2 inline-block text-xs text-primary hover:underline">
              View full audit trail →
            </Link>
          </CardContent>
        </Card>
      )}

      {mandate && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Weights (layer 2: learned heuristics)</CardTitle>
          </CardHeader>
          <CardContent>
            <WeightSliders weights={weights} onChange={previewRanking} />
          </CardContent>
        </Card>
      )}

      {decision && (
        <Card className="mt-6">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>
                Ranking {loading === "preview" && <span className="font-normal text-muted-foreground">(recomputing…)</span>}
              </CardTitle>
              {decision.status === "ranked" && (
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-1.5 rounded-md border border-dashed px-2 py-1 text-xs text-muted-foreground">
                    <FlaskConical className="size-3.5" />
                    <input
                      type="checkbox"
                      checked={simulateTopFailure}
                      onChange={(e) => setSimulateTopFailure(e.target.checked)}
                    />
                    Simulate top-choice failure
                  </label>
                  <Button onClick={confirmPurchase} disabled={loading === "purchase"} size="sm">
                    {loading === "purchase" ? "Checking out…" : "Confirm purchase"}
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {decision.status === "no_candidates" ? (
              <p className="text-sm text-muted-foreground">No candidates survive the hard constraints for this mandate.</p>
            ) : (
              <div className="flex flex-col gap-3">
                {decision.ranking.map((candidate, idx) => (
                  <CandidateCard
                    key={candidate.product_id}
                    candidate={candidate}
                    rank={idx + 1}
                    onBuy={() => buyProduct(candidate.product_id, candidate.product_name)}
                    buying={buyingProductId === candidate.product_id}
                    result={productCheckouts[candidate.product_id]}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {checkout && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Checkout</CardTitle>
          </CardHeader>
          <CardContent>
            {checkout.status === "success" ? (
              <p className="text-sm text-emerald-600 dark:text-emerald-400">
                Success at rank {(checkout.rank ?? 0) + 1} — order {checkout.order?.id}.
                {(checkout.rank ?? 0) > 0 && " The top choice failed and the agent fell back automatically — see the audit trail."}
              </p>
            ) : (
              <p className="text-sm text-destructive">
                Exhausted all {checkout.attempted} candidates — none completed checkout.
              </p>
            )}
          </CardContent>
        </Card>
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
    <div className="rounded-lg border p-3">
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-center gap-2 text-sm font-medium">
          {rank === 1 && <Badge>Top pick</Badge>}
          <span className="text-muted-foreground">#{rank}</span>
          {candidate.merchant_name} — {candidate.product_name}
        </span>
        <span className="shrink-0 text-sm text-muted-foreground">
          {formatPaise(candidate.live_price_paise ?? candidate.price_paise)}
          {candidate.composite_score !== undefined && (
            <span className="ml-2 tabular-nums text-muted-foreground/70">score {formatScore(candidate.composite_score)}</span>
          )}
        </span>
      </div>
      {candidate.trust_components && (
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <ScoreBar label="Payment" value={candidate.trust_components.payment_trust} />
          <ScoreBar label="Promise" value={candidate.trust_components.promise_keeping} />
          <ScoreBar label="Price" value={candidate.trust_components.price_fit} />
          <ScoreBar label="Reputation" value={candidate.trust_components.reputation} />
        </div>
      )}
      <div className="mt-3 flex items-center justify-between">
        <Button onClick={onBuy} disabled={buying} variant="outline" size="sm">
          {buying ? "Buying…" : "Buy this"}
        </Button>
        {result && (
          <span className={result.status === "success" ? "text-xs text-emerald-600 dark:text-emerald-400" : "text-xs text-destructive"}>
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
