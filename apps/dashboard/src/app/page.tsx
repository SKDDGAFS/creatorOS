"use client";
import {useEffect, useState} from "react";

export default function Home() {
  const [status, setStatus] = useState("Connecting...");

  useEffect(() => {
    fetch("http://127.0.0.1:8000")
      .then((res) => res.json())
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

        {/* Sidebar */}
        <aside className="w-64 min-h-screen border-r border-gray-800 p-6">
          <h1 className="text-2xl font-bold mb-8">
            CreatorOS
          </h1>

          <nav className="space-y-4 text-gray-300">
            <p>🏠 Home</p>
            <p>📊 Analytics</p>
            <p>🚀 Publishing</p>
            <p>🔍 Research</p>
            <p>💡 Ideas</p>
            <p>🤖 AI Chat</p>
            <p>🧠 Learning</p>
          </nav>
        </aside>


        {/* Main Content */}
        <section className="flex-1 p-10">

          <h2 className="text-4xl font-bold">
            Welcome back 👋
          </h2>

          <p className="text-gray-400 mt-2">
            Your AI creator assistant is ready.
          </p>

          <p className="mt-5 text-green-400">
            {status}
          </p>  

          <div className="grid grid-cols-3 gap-6 mt-10">

            <div className="rounded-xl border border-gray-800 p-6">
              <h3 className="text-gray-400">
                Views
              </h3>
              <p className="text-3xl font-bold mt-2">
                --
              </p>
            </div>


            <div className="rounded-xl border border-gray-800 p-6">
              <h3 className="text-gray-400">
                Subscribers
              </h3>
              <p className="text-3xl font-bold mt-2">
                --
              </p>
            </div>


            <div className="rounded-xl border border-gray-800 p-6">
              <h3 className="text-gray-400">
                AI Recommendations
              </h3>
              <p className="text-3xl font-bold mt-2">
                --
              </p>
            </div>

          </div>

        </section>

      </div>
    </main>
  );
}