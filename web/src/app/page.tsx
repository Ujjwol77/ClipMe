"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/AuthProvider";

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user ? "/projects" : "/login");
  }, [loading, user, router]);

  return (
    <main className="flex min-h-screen items-center justify-center text-neutral-500">
      Loading...
    </main>
  );
}
