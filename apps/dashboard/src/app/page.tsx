"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getQueue, type ScheduledPost } from "@/lib/api";
export default function Home() {
  const [next, setNext] = useState<ScheduledPost>();
  useEffect(() => { getQueue().then((posts) => setNext(posts.find((post) => post.status === "scheduled"))).catch(() => undefined); }, []);
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Your publishing desk</p>
          <h1>A little more room to create.</h1>
          <p>Prepare your content. Plan when it goes out.</p>
        </div>
        <Link className="button" href="/content#add-content">
          Add content
        </Link>
      </header>
      <div className="cards">
        <section className="card">
          <p className="eyebrow">Next scheduled post</p>
          <h2>{next ? String(next.metadata.title ?? next.metadata.caption ?? "Untitled") : "Your schedule starts here"}</h2>
          <p>{next?.scheduled_at ? new Date(next.scheduled_at).toLocaleString() : "No scheduled posts yet."}</p>
          <Link href="/schedule">View schedule →</Link>
        </section>
        <section className="card">
          <p className="eyebrow">Recommended posting time</p>
          <h2>No recommendation yet</h2>
          <p>
            CreatorOS does not invent recommended times. Recommendations remain unavailable.
          </p>
          <span className="badge">Not available yet</span>
        </section>
      </div>
      <section className="card">
        <h2>Recent publishing activity</h2>
        <p>
          Automatic publishing is not available yet. You can browse existing
          video records in Content.
        </p>
        <Link href="/content">Open content →</Link>
      </section>
    </>
  );
}
