// Centralized so deployment only needs one swap.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

export const TOKEN_KEY = "github_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// All file paths displayed in the UI go through this. Backend already normalizes
// at write time, but old rows and a few edge cases (Windows clone dirs) still
// produce backslashes — normalize at render time as a defensive belt-and-braces.
export function normalizeFilePath(path) {
  if (path == null) return path;
  return String(path).replace(/\\/g, "/");
}
