export default function Loading({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-3 text-textmute text-sm">
      <span className="inline-block h-3 w-3 border-2 border-textmute border-t-accent rounded-full animate-spin" />
      {label}
    </div>
  );
}
