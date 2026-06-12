import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { setToken } from "../config";
import Loading from "../components/Loading";

export default function AuthCallback() {
  const navigate = useNavigate();
  const [error, setError] = useState(null);

  useEffect(() => {
    // Token arrives in the URL fragment (e.g. #token=ghu_...). Fragments never travel
    // to the server, so the token does not appear in Referer headers or access logs.
    const params = new URLSearchParams(window.location.hash.slice(1));
    const token = params.get("token");
    const err = params.get("error");

    if (err) {
      setError(err);
      return;
    }
    if (!token) {
      setError("No token returned from GitHub");
      return;
    }

    setToken(token);
    // Strip the fragment from the address bar so the token does not linger in browser
    // history or get exposed via a copy-pasted URL.
    window.history.replaceState(null, "", window.location.pathname);
    navigate("/dashboard", { replace: true });
  }, [navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      {error ? (
        <div className="text-center">
          <p className="text-danger mb-3">Sign-in failed: {error}</p>
          <button className="btn btn-secondary" onClick={() => navigate("/")}>
            Back to start
          </button>
        </div>
      ) : (
        <Loading label="Signing you in…" />
      )}
    </div>
  );
}
