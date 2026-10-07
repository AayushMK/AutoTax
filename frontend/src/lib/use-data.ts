"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";

interface Loaded<T> {
  key: string;
  data: T | null;
  error: ApiError | null;
}

/** Fetch `path` (or skip while null); returns data, error, loading and a reload function. */
export function useData<T>(path: string | null) {
  const [tick, setTick] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null);
  const key = path === null ? null : `${tick}:${path}`;

  useEffect(() => {
    if (key === null || path === null) return;
    let live = true;
    api<T>(path)
      .then((data) => live && setLoaded({ key, data, error: null }))
      .catch((e) => live && setLoaded((prev) => ({
        key,
        data: prev?.data ?? null,
        error: e instanceof ApiError ? e : new ApiError(0, String(e)),
      })));
    return () => {
      live = false;
    };
  }, [key, path]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  const setData = useCallback((data: T) => setLoaded((prev) => ({ key: prev?.key ?? "", data, error: null })), []);

  return {
    data: loaded?.data ?? null, // stale data stays visible while a reload is in flight
    error: loaded?.key === key ? loaded.error : null,
    loading: key !== null && loaded?.key !== key && !loaded?.data,
    reload,
    setData,
  };
}
