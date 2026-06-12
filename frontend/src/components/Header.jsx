import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { githubApi } from "../api";
import { clearToken } from "../config";
import Logo from "./Logo";

export default function Header({ rightExtra = null }) {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);

  useEffect(() => {
    let alive = true;
    githubApi
      .get("/user")
      .then((r) => alive && setUser(r.data))
      .catch(() => alive && setUser(null));
    return () => {
      alive = false;
    };
  }, []);

  const logout = () => {
    clearToken();
    navigate("/");
  };

  return (
    <header className="h-14 border-b border-border bg-bg px-6 flex items-center justify-between flex-shrink-0">
      <Link to="/dashboard" className="hover:opacity-80">
        <Logo />
      </Link>
      <div className="flex items-center gap-4">
        {rightExtra}
        {user && (
          <>
            <div className="flex items-center gap-2 text-sm">
              <img
                src={user.avatar_url}
                alt={user.login}
                className="h-7 w-7 rounded border border-border"
              />
              <span className="text-textmute">{user.login}</span>
            </div>
            <button className="btn btn-ghost text-xs" onClick={logout}>
              Sign out
            </button>
          </>
        )}
      </div>
    </header>
  );
}
