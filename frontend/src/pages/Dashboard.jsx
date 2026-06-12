import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, githubApi } from "../api";
import Header from "../components/Header";
import Modal from "../components/Modal";
import Badge from "../components/Badge";
import Loading from "../components/Loading";

function statusTone(status, hasAnalysis) {
  if (hasAnalysis) return "success";
  if (status === "failed") return "danger";
  if (status === "pending" || status === "starting") return "warning";
  return "default";
}

function statusLabel(status, hasAnalysis) {
  if (hasAnalysis) return "Analyzed";
  if (status === "failed") return "Failed";
  return "Pending analysis";
}

function fmtDate(s) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

export default function Dashboard() {
  const [me, setMe] = useState(null);
  const [repos, setRepos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);

  const refresh = async (owner) => {
    if (!owner) return;
    setLoading(true);
    try {
      const r = await api.get(`/api/repos`, { params: { owner } });
      setRepos(r.data.repos || []);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const user = await githubApi.get("/user");
        setMe(user.data);
        await refresh(user.data.login);
      } catch (e) {
        setErr("Could not load your GitHub profile. Your session may have expired.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-bg">
      <Header />
      <main className="flex-1 max-w-5xl w-full mx-auto px-6 py-10">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold">Your Repositories</h1>
            <p className="text-sm text-textmute mt-1">
              Repos you've connected to GitMentor.
            </p>
          </div>
          <button
            className="btn btn-primary"
            onClick={() => setModalOpen(true)}
          >
            Analyze New Repo
          </button>
        </div>

        {err && (
          <div className="card border-danger/40 text-danger mb-4 text-sm">
            {err}
          </div>
        )}

        {loading ? (
          <Loading />
        ) : repos.length === 0 ? (
          <div className="card text-textmute text-sm">
            No repos analyzed yet. Click <span className="text-accent">Analyze New Repo</span> to start.
          </div>
        ) : (
          <ul className="space-y-3">
            {repos.map((r) => (
              <li key={r.id} className="card flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm truncate">
                      {r.owner}/{r.name}
                    </span>
                    <Badge tone={statusTone(r.status, r.has_analysis)}>
                      {statusLabel(r.status, r.has_analysis)}
                    </Badge>
                  </div>
                  <div className="text-xs text-textmute mt-1">
                    Last analyzed: {fmtDate(r.latest_analyzed_at || r.cloned_at)}
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Link
                    to={`/repos/${r.id}/analysis`}
                    className="btn btn-secondary text-xs"
                  >
                    View Analysis
                  </Link>
                  <Link
                    to={`/repos/${r.id}/interview`}
                    className="btn btn-primary text-xs"
                  >
                    Start Interview
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>

      <AnalyzeRepoModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        me={me}
        onAnalyzed={() => me && refresh(me.login)}
      />
    </div>
  );
}

function AnalyzeRepoModal({ open, onClose, me, onAnalyzed }) {
  const [url, setUrl] = useState("");
  const [myRepos, setMyRepos] = useState([]);
  const [loadingMyRepos, setLoadingMyRepos] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [stage, setStage] = useState(null); // 'cloning' | 'parsing' | 'embedding' | 'analyzing'
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!open || !me) return;
    setLoadingMyRepos(true);
    githubApi
      .get(`/user/repos?per_page=30&sort=updated`)
      .then((r) => setMyRepos(r.data || []))
      .catch(() => setMyRepos([]))
      .finally(() => setLoadingMyRepos(false));
  }, [open, me]);

  const submit = async (githubUrl) => {
    setError(null);
    setSubmitting(true);
    try {
      setStage("cloning");
      const created = await api.post(`/api/repos`, { github_url: githubUrl });
      const repoId = created.data.repo_id;
      setStage("parsing");
      await api.post(`/api/repos/${repoId}/analyze`);
      setStage("embedding");
      await api.post(`/api/repos/${repoId}/embed`);
      setStage("analyzing");
      await api.post(`/api/repos/${repoId}/full-analysis`);
      setStage(null);
      onAnalyzed();
      onClose();
    } catch (e) {
      setError(e?.response?.data?.detail || e.message);
      setStage(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onClose={submitting ? () => {} : onClose} title="Analyze a Repository">
      {submitting ? (
        <div className="py-6 space-y-3">
          <Loading label={
            stage === "cloning" ? "Cloning repo…" :
            stage === "parsing" ? "Parsing AST + dependency graph…" :
            stage === "embedding" ? "Embedding code chunks…" :
            stage === "analyzing" ? "Running 4-agent pipeline (60-90s)…" :
            "Working…"
          } />
          <p className="text-xs text-textmute">
            Don't close this window — analysis runs end-to-end.
          </p>
        </div>
      ) : (
        <div className="space-y-5">
          <div>
            <label className="block text-xs font-medium text-textmute mb-2">
              Paste a GitHub URL
            </label>
            <div className="flex gap-2">
              <input
                className="input"
                placeholder="https://github.com/owner/repo"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <button
                className="btn btn-primary text-xs"
                disabled={!url.trim()}
                onClick={() => submit(url.trim())}
              >
                Analyze
              </button>
            </div>
          </div>

          <div className="border-t border-border pt-4">
            <div className="text-xs font-medium text-textmute mb-2">
              Or pick one of yours
            </div>
            {loadingMyRepos ? (
              <Loading />
            ) : (
              <ul className="max-h-64 overflow-y-auto space-y-1">
                {myRepos.map((r) => (
                  <li key={r.id}>
                    <button
                      className="w-full text-left px-2 py-2 rounded hover:bg-surface2 text-sm flex justify-between items-center"
                      onClick={() => submit(r.html_url)}
                    >
                      <span className="font-mono truncate">{r.full_name}</span>
                      <span className="text-xs text-textmute ml-2">{r.language || "—"}</span>
                    </button>
                  </li>
                ))}
                {myRepos.length === 0 && (
                  <li className="text-xs text-textmute">No repos found.</li>
                )}
              </ul>
            )}
          </div>

          {error && (
            <div className="text-danger text-xs border border-danger/40 rounded p-2">
              {error}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
