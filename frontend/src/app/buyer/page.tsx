"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { ShoppingBag, FlaskConical, ShieldAlert, Handshake } from "lucide-react";
import { api, formatPaise, formatScore } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  ChatFollowupResult,
  CheckoutResult,
  DecisionResult,
  IntentResult,
  RankedCandidate,
  TrustWeights,
} from "@/lib/types";
import { DEFAULT_WEIGHTS } from "@/lib/weights";
import WeightSliders from "@/components/WeightSliders";
import ScoreBar from "@/components/ScoreBar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

function describeUpdate(diff: ChatFollowupResult, decision: DecisionResult, productPhrase: string): string {
  const parts: string[] = [];
  if (diff.persona) parts.push(`Prioritizing like a ${diff.persona} buyer now.`);
  if (diff.budget_cap_paise) parts.push(`Budget set to ${formatPaise(diff.budget_cap_paise)}.`);
  if (diff.deadline_days) parts.push(`Deadline set to ${diff.deadline_days} day${diff.deadline_days === 1 ? "" : "s"}.`);
  if (diff.product_keywords?.length) parts.push(`Looking at ${productPhrase} now.`);

  if (decision.status === "ranked" && decision.ranking.length > 0) {
    const top = decision.ranking[0];
    parts.push(
      `Top pick: ${top.merchant_name} — ${top.product_name} at ${formatPaise(top.live_price_paise ?? top.price_paise)} (${decision.ranking.length} candidate${decision.ranking.length === 1 ? "" : "s"} ranked).`
    );
  } else if (decision.status === "no_candidates") {
    parts.push("No candidates survive those constraints — try loosening the budget or deadline.");
  }
  return parts.length ? parts.join(" ") : "Got it — didn't catch anything to change there.";
}

