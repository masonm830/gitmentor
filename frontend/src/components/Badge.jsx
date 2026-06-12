const TONE = {
  default: "bg-surface text-textmute border-border",
  accent: "bg-accent/10 text-accent border-accent/30",
  success: "bg-success/10 text-success border-success/30",
  warning: "bg-warning/10 text-warning border-warning/30",
  danger: "bg-danger/10 text-danger border-danger/30",
};

export default function Badge({ children, tone = "default", className = "" }) {
  return (
    <span className={`badge ${TONE[tone] || TONE.default} ${className}`}>
      {children}
    </span>
  );
}
