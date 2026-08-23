"use client";

import type { TrustWeights } from "@/lib/types";
import { Slider } from "@/components/ui/slider";

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
        <div key={key} className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between text-sm">
            <span className="text-foreground">{LABELS[key]}</span>
            <span className="tabular-nums text-muted-foreground">
              {weights[key].toFixed(2)}
              {key === "reputation" ? <span className="ml-1 text-muted-foreground/70">(capped at {REPUTATION_CAP})</span> : null}
            </span>
          </div>
          <Slider
            min={0}
            max={1}
            step={0.05}
            value={[weights[key]]}
            onValueChange={(value) => update(key, Array.isArray(value) ? value[0] : value)}
          />
        </div>
      ))}
      <p className="text-xs text-muted-foreground/70">
        Weights are renormalized server-side to sum to 1; reputation is hard-capped at {REPUTATION_CAP} no matter what you set here.
      </p>
    </div>
  );
}
