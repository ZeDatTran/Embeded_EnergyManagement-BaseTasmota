"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    // AuthContext handles the redirect logic
    // This page just shows a loading state while AuthContext resolves
    const token = localStorage.getItem("smart_home_token");
    if (token) {
      router.replace("/dashboard");
    } else {
      router.replace("/login");
    }
  }, [router]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100vh",
        background: "var(--background)",
      }}
    >
      <Loader2
        size={32}
        style={{ animation: "spin 1s linear infinite", opacity: 0.5 }}
      />
    </div>
  );
}
