"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { AuditEntry } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

const LAYER_LABELS: Record<string, string> = {
  intent: "Intent",
  hard_constraints: "Hard constraints",
  heuristics: "Heuristics ranking",
  real_time_optimize: "Real-time optimization",
  checkout_attempt: "Checkout attempt",
  checkout_failure: "Checkout failure",
  checkout_fallback: "Checkout fallback",
  checkout_success: "Checkout success",
  checkout_exhausted: "Checkout exhausted",
  decision: "Decision",
};

const LAYER_STYLES: Record<string, string> = {
  checkout_failure: "border-red-500/30 bg-red-500/5",
  checkout_fallback: "border-amber-500/30 bg-amber-500/5",
  checkout_success: "border-emerald-500/30 bg-emerald-500/5",
};

function AuditTrailContent() {
  const searchParams = useSearchParams();
  const [mandateId, setMandateId] = useState(searchParams.get("mandate_id") ?? "");
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(id: string) {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const result = await api.getAuditTrail(id);
      setEntries(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const initialMandateId = searchParams.get("mandate_id");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial fetch on mount, not a render cascade
    if (initialMandateId) load(initialMandateId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount only
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Audit trail</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Every Buyer Agent decision layer and checkout attempt for a mandate, in order.
      </p>

      <div className="mt-6 flex gap-2">
        <Input
          value={mandateId}
          onChange={(e) => setMandateId(e.target.value)}
          placeholder="mandate id"
          className="h-auto flex-1 py-2"
        />
        <Button onClick={() => load(mandateId)} disabled={loading}>
          {loading ? "Loading…" : "Load"}
        </Button>
      </div>

      {error && (
        <div className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>
      )}

      {loading && !entries && (
        <div className="mt-6 flex flex-col gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-md" />
          ))}
        </div>
      )}

      {entries && entries.length === 0 && <p className="mt-6 text-sm text-muted-foreground">No audit entries for this mandate yet.</p>}

      {entries && entries.length > 0 && (
        <ol className="mt-6 flex flex-col gap-3">
          {entries.map((entry, idx) => (
            <li key={idx} className={cn("rounded-md border p-3", LAYER_STYLES[entry.layer])}>
              <div className="flex items-baseline justify-between">
                <span className="text-sm font-semibold">{LAYER_LABELS[entry.layer] ?? entry.layer}</span>
                <span className="text-xs text-muted-foreground">{new Date(entry.created_at).toLocaleTimeString()}</span>
              </div>
              <pre className="mt-2 overflow-x-auto rounded bg-foreground/5 p-2 text-xs text-muted-foreground">
                {JSON.stringify(entry.payload, null, 2)}
              </pre>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function AuditTrailPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-4xl px-6 py-10 text-sm text-muted-foreground">Loading…</div>}>
      <AuditTrailContent />
    </Suspense>
  );
}
