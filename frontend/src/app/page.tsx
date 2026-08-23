import Link from "next/link";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

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
      <h1 className="text-3xl font-semibold tracking-tight">AgentReady</h1>
      <p className="mt-3 max-w-2xl text-muted-foreground">
        A trust and growth layer for agentic commerce — where an AI buyer can verify who
        it&apos;s trusting, and an AI-ready merchant can grow because of it.
      </p>

      <div className="mt-10 grid gap-6 sm:grid-cols-3">
        {SURFACES.map((surface) => (
          <Link key={surface.href} href={surface.href} className="group">
            <Card className="h-full transition-shadow group-hover:shadow-md">
              <CardHeader>
                <CardTitle className="text-lg">{surface.title}</CardTitle>
                <CardDescription>{surface.description}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
