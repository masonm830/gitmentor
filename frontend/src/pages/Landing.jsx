import { API_BASE_URL } from "../config";
import Logo from "../components/Logo";

const FEATURES = [
  {
    icon: "▣",
    title: "Architecture Analysis",
    body: "Plain-English breakdown of how every file in your repo fits together.",
  },
  {
    icon: "◆",
    title: "Mock Interview",
    body: "Scored interview questions grounded in your actual code, not generic trivia.",
  },
  {
    icon: "◈",
    title: "Gap Detection",
    body: "Flags AI-generated files you haven't modified and can't yet explain.",
  },
];

export default function Landing() {
  const handleConnect = () => {
    window.location.href = `${API_BASE_URL}/auth/github`;
  };

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <header className="h-14 px-6 flex items-center border-b border-border">
        <Logo />
      </header>

      <main className="flex-1 flex flex-col">
        <section className="flex-1 flex items-center justify-center px-6">
          <div className="max-w-2xl text-center">
            <h1 className="text-4xl sm:text-5xl font-semibold tracking-tight text-text">
              Understand every line of code you've built
            </h1>
            <p className="mt-6 text-lg text-textmute leading-relaxed">
              GitMentor analyzes your GitHub repos and teaches them back to you.
              Know your codebase well enough to explain it in any interview.
            </p>
            <div className="mt-10">
              <button
                onClick={handleConnect}
                className="btn btn-primary px-6 py-3 text-base"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  aria-hidden
                >
                  <path d="M12 .5C5.7.5.5 5.7.5 12c0 5.1 3.3 9.4 7.9 10.9.6.1.8-.2.8-.5v-2c-3.2.7-3.9-1.4-3.9-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.7 1.3 3.4 1 .1-.8.4-1.3.8-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.5-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2.9-.3 1.9-.4 2.9-.4s2 .1 2.9.4c2.3-1.5 3.3-1.2 3.3-1.2.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.3c0 .3.2.6.8.5 4.6-1.5 7.9-5.8 7.9-10.9C23.5 5.7 18.3.5 12 .5z" />
                </svg>
                Connect GitHub
              </button>
            </div>
          </div>
        </section>

        <section className="border-t border-border bg-bg">
          <div className="max-w-5xl mx-auto px-6 py-16 grid grid-cols-1 md:grid-cols-3 gap-4">
            {FEATURES.map((f) => (
              <div key={f.title} className="card">
                <div className="text-accent text-xl mb-3 font-mono">{f.icon}</div>
                <h3 className="text-sm font-semibold mb-1">{f.title}</h3>
                <p className="text-sm text-textmute leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
        </section>
      </main>

      <footer className="h-12 border-t border-border flex items-center justify-center text-xs text-textmute">
        Built with Claude Code · Phase 6
      </footer>
    </div>
  );
}
