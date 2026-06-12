import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { setToken } from "../config";
import Loading from "../components/Loading";

export default function AuthCallback() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState(null);

  useEffect(() => {
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
    navigate("/dashboard", { replace: true });
  }, [params, navigate]);

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
