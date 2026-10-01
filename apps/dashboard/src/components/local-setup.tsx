"use client";
import { useState } from "react";
import { setupLocal, type Channel } from "@/lib/api";

export function LocalSetup({ onReady }: { onReady: (channels: Channel[]) => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function prepare() {
    setBusy(true); setError("");
    try { onReady(await setupLocal()); } catch (caught) { setError(caught instanceof Error ? caught.message : "Setup failed"); } finally { setBusy(false); }
  }
  return <div className="actions"><button type="button" onClick={prepare} disabled={busy}>{busy ? "Preparing…" : "Prepare local channels"}</button>{error && <span role="alert">{error}</span>}</div>;
}