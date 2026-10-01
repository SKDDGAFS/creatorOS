"use client";
import { useEffect, useState } from "react";
import { getVideos, type Video } from "@/lib/api";
export function ContentList() {
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    kind: "loading" | "error" | "ready";
    videos: Video[];
  }>({ kind: "loading", videos: [] });
  // biome-ignore lint/correctness/useExhaustiveDependencies: attempt explicitly triggers a retry of the same page.
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    let active = true;
    setState({ kind: "loading", videos: [] });
    getVideos(offset, controller.signal)
      .then((videos) => {
        if (active) setState({ kind: "ready", videos });
      })
      .catch(() => {
        if (active) setState({ kind: "error", videos: [] });
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [offset, attempt]);
  return (
    <section
      className="card"
      aria-label="Video library"
      aria-busy={state.kind === "loading"}
    >
      <h2>Video library</h2>
      {state.kind === "loading" && <p role="status">Loading your content…</p>}
      {state.kind === "error" && (
        <div role="alert">
          <p>
            Could not load content. Check that your local API is running, then
            try again.
          </p>
          <button type="button" onClick={() => setAttempt(attempt + 1)}>
            Try again
          </button>
        </div>
      )}
      {state.kind === "ready" && (
        <>
          {state.videos.length === 0 ? (
            <p>
              {offset === 0
                ? "No video records yet. Uploads will be available in a later sprint."
                : "No more video records."}
            </p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Published</th>
                  </tr>
                </thead>
                <tbody>
                  {state.videos.map((video) => (
                    <tr key={video.id}>
                      <td>{video.title}</td>
                      <td>
                        <span className="badge">{video.status}</span>
                      </td>
                      <td>
                        {video.published_at
                          ? new Date(video.published_at).toLocaleString()
                          : "Not published"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p>
            Statuses come from existing records. A “scheduled” status does not
            trigger publishing.
          </p>
        </>
      )}
      <div className="actions">
        <button
          type="button"
          disabled={offset === 0 || state.kind === "loading"}
          onClick={() => setOffset(Math.max(0, offset - 20))}
        >
          Previous
        </button>
        <p>Page {offset / 20 + 1}</p>
        <button
          type="button"
          disabled={state.kind !== "ready" || state.videos.length < 20}
          onClick={() => setOffset(offset + 20)}
        >
          Next
        </button>
      </div>
    </section>
  );
}
