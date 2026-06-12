export default function Logo({ className = "" }) {
  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div className="h-6 w-6 rounded border border-accent flex items-center justify-center text-accent font-mono text-xs">
        {"</>"}
      </div>
      <span className="font-semibold tracking-tight">GitMentor</span>
    </div>
  );
}
