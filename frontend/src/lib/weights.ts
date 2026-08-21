import type { TrustWeights } from "./types";

// Mirrors backend/app/trust_engine.py DEFAULT_WEIGHTS.
export const DEFAULT_WEIGHTS: TrustWeights = {
  payment_trust: 0.35,
  promise_keeping: 0.3,
  price_fit: 0.2,
  reputation: 0.15,
};
