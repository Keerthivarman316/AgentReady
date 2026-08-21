import Link from "next/link";

const SURFACES = [
  {
    href: "/buyer",
    title: "Buyer",
    description:
      "Give the Buyer Agent a natural-language goal. Watch it issue a mandate, walk through the 3-layer decision pipeline, and check out — with live weight sliders to re-rank on demand.",
  },
  {
    href: "/merchant",
    title: "Merchant",
    description:
      "Trust Mirror, category Benchmark, Growth Advisor fix list with what-if re-ranking, and SLA Advisor — the merchant-facing view of exactly what the Buyer Agent sees.",
  },
  {
    href: "/audit",
    title: "Audit trail",
    description:
      "Every decision layer for a mandate, in order — mandate hash, hard constraints, heuristics ranking, real-time optimization, and any checkout failure/fallback.",
  },
];

export default function Home() {
  return (
    <div className="mx-auto max-w-5xl px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-tight text-gray-900">AgentReady</h1>
      <p className="mt-3 max-w-2xl text-gray-600">
        A trust and growth layer for agentic commerce — where an AI buyer can verify who
        it&apos;s trusting, and an AI-ready merchant can grow because of it.
      </p>

      <div className="mt-10 grid gap-6 sm:grid-cols-3">
        {SURFACES.map((surface) => (
          <Link
            key={surface.href}
            href={surface.href}
            className="flex flex-col gap-2 rounded-lg border border-gray-200 bg-white p-5 transition-shadow hover:shadow-md"
          >
            <span className="text-lg font-medium text-gray-900">{surface.title}</span>
            <span className="text-sm text-gray-600">{surface.description}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
