export default function ScoreBar({
  label,
  value,
  sublabel,
}: {
  label: string;
  value: number;
  sublabel?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const color = value >= 0.7 ? "bg-emerald-500" : value >= 0.4 ? "bg-amber-500" : "bg-red-500";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium text-gray-700">{label}</span>
        <span className="tabular-nums text-gray-500">
          {value.toFixed(3)}
          {sublabel ? <span className="ml-1 text-gray-400">{sublabel}</span> : null}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
        <div className={`h-full rounded-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
