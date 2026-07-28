"use client";

import { useEffect, useState } from "react";

const apiUrl =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

export default function Home() {
  const [status, setStatus] = useState("Connecting...");

  useEffect(() => {
    fetch(apiUrl)
      .then((response) => response.json())
      .then((data) => {
        setStatus(data.message);
      })
      .catch(() => {
        setStatus("Backend offline");
      });
  }, []);

  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <div className="flex">
        <aside className="min-h-screen w-64 border-r border-gray-800 p-6">
          <h1 className="mb-8 text-2xl font-bold">CreatorOS</h1>

          <nav className="space-y-4 text-gray-300">
            <p>Home</p>
            <p>Analytics</p>
            <p>Publishing</p>
            <p>Research</p>
            <p>Ideas</p>
            <p>AI Chat</p>
            <p>Learning</p>
          </nav>
        </aside>

        <section className="flex-1 p-10">
          <h2 className="text-4xl font-bold">Welcome back</h2>

          <p className="mt-2 text-gray-400">
            Your AI creator assistant is ready.
          </p>

          <p className="mt-5 text-green-400">{status}</p>

          <div className="mt-10 grid grid-cols-3 gap-6">
            <div className="rounded-xl border border-gray-800 p-6">
              <h3 className="text-gray-400">Views</h3>
              <p className="mt-2 text-3xl font-bold">--</p>
            </div>

            <div className="rounded-xl border border-gray-800 p-6">
              <h3 className="text-gray-400">Subscribers</h3>
              <p className="mt-2 text-3xl font-bold">--</p>
            </div>

            <div className="rounded-xl border border-gray-800 p-6">
              <h3 className="text-gray-400">AI Recommendations</h3>
              <p className="mt-2 text-3xl font-bold">--</p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
