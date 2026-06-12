import axios from "axios";

import { API_BASE_URL, getToken } from "./config";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 90_000,
});

// GitHub API client — uses the user's OAuth token from localStorage.
export const githubApi = axios.create({
  baseURL: "https://api.github.com",
  timeout: 20_000,
});

githubApi.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
    config.headers.Accept = "application/vnd.github+json";
  }
  return config;
});
