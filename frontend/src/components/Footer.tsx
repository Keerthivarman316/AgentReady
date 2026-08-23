export default function Footer() {
  return (
    <footer className="border-t">
      <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-2 px-6 py-6 text-xs text-muted-foreground sm:flex-row">
        <span className="flex items-center gap-2">
          <span className="inline-flex size-4 items-center justify-center rounded bg-primary text-[10px] font-bold text-primary-foreground">
            A
          </span>
          AgentReady — trust and growth infrastructure for agentic commerce
        </span>
        <span>Composite Trust Engine · AP2-style mandates · Full audit trail</span>
      </div>
    </footer>
  );
}
