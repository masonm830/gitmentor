import { Navigate } from "react-router-dom";

import { getToken } from "../config";

export default function ProtectedRoute({ children }) {
  if (!getToken()) {
    return <Navigate to="/" replace />;
  }
  return children;
}
