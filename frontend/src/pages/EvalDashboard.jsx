import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import Logo from "../components/Logo";
import Loading from "../components/Loading";
import Badge from "../components/Badge";

function passRateClass(pr) {
  if (pr == null) return "text-textmute";
  const v = pr * 100;
  if (v < 60) return "text-danger";
  if (v < 80) return "text-warning";
  return "text-success";
}

function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

function fmtPct(n) {
  if (n == null) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function fmtNum(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

export default function EvalDashboard() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [err, setErr] = useState(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await api.get("/api/eval/runs");
      setRuns(r.data?.runs || []);
      setErr(null);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const runEval = async () => {
    if (running) return;
    setRunning(true);
    setErr(null);
    try {
      // Server-side eval takes 2-5 minutes — extend axios timeout for this call.
      await api.post("/api/eval/run", null, { timeout: 600_000 });
      await refresh();
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    } finally {
      setRunning(false);
    }
  };

  const mostRecent = runs[0] || null;

  return (
    <div className="min-h-screen flex flex-col bg-bg">
      <header className="h-14 border-b border-border bg-bg px-6 flex items-center justify-between flex-shrink-0">
        <Link to="/" className="hover:opacity-80">
          <Logo />
        </Link>
        <span className="text-xs text-textmute font-mono">
          Eval — internal tool
        </span>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold">Eval Dashboard</h1>
            <p className="text-sm text-textmute mt-1">
              Golden-dataset runs against the InterviewEvaluator. Last 10 runs.
            </p>
          </div>
          <button
            className="btn btn-primary"
            onClick={runEval}
            disabled={running}
          >
            {running ? "Running…" : "Run Eval"}
          </button>
        </div>

        {running && (
          <div className="card mb-4">
            <Loading label="Running eval — this takes 2-5 minutes. Don't close this tab." />
          </div>
        )}

        {err && (
          <div className="card border-danger/40 text-danger mb-4 text-sm">
            {err}
          </div>
        )}

        {loading ? (
          <Loading />
        ) : runs.length === 0 ? (
          <div className="card text-textmute text-sm">
            No eval runs yet. Click <span className="text-accent">Run Eval</span> to start.
          </div>
        ) : (
          <>
            <div className="card overflow-x-auto p-0">
              <table className="w-full text-sm">
                <thead className="text-[10px] uppercase tracking-wider text-textmute">
                  <tr className="border-b border-border">
                    <Th>Date</Th>
                    <Th>Pass rate</Th>
                    <Th>Overall</Th>
                    <Th>Accuracy</Th>
                    <Th>Completeness</Th>
                    <Th>Depth</Th>
                    <Th>Semantic sim</Th>
                    <Th>Latency (s)</Th>
                    <Th>Passed / total</Th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr
                      key={r.id}
                      className="border-b border-border last:border-b-0 hover:bg-surface2"
                    >
                      <Td className="font-mono text-xs">{fmtDate(r.created_at)}</Td>
                      <Td className={`font-mono ${passRateClass(r.pass_rate)}`}>
                        {fmtPct(r.pass_rate)}
                      </Td>
                      <Td className="font-mono">{fmtNum(r.avg_overall)}</Td>
                      <Td className="font-mono">{fmtNum(r.avg_accuracy)}</Td>
                      <Td className="font-mono">{fmtNum(r.avg_completeness)}</Td>
                      <Td className="font-mono">{fmtNum(r.avg_depth)}</Td>
                      <Td className="font-mono">{fmtNum(r.avg_semantic_similarity, 3)}</Td>
                      <Td className="font-mono">{fmtNum(r.avg_latency_seconds, 2)}</Td>
                      <Td className="font-mono">
                        {r.passed} / {r.total_entries}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {mostRecent && (
              <section className="mt-8">
                <h2 className="text-lg font-semibold mb-1">
                  Most recent run — per-entry breakdown
                </h2>
                <p className="text-xs text-textmute mb-4 font-mono">
                  {fmtDate(mostRecent.created_at)}
                </p>
                <ul className="space-y-2">
                  {(mostRecent.per_entry_results || []).map((e, i) => (
                    <li key={i} className="card py-3">
                      <div className="flex items-start gap-3 justify-between">
                        <div className="min-w-0">
                          <div className="text-sm text-text">
                            {i + 1}. {e.question_text}
                          </div>
                          <div className="text-[11px] text-textmute font-mono mt-1 flex gap-3 flex-wrap">
                            <span>category: {e.category}</span>
                            <span>difficulty: {e.difficulty}</span>
                            <span>
                              expected: {e.expected_score_min}–{e.expected_score_max}
                            </span>
                            <span>actual: {e.overall}</span>
                            <span>
                              acc/comp/depth: {e.accuracy}/{e.completeness}/{e.depth}
                            </span>
                            <span>sim: {fmtNum(e.semantic_similarity, 3)}</span>
                            <span>{fmtNum(e.latency_seconds, 2)}s</span>
                          </div>
                          {e.error && (
                            <div className="text-xs text-danger mt-1">
                              error: {e.error}
                            </div>
                          )}
                        </div>
                        <Badge tone={e.passed ? "success" : "danger"}>
                          {e.passed ? "PASS" : "FAIL"}
                        </Badge>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function Th({ children }) {
  return <th className="text-left px-4 py-2 font-medium">{children}</th>;
}

function Td({ children, className = "" }) {
  return <td className={`px-4 py-2 ${className}`}>{children}</td>;
}
