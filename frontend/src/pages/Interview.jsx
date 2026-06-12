import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../api";
import Header from "../components/Header";
import Loading from "../components/Loading";
import Badge from "../components/Badge";
import ScoreBadge from "../components/ScoreBadge";
import { useSpeechRecognition, SPEECH_SUPPORTED } from "../hooks/useSpeechRecognition";

const CATEGORY_TONE = {
  data_flow: "accent",
  design: "success",
  failure_mode: "danger",
  implementation: "warning",
};

const CATEGORY_LABEL = {
  data_flow: "Data flow",
  design: "Design",
  failure_mode: "Failure mode",
  implementation: "Implementation",
};

export default function Interview() {
  const { repoId } = useParams();
  const [session, setSession] = useState(null);
  const [err, setErr] = useState(null);
  const [activeIdx, setActiveIdx] = useState(0);
  // answers[idx] = { draft: string, submittedAnswer: string|null, evaluation: object|null, submitting: bool, error: string|null }
  const [answers, setAnswers] = useState({});

  // Load latest analysis -> start session
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const a = await api.get(`/api/repos/${repoId}/analysis`);
        if (!alive) return;
        const analysisId = a.data.analysis.id;
        const start = await api.post(
          `/api/repos/${repoId}/interview/start`,
          { analysis_id: analysisId }
        );
        if (!alive) return;
        setSession(start.data);
      } catch (e) {
        if (alive) setErr(e?.response?.data?.detail || e.message);
      }
    })();
    return () => { alive = false; };
  }, [repoId]);

  const ensureAnswer = (idx) =>
    answers[idx] || { draft: "", submittedAnswer: null, evaluation: null, submitting: false, error: null };

  const updateAnswer = (idx, patch) => {
    setAnswers((prev) => ({ ...prev, [idx]: { ...ensureAnswer(idx), ...patch } }));
  };

  const submitAnswer = async () => {
    const idx = activeIdx;
    const current = ensureAnswer(idx);
    const text = current.draft.trim();
    if (!text || current.submitting) return;

    updateAnswer(idx, { submitting: true, error: null });
    try {
      const r = await api.post(
        `/api/repos/${repoId}/interview/evaluate`,
        {
          session_id: session.session_id,
          question_index: idx,
          user_answer: text,
        }
      );
      updateAnswer(idx, {
        submittedAnswer: text,
        evaluation: r.data.evaluation,
        submitting: false,
        error: null,
        draft: "",
      });
    } catch (e) {
      updateAnswer(idx, {
        submitting: false,
        error: e?.response?.data?.detail || e.message,
      });
    }
  };

  if (err)
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center text-danger text-sm">
          {err}
        </main>
      </div>
    );

  if (!session)
    return (
      <div className="min-h-screen flex flex-col">
        <Header />
        <main className="flex-1 flex items-center justify-center">
          <Loading label="Starting interview…" />
        </main>
      </div>
    );

  const activeQuestion = session.questions[activeIdx];
  const activeState = ensureAnswer(activeIdx);

  return (
    <div className="h-screen flex flex-col bg-bg">
      <Header
        rightExtra={
          <span className="text-xs text-textmute font-mono">Interview · {session.questions.length} questions</span>
        }
      />
      <div className="flex-1 flex min-h-0">
        {/* Sidebar */}
        <aside className="w-72 border-r border-border overflow-y-auto bg-surface">
          <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-textmute border-b border-border">
            Questions
          </div>
          <ul>
            {session.questions.map((q) => {
              const state = ensureAnswer(q.index);
              const active = q.index === activeIdx;
              return (
                <li key={q.index}>
                  <button
                    className={`w-full text-left px-3 py-3 border-b border-border hover:bg-surface2 ${
                      active ? "bg-surface2" : ""
                    }`}
                    onClick={() => setActiveIdx(q.index)}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-mono text-textmute">
                        Q{q.index + 1}
                      </span>
                      <div className="flex items-center gap-1">
                        {q.category && (
                          <Badge tone={CATEGORY_TONE[q.category] || "default"}>
                            {CATEGORY_LABEL[q.category] || q.category}
                          </Badge>
                        )}
                        {q.difficulty && (
                          <Badge tone="default">{q.difficulty}</Badge>
                        )}
                      </div>
                    </div>
                    <div className="text-xs text-text line-clamp-2">
                      {q.question}
                    </div>
                    {state.evaluation && (
                      <div className="mt-2 text-[10px] font-mono text-textmute">
                        scored {state.evaluation.scores.overall}/10
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        {/* Chat */}
        <ChatPanel
          question={activeQuestion}
          state={activeState}
          onDraftChange={(t) => updateAnswer(activeIdx, { draft: t })}
          onSubmit={submitAnswer}
          onNext={
            activeIdx < session.questions.length - 1
              ? () => setActiveIdx(activeIdx + 1)
              : null
          }
        />
      </div>
    </div>
  );
}

function ChatPanel({ question, state, onDraftChange, onSubmit, onNext }) {
  const scrollerRef = useRef(null);
  const draftRef = useRef(state.draft);

  useEffect(() => { draftRef.current = state.draft; }, [state.draft]);

  // Speech: append finals to the draft, show interims appended live.
  const [interim, setInterim] = useState("");
  const { supported, listening, toggle } = useSpeechRecognition({
    onTranscript: ({ finalChunk, interim }) => {
      if (finalChunk) {
        const next = (draftRef.current ? draftRef.current + " " : "") + finalChunk.trim();
        onDraftChange(next);
        setInterim("");
      } else {
        setInterim(interim);
      }
    },
  });

  useEffect(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, [state.evaluation, state.submittedAnswer]);

  const displayDraft = useMemo(() => {
    if (!listening) return state.draft;
    return interim ? `${state.draft}${state.draft ? " " : ""}${interim}` : state.draft;
  }, [state.draft, interim, listening]);

  return (
    <section className="flex-1 flex flex-col min-w-0">
      <div ref={scrollerRef} className="flex-1 overflow-y-auto px-8 py-6 space-y-4">
        {/* GitMentor question bubble */}
        <Bubble side="left" sender="GitMentor">
          <p className="text-sm leading-relaxed">{question.question}</p>
          {question.relevant_files?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1">
              {question.relevant_files.map((fp) => (
                <Badge key={fp} tone="accent">
                  <span className="font-mono">{fp}</span>
                </Badge>
              ))}
            </div>
          )}
        </Bubble>

        {state.submittedAnswer && (
          <Bubble side="right" sender="You">
            <p className="text-sm whitespace-pre-wrap">{state.submittedAnswer}</p>
          </Bubble>
        )}

        {state.submitting && (
          <Bubble side="left" sender="GitMentor">
            <Loading label="Grading your answer…" />
          </Bubble>
        )}

        {state.evaluation && (
          <Bubble side="left" sender="GitMentor">
            <EvaluationCard evaluation={state.evaluation} onNext={onNext} />
          </Bubble>
        )}

        {state.error && (
          <div className="text-danger text-xs border border-danger/40 rounded p-2">
            {state.error}
          </div>
        )}
      </div>

      {/* Composer */}
      <div className="border-t border-border bg-surface px-6 py-4">
        <div className="flex gap-3 items-end">
          <textarea
            className="input min-h-[80px] resize-y font-sans"
            placeholder={
              listening
                ? "Listening… speak your answer"
                : "Type your answer, or click the mic to speak it"
            }
            value={displayDraft}
            onChange={(e) => onDraftChange(e.target.value)}
            disabled={state.submitting}
          />
          <div className="flex flex-col gap-2">
            <MicButton
              supported={supported}
              listening={listening}
              onClick={toggle}
            />
            <button
              className="btn btn-primary text-xs"
              disabled={!state.draft.trim() || state.submitting}
              onClick={onSubmit}
            >
              Submit
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

function Bubble({ side, sender, children }) {
  const align = side === "right" ? "items-end" : "items-start";
  const tone =
    side === "right"
      ? "bg-accent/10 border-accent/30"
      : "bg-surface border-border";
  return (
    <div className={`flex flex-col ${align}`}>
      <div className="text-[10px] uppercase tracking-wider text-textmute mb-1">
        {sender}
      </div>
      <div className={`max-w-[85%] border rounded p-3 ${tone}`}>{children}</div>
    </div>
  );
}

function MicButton({ supported, listening, onClick }) {
  if (!supported) {
    return (
      <button
        className="btn btn-ghost text-xs cursor-not-allowed"
        title="Voice input not supported in this browser"
        disabled
      >
        🎤 N/A
      </button>
    );
  }
  return (
    <button
      className={`btn text-xs ${
        listening
          ? "bg-danger/20 text-danger border-danger mic-recording"
          : "btn-secondary"
      }`}
      onClick={onClick}
      title={listening ? "Stop recording" : "Start voice input"}
    >
      {listening ? "● Stop" : "🎤 Speak"}
    </button>
  );
}

function EvaluationCard({ evaluation, onNext }) {
  const { scores, strengths, gaps, follow_up_question, semantic_similarity } = evaluation;
  return (
    <div className="space-y-4">
      <div className="flex gap-2 flex-wrap">
        <ScoreBadge label="Accuracy" value={scores.accuracy} />
        <ScoreBadge label="Completeness" value={scores.completeness} />
        <ScoreBadge label="Depth" value={scores.depth} />
        <ScoreBadge label="Overall" value={scores.overall} />
      </div>
      <div className="text-[10px] text-textmute font-mono">
        semantic similarity: {semantic_similarity?.toFixed?.(3) ?? semantic_similarity}
      </div>
      {strengths?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-success mb-1">
            Strengths
          </div>
          <ul className="space-y-1 text-sm">
            {strengths.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-success">✓</span>
                <span>{s}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {gaps?.length > 0 && (
        <div>
          <div className="text-xs uppercase tracking-wider text-danger mb-1">
            Gaps
          </div>
          <ul className="space-y-1 text-sm">
            {gaps.map((g, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-danger">✗</span>
                <span>{g}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {follow_up_question && (
        <div className="border-l-2 border-accent pl-3 py-1">
          <div className="text-[10px] uppercase tracking-wider text-accent mb-1">
            Follow-up
          </div>
          <p className="text-sm">{follow_up_question}</p>
        </div>
      )}
      {onNext && (
        <div className="pt-1">
          <button className="btn btn-secondary text-xs" onClick={onNext}>
            Next Question →
          </button>
        </div>
      )}
    </div>
  );
}
