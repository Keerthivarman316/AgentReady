import Link from "next/link";
import { ArrowRight, ShieldCheck, Workflow, Repeat, ShoppingBag, Store, ScrollText } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const HIGHLIGHTS = [
  {
    icon: ShieldCheck,
    title: "Composite trust score",
    description: "Payment trust, promise-keeping, price fit, and capped reputation — one weighted, inspectable score.",
  },
  {
    icon: Workflow,
    title: "3-layer decision pipeline",
    description: "Hard constraints, weighted heuristics, then a live-price tie-break — every layer logged as it runs.",
  },
  {
    icon: Repeat,
    title: "Automatic fallback",
    description: "A failed top choice falls back to the next-ranked merchant within the same mandate, no re-prompt.",
  },
];

const SURFACES = [
  {
    href: "/buyer",
    icon: ShoppingBag,
    title: "Buyer",
    description:
      "Give the Buyer Agent a natural-language goal. Watch it issue a mandate, walk through the 3-layer decision pipeline, and check out — with live weight sliders to re-rank on demand.",
  },
  {
    href: "/merchant",
    icon: Store,
    title: "Merchant",
    description:
      "Trust Mirror, category Benchmark, Growth Advisor fix list with what-if re-ranking, and SLA Advisor — the merchant-facing view of exactly what the Buyer Agent sees.",
  },
  {
    href: "/audit",
    icon: ScrollText,
    title: "Audit trail",
    description:
      "Every decision layer for a mandate, in order — mandate hash, hard constraints, heuristics ranking, real-time optimization, and any checkout failure/fallback.",
  },
];

export default function Home() {
  return (
    <div>
      <section className="border-b bg-gradient-to-b from-accent/40 to-transparent">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <Badge variant="outline" className="mb-4 border-primary/20 bg-primary/10 text-primary">
            Trust infrastructure for agentic commerce
          </Badge>
          <h1 className="max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
            Where an AI buyer verifies who it&apos;s trusting — and a merchant grows because of it
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-muted-foreground">
            AgentReady computes one composite trust score from real transaction signals, then lets a buyer agent
            act on it and a merchant see — and improve — exactly what drove the decision.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/buyer">
              <Button size="lg" className="gap-1.5">
                Try the Buyer Agent
                <ArrowRight className="size-4" />
              </Button>
            </Link>
            <Link href="/merchant">
              <Button size="lg" variant="outline">
                View Merchant Dashboard
              </Button>
            </Link>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-6 py-14">
        <div className="grid gap-6 sm:grid-cols-3">
          {HIGHLIGHTS.map((h) => (
            <div key={h.title} className="flex flex-col gap-2">
              <h.icon className="size-5 text-primary" />
              <h3 className="font-medium">{h.title}</h3>
              <p className="text-sm text-muted-foreground">{h.description}</p>
            </div>
          ))}
        </div>

        <div className="mt-14 grid gap-6 sm:grid-cols-3">
          {SURFACES.map((surface) => (
            <Link key={surface.href} href={surface.href} className="group">
              <Card className="h-full transition-shadow group-hover:shadow-md">
                <CardHeader>
                  <surface.icon className="mb-1 size-5 text-primary" />
                  <CardTitle className="text-lg">{surface.title}</CardTitle>
                  <CardDescription>{surface.description}</CardDescription>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
