"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { api, getToken } from "@/lib/api";
import { homeFor } from "@/lib/home";
import type { Me } from "@/lib/types";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    api<Me>("/auth/me")
      .then((me) => router.replace(homeFor(me)))
      .catch(() => router.replace("/login"));
  }, [router]);
  return null;
}
