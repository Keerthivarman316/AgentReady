"use client";

import type { TrustWeights } from "@/lib/types";

const LABELS: Record<keyof TrustWeights, string> = {
  payment_trust: "Payment trust",
  promise_keeping: "Promise-keeping",
  price_fit: "Price competitiveness",
  reputation: "Reputation",
};

const REPUTATION_CAP = 0.2;

export default function WeightSliders({
  weights,
  onChange,
}: {
  weights: TrustWeights;
  onChange: (weights: TrustWeights) => void;
}) {
  const update = (key: keyof TrustWeights, value: number) => {
    onChange({ ...weights, [key]: value });
  };

  return (
    <div className="flex flex-col gap-3">
      {(Object.keys(LABELS) as (keyof TrustWeights)[]).map((key) => (
        <div key={key} className="flex flex-col gap-1">
          <div className="flex items-baseline justify-between text-sm">
            <span className="text-gray-700">{LABELS[key]}</span>
            <span className="tabular-nums text-gray-500">
              {weights[key].toFixed(2)}
              {key === "reputation" ? <span className="ml-1 text-gray-400">(capped at {REPUTATION_CAP})</span> : null}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={weights[key]}
            onChange={(e) => update(key, Number(e.target.value))}
            className="w-full accent-indigo-600"
          />
        </div>
      ))}
      <p className="text-xs text-gray-400">
        Weights are renormalized server-side to sum to 1; reputation is hard-capped at {REPUTATION_CAP} no matter what you set here.
      </p>
    </div>
  );
}
