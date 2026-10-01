"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  type DashboardSnapshot,
  getDashboardSnapshot,
  type Video,
  type VideoMetric,
} from "@/lib/api";

const numberFormat = new Intl.NumberFormat();
const platforms = ["youtube", "instagram", "tiktok"] as const;

export default function Home() {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot>();
  const [error, setError] = useState("");
  const [today, setToday] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = setTimeout(() => controller.abort(), 10000);
    setSnapshot(undefined);
    setError("");
    getDashboardSnapshot(controller.signal)
      .then(setSnapshot)
      .catch((caught: unknown) => {
        if (active) {
          setError(
            controller.signal.aborted
              ? "The local API request timed out"
              : caught instanceof Error
                ? caught.message
                : "Dashboard unavailable",
          );
        }
      })
      .finally(() => clearTimeout(timeout));
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  useEffect(() => {
    setToday(
      new Intl.DateTimeFormat(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(new Date()),
    );
  }, []);

  const latestMetricEntries: { video: Video; metric: VideoMetric }[] = [];
  if (snapshot) {
    for (const video of snapshot.recentVideos) {
      const metric = snapshot.latestMetrics[video.id];
      if (metric) latestMetricEntries.push({ video, metric });
    }
  }

  const views = latestMetricEntries.reduce(
    (total, entry) => total + entry.metric.views,
    0,
  );
  const interactions = latestMetricEntries.reduce(
    (total, entry) =>
      total + entry.metric.likes + entry.metric.comments + entry.metric.shares,
    0,
  );
  const impressions = latestMetricEntries.reduce(
    (total, entry) => total + entry.metric.impressions,
    0,
  );
  const weightedClickThrough = latestMetricEntries.reduce(
    (total, entry) =>
      total +
      entry.metric.impressions * Number(entry.metric.click_through_rate),
    0,
  );
  const averageViewDuration = latestMetricEntries.length
    ? Math.round(
        latestMetricEntries.reduce(
          (total, entry) => total + entry.metric.average_view_duration_seconds,
          0,
        ) / latestMetricEntries.length,
      )
    : null;
  const scheduledPosts = snapshot?.posts
    .filter((post) => post.status === "scheduled" && post.scheduled_at)
    .sort(
      (first, second) =>
        Date.parse(first.scheduled_at ?? "") -
        Date.parse(second.scheduled_at ?? ""),
    );
  const maxViews = Math.max(
    1,
    ...latestMetricEntries.map((entry) => entry.metric.views),
  );
  const chartEntries = [...latestMetricEntries]
    .sort((first, second) => second.metric.views - first.metric.views)
    .slice(0, 8);

  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">CreatorOS / Overview</p>
          <h1>Creator dashboard</h1>
          <p>Content pipeline, publishing queue, and recorded performance.</p>
        </div>
        <div className="dashboard-toolbar">
          <p>{today}</p>
          <button type="button" onClick={() => window.location.reload()}>
            Refresh data
          </button>
        </div>
      </header>
      {!snapshot && !error && (
        <section className="dashboard-panel" role="status">
          Loading creator data…
        </section>
      )}
      {error && (
        <section className="dashboard-panel error-panel" role="alert">
          <h2>Dashboard data is unavailable</h2>
          <p>{error}. Check that the local API and database are running.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Retry
          </button>
        </section>
      )}
      {snapshot && (
        <>
          <section className="dashboard-stats" aria-label="Creator overview">
            <article className="stat-card">
              <p className="stat-label">Videos in library</p>
              <strong className="stat-value">
                {numberFormat.format(snapshot.videos.length)}
              </strong>
              <p className="stat-detail">Across all local targets</p>
            </article>
            <article className="stat-card">
              <p className="stat-label">Scheduled posts</p>
              <strong className="stat-value">
                {numberFormat.format(scheduledPosts?.length ?? 0)}
              </strong>
              <p className="stat-detail">Saved locally, not auto-published</p>
            </article>
            <article className="stat-card">
              <p className="stat-label">Views tracked</p>
              <strong className="stat-value">
                {numberFormat.format(views)}
              </strong>
              <p className="stat-detail">
                Latest snapshots · {latestMetricEntries.length} of{" "}
                {snapshot.recentVideos.length} newest videos
              </p>
            </article>
            <article className="stat-card">
              <p className="stat-label">Interactions</p>
              <strong className="stat-value">
                {numberFormat.format(interactions)}
              </strong>
              <p className="stat-detail">Likes, comments, and shares</p>
            </article>
          </section>

          <div className="dashboard-grid">
            <section className="dashboard-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">Analytics</p>
                  <h2>Latest performance</h2>
                  <p>
                    Most recent saved snapshot for each of the 12 newest videos.
                  </p>
                </div>
                <Link href="/content">Content library</Link>
              </div>
              {latestMetricEntries.length === 0 ? (
                <p className="empty-state">
                  No performance snapshots recorded yet. Metrics will appear
                  here when added to a video.
                </p>
              ) : (
                <>
                  <div className="performance-totals">
                    <div className="performance-total">
                      <span>Impressions</span>
                      <strong>{numberFormat.format(impressions)}</strong>
                    </div>
                    <div className="performance-total">
                      <span>Avg. view duration</span>
                      <strong>
                        {averageViewDuration === null
                          ? "Not tracked"
                          : `${averageViewDuration}s`}
                      </strong>
                    </div>
                    <div className="performance-total">
                      <span>Impression CTR</span>
                      <strong>
                        {impressions > 0
                          ? `${((weightedClickThrough / impressions) * 100).toFixed(1)}%`
                          : "Not tracked"}
                      </strong>
                    </div>
                  </div>
                  <div className="chart-list">
                    {chartEntries.map(({ video, metric }) => (
                      <div className="chart-row" key={video.id}>
                        <span className="chart-title" title={video.title}>
                          {video.title}
                        </span>
                        <span className="chart-track">
                          <span
                            className="chart-bar"
                            style={{
                              width: `${(metric.views / maxViews) * 100}%`,
                            }}
                          />
                        </span>
                        <span className="chart-value">
                          {numberFormat.format(metric.views)}
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </section>

            <div className="panel-stack">
              <section className="dashboard-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Publishing</p>
                    <h2>Upcoming queue</h2>
                  </div>
                  <Link href="/schedule">View all</Link>
                </div>
                {scheduledPosts?.length ? (
                  <div className="queue-list">
                    {scheduledPosts.slice(0, 4).map((post) => (
                      <div className="queue-row" key={post.id}>
                        <div>
                          <strong>
                            {String(
                              post.metadata.title ??
                                post.metadata.caption ??
                                "Untitled post",
                            )}
                          </strong>
                          <span>
                            {post.platform} · {post.timezone}
                          </span>
                        </div>
                        <span>
                          {new Date(post.scheduled_at ?? "").toLocaleString(
                            undefined,
                            {
                              month: "short",
                              day: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                            },
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="empty-state">
                    No upcoming posts in the local queue.
                  </p>
                )}
              </section>

              <section className="dashboard-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Accounts</p>
                    <h2>Platform targets</h2>
                  </div>
                  <Link href="/connections">Manage</Link>
                </div>
                <div className="channel-list">
                  {platforms.map((platform) => {
                    const channel = snapshot.channels.find(
                      (item) => item.platform === platform,
                    );
                    return (
                      <div className="channel-row" key={platform}>
                        <div>
                          <strong>{channel?.name ?? platform}</strong>
                          <span>{platform}</span>
                        </div>
                        <span
                          className={
                            channel?.is_authorized ? "status-connected" : ""
                          }
                        >
                          {channel?.is_authorized
                            ? "Connected"
                            : channel
                              ? "Local target"
                              : "Not set up"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </section>
            </div>
          </div>

          <section className="dashboard-panel recent-content">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Library</p>
                <h2>Recently added</h2>
              </div>
              <Link href="/content">View library</Link>
            </div>
            {snapshot.recentVideos.length ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Video</th>
                      <th>Target</th>
                      <th>Status</th>
                      <th>Latest views</th>
                      <th>Added</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.recentVideos.slice(0, 6).map((video) => {
                      const metric = snapshot.latestMetrics[video.id];
                      const channel = snapshot.channels.find(
                        (item) => item.id === video.channel_id,
                      );
                      return (
                        <tr key={video.id}>
                          <td>{video.title}</td>
                          <td>{channel?.platform ?? "Unknown"}</td>
                          <td>
                            <span className="badge">{video.status}</span>
                          </td>
                          <td>
                            {metric
                              ? numberFormat.format(metric.views)
                              : "Not tracked"}
                          </td>
                          <td>
                            {new Date(video.created_at).toLocaleDateString(
                              undefined,
                              {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              },
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="empty-state">
                No videos yet. Import or upload content to start your library.
              </p>
            )}
          </section>

          <div className="dashboard-links">
            <Link href="/content">Prepare content</Link>
            <Link href="/schedule">Open schedule</Link>
            <span>
              Metrics shown are saved snapshots, not live platform data.
            </span>
          </div>
        </>
      )}
    </>
  );
}
