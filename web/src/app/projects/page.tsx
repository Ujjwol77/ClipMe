"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ProjectStatusBadge } from "@/components/ProjectStatusBadge";
import { UploadForm } from "@/components/UploadForm";
import { useAuth } from "@/lib/AuthProvider";
import { api } from "@/lib/apiClient";
import { supabase } from "@/lib/supabaseClient";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    api
      .listProjects()
      .then(setProjects)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [user]);

  if (loading || !user) {
    return <main className="flex min-h-screen items-center justify-center text-neutral-500">Loading...</main>;
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <div className="mb-8 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Your projects</h1>
        <button
          onClick={() => supabase.auth.signOut().then(() => router.replace("/login"))}
          className="text-sm text-neutral-400 underline underline-offset-2"
        >
          Sign out
        </button>
      </div>

      <div className="mb-8">
        <UploadForm />
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <ul className="flex flex-col gap-2">
        {projects?.length === 0 && (
          <li className="text-sm text-neutral-500">No projects yet. Upload a video to get started.</li>
        )}
        {projects?.map((p) => (
          <li key={p.id}>
            <Link
              href={`/projects/${p.id}`}
              className="flex items-center justify-between rounded-md border border-neutral-800 px-4 py-3 hover:border-neutral-600"
            >
              <div>
                <p className="text-sm font-medium">{p.title}</p>
                <p className="text-xs text-neutral-500">{new Date(p.created_at).toLocaleString()}</p>
              </div>
              <ProjectStatusBadge status={p.status} />
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
