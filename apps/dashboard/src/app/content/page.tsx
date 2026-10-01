"use client";
import { useEffect, useState } from "react";
import { ContentList } from "@/components/content-list";
import { LocalSetup } from "@/components/local-setup";
import { UploadPanel } from "@/components/upload-panel";
import { setupLocal, type Channel } from "@/lib/api";
export default function Content() {
  const [channels, setChannels] = useState<Channel[]>([]);
  useEffect(() => { setupLocal().then(setChannels).catch(() => setChannels([])); }, []);
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Your library</p>
          <h1>Content</h1>
          <p>Existing videos from your local CreatorOS library.</p>
        </div>
      </header>
      {channels.length === 0 ? <section className="card"><h2>Local preparation</h2><p>Set up local target channels for preparation. These records are not authorized platform connections.</p><LocalSetup onReady={setChannels} /></section> : <UploadPanel channels={channels} onUploaded={() => undefined} />}
      <ContentList />
    </>
  );
}
