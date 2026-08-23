"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, formatPercent, formatScore } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { BenchmarkResult, GrowthAdvisorResult, SlaAdvisorResult, TrustComponents, TrustMirrorResult, TrustWeights, WhatIfResult } from "@/lib/types";
import { DEFAULT_WEIGHTS } from "@/lib/weights";
import WeightSliders from "@/components/WeightSliders";
import ScoreBar from "@/components/ScoreBar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const COMPONENT_LABELS: Record<keyof TrustComponents, string> = {
  payment_trust: "Payment trust",
  promise_keeping: "Promise-keeping",
  price_fit: "Price competitiveness",
  reputation: "Reputation",
};

function toOverrides(weights: TrustWeights) {
  return {
    w_payment_trust: weights.payment_trust,
    w_promise_keeping: weights.promise_keeping,
    w_price_fit: weights.price_fit,
    w_reputation: weights.reputation,
  };
}

export default function MerchantDetailPage() {
  const params = useParams<{ id: string }>();
  const merchantId = params.id;

  const [weights, setWeights] = useState<TrustWeights>(DEFAULT_WEIGHTS);
  const [mirror, setMirror] = useState<TrustMirrorResult | null>(null);
  const [benchmark, setBenchmark] = useState<BenchmarkResult | null>(null);
  const [growth, setGrowth] = useState<GrowthAdvisorResult | null>(null);
  const [sla, setSla] = useState<SlaAdvisorResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
      Promise.all([
        api.getTrustMirror(merchantId, toOverrides(weights)),
        api.getBenchmark(merchantId, toOverrides(weights)),
        api.getGrowthAdvisor(merchantId, toOverrides(weights)),
      ])
        .then(([m, b, g]) => {
          setMirror(m);
          setBenchmark(b);
          setGrowth(g);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [merchantId, weights]);

  useEffect(() => {
    api.getSlaAdvisor(merchantId).then(setSla).catch(() => {});
  }, [merchantId]);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Trust Mirror</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Exactly what the Buyer Agent sees for this merchant, plus its position against the category and a ranked fix list.
      </p>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error} — is the backend running and the database seeded?
        </div>
      )}

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Weights</CardTitle>
        </CardHeader>
        <CardContent>
          <WeightSliders weights={weights} onChange={setWeights} />
        </CardContent>
      </Card>

      <Tabs defaultValue="mirror" className="mt-6">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="mirror">Trust Mirror</TabsTrigger>
          <TabsTrigger value="benchmark">Benchmark</TabsTrigger>
          <TabsTrigger value="growth">Growth Advisor</TabsTrigger>
          <TabsTrigger value="sla">SLA Advisor</TabsTrigger>
          <TabsTrigger value="readiness">Readiness</TabsTrigger>
        </TabsList>

        <TabsContent value="mirror">
          {mirror ? (
            <Card>
              <CardHeader>
                <div className="flex items-baseline justify-between">
                  <CardTitle>
                    Composite score {loading && <span className="font-normal text-muted-foreground">(recomputing…)</span>}
                  </CardTitle>
                  <span className="text-lg font-semibold tabular-nums">{formatScore(mirror.composite_score)}</span>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {(Object.keys(COMPONENT_LABELS) as (keyof TrustComponents)[]).map((key) => (
                    <ScoreBar key={key} label={COMPONENT_LABELS[key]} value={mirror.components[key]} />
                  ))}
                </div>
                <p className="mt-3 text-xs text-muted-foreground">
                  Weakest signal: <span className="font-medium text-foreground">{COMPONENT_LABELS[mirror.weakest_signal]}</span> · Strongest:{" "}
                  <span className="font-medium text-foreground">{COMPONENT_LABELS[mirror.strongest_signal]}</span>
                </p>
              </CardContent>
            </Card>
          ) : (
            <Skeleton className="h-40" />
          )}
        </TabsContent>

        <TabsContent value="benchmark">
          {benchmark ? (
            <Card>
              <CardHeader>
                <CardTitle>Benchmark</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">
                  Rank <span className="font-medium">{benchmark.rank}</span> of {benchmark.total_in_category} in category ·
                  category median {formatScore(benchmark.category_median_score)} · gap{" "}
                  <span className={benchmark.gap_to_median !== null && benchmark.gap_to_median < 0 ? "text-destructive" : "text-emerald-600 dark:text-emerald-400"}>
                    {benchmark.gap_to_median !== null ? formatScore(benchmark.gap_to_median) : "n/a"}
                  </span>
                </p>
              </CardContent>
            </Card>
          ) : (
            <Skeleton className="h-20" />
          )}
        </TabsContent>

        <TabsContent value="growth">
          {growth ? (
            <Card>
              <CardHeader>
                <CardTitle>Growth Advisor</CardTitle>
              </CardHeader>
              <CardContent>
                {growth.fixes.length === 0 ? (
                  <p className="text-sm text-emerald-600 dark:text-emerald-400">No component sits below the category median — nothing to fix.</p>
                ) : (
                  <ul className="flex flex-col gap-3">
                    {growth.fixes.map((fix) => (
                      <li key={fix.component} className="rounded-md border bg-muted/50 p-3 text-sm">
                        <div className="flex items-baseline justify-between">
                          <span className="font-medium">{COMPONENT_LABELS[fix.component]}</span>
                          <span className="text-xs text-muted-foreground">
                            {formatScore(fix.merchant_value)} vs median {formatScore(fix.category_median)} · impact {formatScore(fix.impact)}
                          </span>
                        </div>
                        <p className="mt-1 text-muted-foreground">{fix.message}</p>
                      </li>
                    ))}
                  </ul>
                )}
                {growth.fixes.length > 0 && <WhatIfSimulator merchantId={merchantId} weights={weights} fixes={growth.fixes} />}
              </CardContent>
            </Card>
          ) : (
            <Skeleton className="h-32" />
          )}
        </TabsContent>

        <TabsContent value="sla">
          {sla ? (
            <Card>
              <CardHeader>
                <CardTitle>SLA Advisor</CardTitle>
              </CardHeader>
              <CardContent>
                {sla.assessment === "insufficient_data" ? (
                  <p className="text-sm text-muted-foreground">Not enough COD history yet to recommend an SLA.</p>
                ) : (
                  <>
                    <p className="text-sm">
                      Declares <span className="font-medium">{sla.current_declared_sla_days}d</span>, recommend{" "}
                      <span className="font-medium">{sla.recommended_sla_days}d</span> based on{" "}
                      {sla.sample_size} historical COD deliveries (median actual {sla.median_actual_delivery_days}d).
                    </p>
                    <p className="mt-2 flex items-center gap-2 text-sm">
                      <AssessmentBadge assessment={sla.assessment} />
                      <span className="text-muted-foreground">
                        violation rate {sla.current_violation_rate !== undefined ? formatPercent(sla.current_violation_rate) : "n/a"} at
                        current declaration, {sla.projected_violation_rate !== undefined ? formatPercent(sla.projected_violation_rate) : "n/a"}{" "}
                        at recommended.
                      </span>
                    </p>
                  </>
                )}
              </CardContent>
            </Card>
          ) : (
            <Skeleton className="h-24" />
          )}
        </TabsContent>

        <TabsContent value="readiness">
          <ReadinessChecker merchantId={merchantId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function AssessmentBadge({ assessment }: { assessment: SlaAdvisorResult["assessment"] }) {
  const styles: Record<string, string> = {
    over_promising: "bg-red-500/10 text-red-600 dark:text-red-400",
    under_promising: "bg-amber-500/10 text-amber-600 dark:text-amber-400",
    well_calibrated: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    insufficient_data: "bg-muted text-muted-foreground",
  };
  const text: Record<string, string> = {
    over_promising: "Over-promising",
    under_promising: "Under-promising",
    well_calibrated: "Well-calibrated",
    insufficient_data: "Insufficient data",
  };
  return <Badge variant="outline" className={cn("border-transparent", styles[assessment])}>{text[assessment]}</Badge>;
}

function WhatIfSimulator({
  merchantId,
  weights,
  fixes,
}: {
  merchantId: string;
  weights: TrustWeights;
  fixes: GrowthAdvisorResult["fixes"];
}) {
  const [component, setComponent] = useState<keyof TrustComponents>(fixes[0]?.component ?? "payment_trust");
  const [targetValue, setTargetValue] = useState(fixes[0]?.category_median ?? 0.7);
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function simulate() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.postWhatIf(merchantId, component, targetValue, toOverrides(weights));
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-4 rounded-md border border-primary/20 bg-accent p-3">
      <h3 className="text-sm font-semibold text-accent-foreground">What-if simulator</h3>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <select
          value={component}
          onChange={(e) => setComponent(e.target.value as keyof TrustComponents)}
          className="h-8 rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {fixes.map((f) => (
            <option key={f.component} value={f.component}>
              {COMPONENT_LABELS[f.component]}
            </option>
          ))}
        </select>
        <span className="text-muted-foreground">→ target</span>
        <Input
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={targetValue}
          onChange={(e) => setTargetValue(Number(e.target.value))}
          className="w-20"
        />
        <Button onClick={simulate} disabled={loading} size="sm">
          {loading ? "Simulating…" : "Simulate"}
        </Button>
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
      {result && (
        <p className="mt-2 text-sm">
          Rank <span className="font-medium">{result.before_rank}</span> → <span className="font-medium">{result.after_rank}</span> of{" "}
          {result.total_in_category} (score {formatScore(result.before_score)} → {formatScore(result.after_score)})
        </p>
      )}
    </div>
  );
}

