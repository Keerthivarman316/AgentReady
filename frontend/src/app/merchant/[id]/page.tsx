"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, formatPercent, formatScore } from "@/lib/api";
import type { BenchmarkResult, GrowthAdvisorResult, SlaAdvisorResult, TrustComponents, TrustMirrorResult, TrustWeights, WhatIfResult } from "@/lib/types";
import { DEFAULT_WEIGHTS } from "@/lib/weights";
import WeightSliders from "@/components/WeightSliders";
import ScoreBar from "@/components/ScoreBar";

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
      <h1 className="text-2xl font-semibold text-gray-900">Trust Mirror</h1>
      <p className="mt-1 text-sm text-gray-600">
        Exactly what the Buyer Agent sees for this merchant, plus its position against the category and a ranked fix list.
      </p>

      {error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error} — is the backend running and the database seeded?
        </div>
      )}

      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-gray-900">Weights</h2>
        <div className="mt-3">
          <WeightSliders weights={weights} onChange={setWeights} />
        </div>
      </section>

      {mirror && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-gray-900">Composite score {loading && <span className="text-gray-400">(recomputing…)</span>}</h2>
            <span className="text-lg font-semibold tabular-nums text-gray-900">{formatScore(mirror.composite_score)}</span>
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(Object.keys(COMPONENT_LABELS) as (keyof TrustComponents)[]).map((key) => (
              <ScoreBar key={key} label={COMPONENT_LABELS[key]} value={mirror.components[key]} />
            ))}
          </div>
          <p className="mt-3 text-xs text-gray-500">
            Weakest signal: <span className="font-medium">{COMPONENT_LABELS[mirror.weakest_signal]}</span> · Strongest:{" "}
            <span className="font-medium">{COMPONENT_LABELS[mirror.strongest_signal]}</span>
          </p>
        </section>
      )}

      {benchmark && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">Benchmark</h2>
          <p className="mt-2 text-sm text-gray-700">
            Rank <span className="font-medium">{benchmark.rank}</span> of {benchmark.total_in_category} in category ·
            category median {formatScore(benchmark.category_median_score)} · gap{" "}
            <span className={benchmark.gap_to_median !== null && benchmark.gap_to_median < 0 ? "text-red-600" : "text-emerald-600"}>
              {benchmark.gap_to_median !== null ? formatScore(benchmark.gap_to_median) : "n/a"}
            </span>
          </p>
        </section>
      )}

      {growth && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">Growth Advisor</h2>
          {growth.fixes.length === 0 ? (
            <p className="mt-2 text-sm text-emerald-700">No component sits below the category median — nothing to fix.</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-3">
              {growth.fixes.map((fix) => (
                <li key={fix.component} className="rounded-md border border-gray-100 bg-gray-50 p-3 text-sm">
                  <div className="flex items-baseline justify-between">
                    <span className="font-medium text-gray-900">{COMPONENT_LABELS[fix.component]}</span>
                    <span className="text-xs text-gray-500">
                      {formatScore(fix.merchant_value)} vs median {formatScore(fix.category_median)} · impact {formatScore(fix.impact)}
                    </span>
                  </div>
                  <p className="mt-1 text-gray-600">{fix.message}</p>
                </li>
              ))}
            </ul>
          )}
          {growth.fixes.length > 0 && <WhatIfSimulator merchantId={merchantId} weights={weights} fixes={growth.fixes} />}
        </section>
      )}

      {sla && (
        <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-gray-900">SLA Advisor</h2>
          {sla.assessment === "insufficient_data" ? (
            <p className="mt-2 text-sm text-gray-500">Not enough COD history yet to recommend an SLA.</p>
          ) : (
            <>
              <p className="mt-2 text-sm text-gray-700">
                Declares <span className="font-medium">{sla.current_declared_sla_days}d</span>, recommend{" "}
                <span className="font-medium">{sla.recommended_sla_days}d</span> based on{" "}
                {sla.sample_size} historical COD deliveries (median actual {sla.median_actual_delivery_days}d).
              </p>
              <p className="mt-1 text-sm">
                <AssessmentBadge assessment={sla.assessment} />
                <span className="ml-2 text-gray-500">
                  violation rate {sla.current_violation_rate !== undefined ? formatPercent(sla.current_violation_rate) : "n/a"} at
                  current declaration, {sla.projected_violation_rate !== undefined ? formatPercent(sla.projected_violation_rate) : "n/a"}{" "}
                  at recommended.
                </span>
              </p>
            </>
          )}
        </section>
      )}

      <ReadinessChecker merchantId={merchantId} />
    </div>
  );
}

function AssessmentBadge({ assessment }: { assessment: SlaAdvisorResult["assessment"] }) {
  const styles: Record<string, string> = {
    over_promising: "bg-red-100 text-red-700",
    under_promising: "bg-amber-100 text-amber-700",
    well_calibrated: "bg-emerald-100 text-emerald-700",
    insufficient_data: "bg-gray-100 text-gray-600",
  };
  const text: Record<string, string> = {
    over_promising: "Over-promising",
    under_promising: "Under-promising",
    well_calibrated: "Well-calibrated",
    insufficient_data: "Insufficient data",
  };
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[assessment]}`}>{text[assessment]}</span>;
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
    <div className="mt-4 rounded-md border border-indigo-100 bg-indigo-50 p-3">
      <h3 className="text-sm font-semibold text-indigo-900">What-if simulator</h3>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <select
          value={component}
          onChange={(e) => setComponent(e.target.value as keyof TrustComponents)}
          className="rounded-md border border-gray-300 px-2 py-1"
        >
          {fixes.map((f) => (
            <option key={f.component} value={f.component}>
              {COMPONENT_LABELS[f.component]}
            </option>
          ))}
        </select>
        <span className="text-gray-500">→ target</span>
        <input
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={targetValue}
          onChange={(e) => setTargetValue(Number(e.target.value))}
          className="w-20 rounded-md border border-gray-300 px-2 py-1"
        />
        <button
          onClick={simulate}
          disabled={loading}
          className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Simulating…" : "Simulate"}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
      {result && (
        <p className="mt-2 text-sm text-indigo-900">
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
    <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-gray-900">Readiness Agent — catalog check</h2>
      <p className="mt-1 text-xs text-gray-500">Paste one raw, marketing-style catalog line per item.</p>
      <textarea
        className="mt-2 w-full rounded-md border border-gray-300 p-2 text-sm"
        rows={3}
        value={raw}
        onChange={(e) => setRaw(e.target.value)}
      />
      <button
        onClick={check}
        disabled={loading}
        className="mt-2 rounded-md bg-gray-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-900 disabled:opacity-50"
      >
        {loading ? "Checking…" : "Check readiness"}
      </button>
      {error && <p className="mt-2 text-xs text-red-700">{error}</p>}
      {result && (
        <div className="mt-3 flex flex-col gap-2">
          <p className="text-sm text-gray-700">
            Overall readiness: <span className="font-medium">{formatScore(result.overall_readiness_score)}</span>
          </p>
          {result.items.map((item, idx) => (
            <div key={idx} className="rounded-md border border-gray-100 bg-gray-50 p-2 text-xs">
              <p className="text-gray-700">{item.raw_text}</p>
              {item.gaps.length > 0 ? (
                <p className="mt-1 text-amber-700">Gaps: {item.gaps.join("; ")}</p>
              ) : (
                <p className="mt-1 text-emerald-700">Fully structured.</p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
