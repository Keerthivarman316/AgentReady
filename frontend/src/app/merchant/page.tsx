"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Merchant } from "@/lib/types";

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
      <h1 className="text-2xl font-semibold text-gray-900">Merchants</h1>
      <p className="mt-1 text-sm text-gray-600">
        Pick a merchant to see the Trust Mirror, category Benchmark, Growth Advisor, and SLA Advisor.
      </p>

      {loading && <p className="mt-6 text-sm text-gray-500">Loading…</p>}
      {error && (
        <div className="mt-6 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error} — is the backend running and the database seeded?
        </div>
      )}

      {Object.entries(byCategory).map(([category, list]) => (
        <section key={category} className="mt-6">
          <h2 className="text-sm font-semibold text-gray-500">{category}</h2>
          <div className="mt-2 grid gap-3 sm:grid-cols-2">
            {list.map((m) => (
              <Link
                key={m.id}
                href={`/merchant/${m.id}`}
                className="rounded-md border border-gray-200 bg-white p-4 hover:shadow-md"
              >
                <span className="font-medium text-gray-900">{m.name}</span>
                <span className="ml-2 text-xs text-gray-400">SLA {m.declared_sla_days}d</span>
              </Link>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