export default function BuyerPage() {
  const [consumerId] = useState("demo-consumer");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [productPhrase, setProductPhrase] = useState("");
  const [categoryHint, setCategoryHint] = useState("");
  const [budgetPaise, setBudgetPaise] = useState<number | null>(null);
  const [deadlineDays, setDeadlineDays] = useState(7);
  const [mandate, setMandate] = useState<IntentResult | null>(null);
  const [weights, setWeights] = useState<TrustWeights>(DEFAULT_WEIGHTS);
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [checkout, setCheckout] = useState<CheckoutResult | null>(null);
  const [loading, setLoading] = useState<"chat" | "preview" | "purchase" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [simulateTopFailure, setSimulateTopFailure] = useState(false);
  const [buyingProductId, setBuyingProductId] = useState<string | null>(null);
  const [productCheckouts, setProductCheckouts] = useState<Record<string, CheckoutResult | null>>({});
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function sendChatMessage() {
    const text = chatInput.trim();
    if (!text || loading === "chat") return;
    setChatInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading("chat");
    setError(null);

    try {
      const diff = await api.parseChatFollowup(text);
      const nextProductPhrase = diff.product_keywords?.length ? diff.product_keywords.join(" ") : productPhrase;
      const nextCategory = diff.category ?? categoryHint;
      const nextBudgetPaise = diff.budget_cap_paise ?? budgetPaise;
      const nextDeadlineDays = diff.deadline_days ?? deadlineDays;
      const nextWeights = diff.weights ?? weights;

      if (nextBudgetPaise === null) {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: 'I still need a budget to work with — try something like "under 2000 rupees".' },
        ]);
        return;
      }

      const productOrCategory = nextProductPhrase || nextCategory.toLowerCase();
      const goalText = `${productOrCategory} under ${nextBudgetPaise / 100} rupees within ${nextDeadlineDays} days`.trim();

      const result = await api.createIntent(consumerId, goalText);
      const preview = await api.rankPreview(result.mandate_id, toOverrides(nextWeights));

      setProductPhrase(nextProductPhrase);
      setCategoryHint(nextCategory);
      setBudgetPaise(nextBudgetPaise);
      setDeadlineDays(nextDeadlineDays);
      setWeights(nextWeights);
      setMandate(result);
      setDecision(preview.decision);
      setCheckout(null);
      setProductCheckouts({});

      setMessages((prev) => [...prev, { role: "assistant", text: describeUpdate(diff, preview.decision, nextProductPhrase) }]);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setMessages((prev) => [...prev, { role: "assistant", text: `Couldn't process that: ${msg}` }]);
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
        const fellBack = (result.checkout.rank ?? 0) > 0;
        const simulated = result.checkout.order?.simulated;
        toast.success(`Purchased at rank ${(result.checkout.rank ?? 0) + 1}`, {
          description: [
            fellBack && "Top choice failed — agent fell back automatically.",
            simulated && "Demo order (Razorpay not configured) — no real payment.",
          ]
            .filter(Boolean)
            .join(" ") || undefined,
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
        toast.success(`Purchased ${productName}`, {
          description: result.checkout.order?.simulated
            ? `Demo order ${result.checkout.order?.id} — Razorpay not configured, no real payment.`
            : `Order ${result.checkout.order?.id}`,
        });
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
        Tell the agent what you want, then redirect it anytime — the Intent Agent re-issues a mandate on
        every turn and the Buyer Agent re-ranks live through hard constraints, weighted heuristics, and a
        real-time price tie-break.
      </p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Chat</CardTitle>
        </CardHeader>
        <CardContent>
          <div ref={transcriptRef} className="flex max-h-80 flex-col gap-3 overflow-y-auto rounded-md border bg-muted/30 p-3">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Try &ldquo;wireless earbuds under 2000 within 3 days&rdquo;. You can redirect anytime —
                &ldquo;actually get me the cheapest one&rdquo;, &ldquo;I need it faster&rdquo;, &ldquo;how about
                headphones instead&rdquo;.
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={cn(
                  "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                  m.role === "user" ? "self-end bg-primary text-primary-foreground" : "self-start border bg-background"
                )}
              >
                {m.text}
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <Textarea
              rows={1}
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendChatMessage();
                }
              }}
              placeholder="wireless earbuds under 2000 within 3 days"
              className="min-h-9 resize-none"
            />
            <Button onClick={sendChatMessage} disabled={loading === "chat" || !chatInput.trim()}>
              {loading === "chat" ? "…" : "Send"}
            </Button>
          </div>
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
            <p className="text-xs text-muted-foreground">
              The chat can drive these too — say &ldquo;cheapest&rdquo;, &ldquo;most trusted&rdquo;, or
              &ldquo;fastest&rdquo; — or drag them directly.
            </p>
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
            {(decision.quarantined_count ?? 0) > 0 && (
              <p className="mb-3 flex items-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                <ShieldAlert className="size-3.5" />
                {decision.quarantined_count} merchant{decision.quarantined_count === 1 ? "" : "s"} excluded — reputation
                didn&apos;t match operational data.
              </p>
            )}
            {decision.counter_offer && (
              <p className="mb-3 flex items-center gap-1.5 text-xs text-primary">
                <Handshake className="size-3.5" />
                {decision.counter_offer.merchant_name} countered with {formatPaise(decision.counter_offer.countered_price_paise)}{" "}
                (was {formatPaise(decision.counter_offer.original_price_paise)}) to win this mandate — see audit trail.
              </p>
            )}
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
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm text-emerald-600 dark:text-emerald-400">
                  Success at rank {(checkout.rank ?? 0) + 1} — order {checkout.order?.id}.
                  {(checkout.rank ?? 0) > 0 && " The top choice failed and the agent fell back automatically — see the audit trail."}
                </p>
                {checkout.order?.simulated ? (
                  <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400">
                    Demo order — Razorpay not configured
                  </Badge>
                ) : (
                  <Badge
                    variant="outline"
                    className="border-primary/30 bg-primary/10 text-primary"
                    title={checkout.order?.settlement_note}
                  >
                    Payment Mandate authorized (Razorpay test mode)
                  </Badge>
                )}
              </div>
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
          {candidate.countered && (
            <Badge variant="outline" className="gap-1 border-primary/30 bg-primary/10 text-primary">
              <Handshake className="size-3" />
              Countered
            </Badge>
          )}
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
            {result.status === "success"
              ? `Purchased — ${result.order?.simulated ? "demo order" : "mandate authorized"} ${result.order?.id}`
              : "Checkout failed"}
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
