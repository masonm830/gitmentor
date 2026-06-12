import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import Header from "../components/Header";
import Loading from "../components/Loading";
import Badge from "../components/Badge";

const GAP_COLOR = {
  generated: "text-textmute",
  hand_written: "text-success",
  handwritten: "text-success",
  modified: "text-warning",
  "generated-then-edited": "text-warning",
};

function classifyColor(c) {
  if (!c) return "text-text";
  return GAP_COLOR[c] || "text-text";
}

function classifyLabel(c) {
  if (!c) return "Unclassified";
  return c.replace(/_/g, " ").replace(/-/g, " ");
}

export default function Analysis() {
  const { repoId } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .get(`/api/repos/${repoId}/analysis`)
      .then((r) => {
        if (!alive) return;
        setData(r.data);
        const files = Object.keys(r.data.analysis.file_explanations || {});
        if (files.length) setSelected(files[0]);
      })
      .catch((e) => alive && setErr(e?.response?.data?.detail || e.message));
    return () => {
      alive = false;
    };
  }, [repoId]);

  const files = useMemo(() => {
    if (!data) return [];
    const expls = data.analysis.file_explanations || {};
    const gap = data.analysis.gap_analysis || {};
    return Object.keys(expls).sort().map((fp) => ({
      file_path: fp,
      classification: gap[fp]?.classification,
    }));
  }, [data]);

  if (err)
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center text-danger text-sm">
          {err}
        </main>
      </div>
    );
  if (!data)
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center">
          <Loading label="Loading analysis…" />
        </main>
      </div>
    );

  const explanation = selected
    ? data.analysis.file_explanations?.[selected] || ""
    : "";
  const parsed = selected ? data.parsed_files?.[selected] : null;
  const functions = parsed?.functions || [];
  const gap = selected ? data.analysis.gap_analysis?.[selected] : null;

  return (
    <div className="h-screen flex flex-col bg-bg">
      <Header
        rightExtra={
          <span className="text-xs text-textmute font-mono">
            {data.repo.owner}/{data.repo.name}
          </span>
        }
      />
      <div className="flex-1 flex min-h-0">
        {/* Left: file tree */}
        <aside className="w-60 border-r border-border overflow-y-auto bg-surface">
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-textmute border-b border-border">
            Files ({files.length})
          </div>
          <ul className="py-1">
            {files.map((f) => (
              <li key={f.file_path}>
                <button
                  className={`w-full text-left px-3 py-1.5 text-xs font-mono truncate hover:bg-surface2 ${
                    selected === f.file_path ? "bg-surface2 text-accent" : classifyColor(f.classification)
                  }`}
                  onClick={() => setSelected(f.file_path)}
                  title={f.file_path}
                >
                  {f.file_path}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {/* Center: file explanation */}
        <section className="flex-1 overflow-y-auto px-8 py-6 min-w-0">
          {selected ? (
            <>
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-mono text-sm break-all">{selected}</h2>
                {gap?.classification && (
                  <Badge
                    tone={
                      gap.classification === "hand_written"
                        ? "success"
                        : gap.classification === "generated"
                        ? "default"
                        : "warning"
                    }
                  >
                    {classifyLabel(gap.classification)}
                  </Badge>
                )}
              </div>

              <div className="text-sm text-text leading-relaxed whitespace-pre-wrap">
                {explanation || (
                  <span className="text-textmute italic">
                    No explanation stored for this file.
                  </span>
                )}
              </div>

              {gap?.reason && (
                <div className="mt-4 text-xs text-textmute border-l-2 border-border pl-3">
                  Gap detector: {gap.reason}
                </div>
              )}

              {functions.length > 0 && (
                <div className="mt-8">
                  <h3 className="text-xs uppercase tracking-wider text-textmute mb-3">
                    Functions ({functions.length})
                  </h3>
                  <ul className="space-y-2">
                    {functions.map((fn) => (
                      <li
                        key={`${fn.name}-${fn.line_start}`}
                        className="card py-3"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-sm text-accent">
                            {fn.name}()
                          </span>
                          <span className="font-mono text-xs text-textmute">
                            L{fn.line_start}–L{fn.line_end}
                          </span>
                        </div>
                        {fn.docstring && (
                          <p className="text-xs text-textmute mt-2 whitespace-pre-wrap">
                            {fn.docstring}
                          </p>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          ) : (
            <div className="text-textmute text-sm">Select a file on the left.</div>
          )}
        </section>

        {/* Right: architecture overview */}
        <aside className="w-72 border-l border-border overflow-y-auto bg-surface px-5 py-5 flex flex-col">
          <h3 className="text-xs uppercase tracking-wider text-textmute mb-3">
            Architecture Overview
          </h3>
          <div className="text-sm text-text whitespace-pre-wrap leading-relaxed flex-1">
            {data.analysis.architecture_overview || (
              <span className="text-textmute italic">
                No architecture overview generated.
              </span>
            )}
          </div>
          <Link
            to={`/repos/${repoId}/interview`}
            className="btn btn-primary mt-5"
          >
            Start Mock Interview
          </Link>
        </aside>
      </div>
    </div>
  );
}
