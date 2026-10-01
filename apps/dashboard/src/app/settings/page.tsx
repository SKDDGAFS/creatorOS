"use client";
import { useEffect, useState } from "react";
export default function Settings() {
  const [timezone, setTimezone] = useState("Detecting…");
  useEffect(() => {
    setTimezone(Intl.DateTimeFormat().resolvedOptions().timeZone);
  }, []);
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Keep it simple</p>
          <h1>Settings</h1>
          <p>Local application preferences.</p>
        </div>
      </header>
      <section className="card">
        <h2>Current setup</h2>
        <dl>
          <dt>Mode</dt>
          <dd>Private, single user</dd>
          <dt>Display timezone</dt>
          <dd>{timezone}</dd>
          <dt>Time display</dt>
          <dd>Uses this browser’s timezone and locale.</dd>
        </dl>
      </section>
      <p>
        Read-only for now. Scheduling preferences will be added with the queue.
      </p>
    </>
  );
}
