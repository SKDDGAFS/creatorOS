"use client";
import { useEffect, useState } from "react";
import { getVideos, prepareVideo, updateVideo, type Video } from "@/lib/api";
export function ContentList() {
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [reviewVideo, setReviewVideo] = useState<Video | null>(null);
  const [draft, setDraft] = useState({
    title: "",
    description: "",
    caption: "",
    tags: "",
    hashtags: "",
  });
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewMessage, setReviewMessage] = useState("");
  const [state, setState] = useState<{
    kind: "loading" | "error" | "ready";
    videos: Video[];
  }>({ kind: "loading", videos: [] });
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    let active = true;
    setState({ kind: "loading", videos: [] });
    getVideos(offset, controller.signal, 20, attempt)
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
                ? "No videos yet. Upload a file or scan the local watch folder."
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
                    <th>Review</th>
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
                      <td>
                        <button
                          type="button"
                          className="button-secondary"
                          onClick={() => {
                            setReviewVideo(video);
                            const fields = video.draft_metadata?.fields ?? {};
                            const text = (key: string) => {
                              const value = fields[key];
                              return Array.isArray(value)
                                ? value.join(" ")
                                : typeof value === "string"
                                  ? value
                                  : "";
                            };
                            setDraft({
                              title: text("title") || video.title,
                              description: text("description"),
                              caption: text("caption"),
                              tags: text("tags"),
                              hashtags: text("hashtags"),
                            });
                            setReviewMessage("");
                          }}
                        >
                          Review
                        </button>
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
      {reviewVideo && (
        <div className="review-panel" aria-busy={reviewBusy}>
          <h3>Review draft: {reviewVideo.title}</h3>
          <p>
            {reviewVideo.platform} · {reviewVideo.status}
          </p>
          <div className="review-grid">
            {reviewVideo.platform === "youtube" ? (
              <>
                <label>
                  Title
                  <input
                    value={draft.title}
                    maxLength={100}
                    onChange={(event) =>
                      setDraft({ ...draft, title: event.target.value })
                    }
                  />
                </label>
                <label>
                  Description
                  <textarea
                    value={draft.description}
                    maxLength={5000}
                    onChange={(event) =>
                      setDraft({ ...draft, description: event.target.value })
                    }
                  />
                </label>
                <label>
                  Tags
                  <input
                    value={draft.tags}
                    onChange={(event) =>
                      setDraft({ ...draft, tags: event.target.value })
                    }
                  />
                </label>
              </>
            ) : (
              <>
                <label>
                  Caption
                  <textarea
                    value={draft.caption}
                    maxLength={2200}
                    onChange={(event) =>
                      setDraft({ ...draft, caption: event.target.value })
                    }
                  />
                </label>
                <label>
                  Hashtags
                  <input
                    value={draft.hashtags}
                    onChange={(event) =>
                      setDraft({ ...draft, hashtags: event.target.value })
                    }
                  />
                </label>
              </>
            )}
          </div>
          <div className="actions">
            <button
              type="button"
              disabled={reviewBusy || !reviewVideo.media_path}
              onClick={async () => {
                setReviewBusy(true);
                setReviewMessage("Preparing locally…");
                try {
                  const prepared = await prepareVideo(reviewVideo.id);
                  setReviewVideo(prepared);
                  const fields = prepared.draft_metadata?.fields ?? {};
                  const text = (key: string) => {
                    const value = fields[key];
                    return Array.isArray(value)
                      ? value.join(" ")
                      : typeof value === "string"
                        ? value
                        : "";
                  };
                  setDraft({
                    title: text("title") || prepared.title,
                    description: text("description"),
                    caption: text("caption"),
                    tags: text("tags"),
                    hashtags: text("hashtags"),
                  });
                  setState((current) =>
                    current.kind === "ready"
                      ? {
                          ...current,
                          videos: current.videos.map((video) =>
                            video.id === prepared.id ? prepared : video,
                          ),
                        }
                      : current,
                  );
                  setReviewMessage(
                    "Local transcript and draft are ready to review.",
                  );
                } catch (error) {
                  setReviewMessage(
                    error instanceof Error
                      ? error.message
                      : "Preparation failed",
                  );
                } finally {
                  setReviewBusy(false);
                }
              }}
            >
              Generate transcript and draft
            </button>
            <button
              type="button"
              className="button-secondary"
              disabled={reviewBusy}
              onClick={async () => {
                setReviewBusy(true);
                try {
                  const fields =
                    reviewVideo.platform === "youtube"
                      ? {
                          title: draft.title,
                          description: draft.description,
                          tags: draft.tags
                            .split(",")
                            .map((tag) => tag.trim())
                            .filter(Boolean),
                        }
                      : {
                          caption: draft.caption,
                          hashtags: draft.hashtags.split(/\s+/).filter(Boolean),
                        };
                  const saved = await updateVideo(reviewVideo.id, {
                    ...(reviewVideo.platform === "youtube"
                      ? { title: draft.title }
                      : {}),
                    draft_metadata: {
                      platform: reviewVideo.platform,
                      fields,
                    },
                  });
                  setReviewVideo(saved);
                  setState((current) =>
                    current.kind === "ready"
                      ? {
                          ...current,
                          videos: current.videos.map((video) =>
                            video.id === saved.id ? saved : video,
                          ),
                        }
                      : current,
                  );
                  setReviewMessage(
                    "Draft saved locally. Nothing was published.",
                  );
                } catch (error) {
                  setReviewMessage(
                    error instanceof Error
                      ? error.message
                      : "Could not save draft",
                  );
                } finally {
                  setReviewBusy(false);
                }
              }}
            >
              Save draft
            </button>
            <button
              type="button"
              className="button-secondary"
              onClick={() => setReviewVideo(null)}
            >
              Close review
            </button>
          </div>
          {reviewVideo.transcript && (
            <details>
              <summary>Transcript</summary>
              <p>{reviewVideo.transcript}</p>
            </details>
          )}
          {reviewVideo.ai_analysis && (
            <details>
              <summary>Local analysis</summary>
              <pre>{JSON.stringify(reviewVideo.ai_analysis, null, 2)}</pre>
            </details>
          )}
          {reviewMessage && <p role="status">{reviewMessage}</p>}
        </div>
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
