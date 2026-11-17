import { supabase } from "./supabaseClient";
import type { Project, ProjectDetail } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) {
    throw new Error("Not signed in");
  }
  return { Authorization: `Bearer ${token}` };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeaders()),
    ...(init.headers ?? {}),
  };
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface CreateProjectUpload {
  signed_url: string;
  token: string;
  path: string;
}

export interface CreateProjectResponse {
  project_id: string;
  upload: CreateProjectUpload;
}

export const api = {
  createProject: (filename: string, contentType: string, title?: string) =>
    request<CreateProjectResponse>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ filename, content_type: contentType, title }),
    }),

  processProject: (projectId: string) =>
    request<{ status: string; already_processing: boolean }>(
      `/api/projects/${projectId}/process`,
      { method: "POST" }
    ),

  retryProject: (projectId: string) =>
    request<{ status: string; already_processing: boolean }>(
      `/api/projects/${projectId}/retry`,
      { method: "POST" }
    ),

  listProjects: () => request<Project[]>("/api/projects"),

  getProject: (projectId: string) => request<ProjectDetail>(`/api/projects/${projectId}`),

  getSourceUrl: (projectId: string) =>
    request<{ url: string }>(`/api/projects/${projectId}/source-url`),

  deleteProject: (projectId: string) =>
    request<{ deleted: boolean }>(`/api/projects/${projectId}`, { method: "DELETE" }),

  updateClipTrim: (clipId: string, startSeconds: number, endSeconds: number) =>
    request<{ id: string; start_seconds: number; end_seconds: number; status: string }>(
      `/api/clips/${clipId}`,
      {
        method: "PATCH",
        body: JSON.stringify({ start_seconds: startSeconds, end_seconds: endSeconds }),
      }
    ),

  regenerateClip: (clipId: string) =>
    request<{ queued: boolean }>(`/api/clips/${clipId}/regenerate`, { method: "POST" }),

  downloadClip: (clipId: string) => request<{ url: string }>(`/api/clips/${clipId}/download`),
};
