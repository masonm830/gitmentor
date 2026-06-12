function toneFor(value) {
  if (value >= 7) return "bg-success/15 text-success border-success/40";
  if (value >= 4) return "bg-warning/15 text-warning border-warning/40";
  return "bg-danger/15 text-danger border-danger/40";
}

export default function ScoreBadge({ label, value }) {
  return (
    <div
      className={`flex flex-col items-center justify-center px-3 py-2 rounded border ${toneFor(value)} min-w-[72px]`}
    >
      <div className="text-[10px] uppercase tracking-wider opacity-80">
        {label}
      </div>
      <div className="text-lg font-mono font-semibold leading-tight">
        {value}
      </div>
    </div>
  );
}
