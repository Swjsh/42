"use client";

// Persists a Tile's open/closed state to localStorage, tile-level only (never
// per-activity-row -- rows rotate every 20s poll, so persisting row keys would
// leak unbounded stale entries). SSR-safe: seed useState with defaultOpen (so
// server and first client render agree, no hydration mismatch), then sync
// from storage in a useEffect AFTER mount.

import { useEffect, useState } from "react";

function storageKey(id: string): string {
  return `gamma:tile:${id}:expanded`;
}

export function useTileState(id: string, defaultOpen: boolean): [boolean, (next: boolean) => void] {
  const [open, setOpen] = useState<boolean>(defaultOpen);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(storageKey(id));
      if (stored !== null) setOpen(stored === "1");
    } catch {
      // localStorage unavailable (private mode, disabled) -- fail open, keep defaultOpen.
    }
    // Only re-sync if the tile id itself changes; this must not re-run on
    // every render or it would stomp the user's own toggles.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const update = (next: boolean): void => {
    setOpen(next);
    try {
      window.localStorage.setItem(storageKey(id), next ? "1" : "0");
    } catch {
      // Fail open -- in-memory state still works for this session.
    }
  };

  return [open, update];
}
