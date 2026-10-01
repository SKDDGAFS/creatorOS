"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getQueue, updatePost, type ScheduledPost } from "@/lib/api";
export default function Schedule() {
  const [posts, setPosts] = useState<ScheduledPost[]>([]);
  const [error, setError] = useState("");
  function refresh() { getQueue().then(setPosts).catch((caught) => setError(caught instanceof Error ? caught.message : "Queue unavailable")); }
  useEffect(refresh, []);
  async function cancel(id: string) { await updatePost(id, { status: "cancelled" }); refresh(); }
  async function reschedule(post: ScheduledPost) { const value = window.prompt("New local date/time", post.scheduled_at ? post.scheduled_at.slice(0, 16) : ""); if (value) { await updatePost(post.id, { scheduled_at: new Date(value).toISOString(), status: "scheduled" }); refresh(); } }
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Plan your next post</p>
          <h1>Schedule</h1>
          <p>A simple place for upcoming content.</p>
        </div>
      </header>
      <section className="card">
        <h2>Upcoming posts</h2>
        <p className="notice">Local queue only. Nothing here publishes to a platform.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Content</th>
                <th>Platform</th>
                <th>Scheduled time</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {posts.length === 0 && <tr><td colSpan={5}>Your queue is empty.</td></tr>}
              {posts.map((post) => <tr key={post.id}><td>{String(post.metadata.title ?? post.metadata.caption ?? "Untitled")}</td><td>{post.platform}</td><td>{post.scheduled_at ? new Date(post.scheduled_at).toLocaleString() : "Draft"}</td><td><span className="badge">{post.status}</span></td><td>{post.status !== "cancelled" && <><button type="button" onClick={() => reschedule(post)}>Reschedule</button> <button type="button" onClick={() => cancel(post.id)}>Cancel</button></>}</td></tr>)}
            </tbody>
          </table>
        </div>
        {error && <p role="alert">{error}</p>}<div className="actions">
          <Link href="/content">Browse content →</Link>
        </div>
      </section>
    </>
  );
}