function ReadinessChecker({ merchantId }: { merchantId: string }) {
  const [raw, setRaw] = useState(
    "Amazing wireless earbuds!! Best sound ever, you'll love them.\nGreat quality product, everyone loves it, buy now!!"
  );
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.postReadiness>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    setLoading(true);
    setError(null);
    try {
      const items = raw.split("\n").map((s) => s.trim()).filter(Boolean);
      const res = await api.postReadiness(merchantId, items);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Readiness Agent — catalog check</CardTitle>
        <p className="text-xs text-muted-foreground">Paste one raw, marketing-style catalog line per item.</p>
      </CardHeader>
      <CardContent>
        <Textarea rows={3} value={raw} onChange={(e) => setRaw(e.target.value)} />
        <Button onClick={check} disabled={loading} variant="secondary" size="sm" className="mt-2">
          {loading ? "Checking…" : "Check readiness"}
        </Button>
        {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
        {result && (
          <div className="mt-3 flex flex-col gap-2">
            <p className="text-sm">
              Overall readiness: <span className="font-medium">{formatScore(result.overall_readiness_score)}</span>
            </p>
            {result.items.map((item, idx) => (
              <div key={idx} className="rounded-md border bg-muted/50 p-2 text-xs">
                <p>{item.raw_text}</p>
                {item.gaps.length > 0 ? (
                  <p className="mt-1 text-amber-600 dark:text-amber-400">Gaps: {item.gaps.join("; ")}</p>
                ) : (
                  <p className="mt-1 text-emerald-600 dark:text-emerald-400">Fully structured.</p>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
