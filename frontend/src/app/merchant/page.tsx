"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Merchant } from "@/lib/types";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export default function MerchantListPage() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listMerchants()
      .then(setMerchants)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const byCategory = merchants.reduce<Record<string, Merchant[]>>((acc, m) => {
    (acc[m.category] ??= []).push(m);
    return acc;
  }, {});

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Merchants</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Pick a merchant to see the Trust Mirror, category Benchmark, Growth Advisor, and SLA Advisor.
      </p>

      {loading && (
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-lg" />
          ))}
        </div>
      )}
      {error && (
        <div className="mt-6 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error} — is the backend running and the database seeded?
        </div>
      )}

      {Object.entries(byCategory).map(([category, list]) => (
        <section key={category} className="mt-6">
          <h2 className="text-sm font-semibold text-muted-foreground">{category}</h2>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {list.map((m) => (
              <Link key={m.id} href={`/merchant/${m.id}`}>
                <Card className="transition-shadow hover:shadow-md">
                  <CardHeader className="flex-row items-center justify-between gap-3 space-y-0">
                    <CardTitle className="text-sm">{m.name}</CardTitle>
                    <Badge variant="secondary">SLA {m.declared_sla_days}d</Badge>
                  </CardHeader>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
