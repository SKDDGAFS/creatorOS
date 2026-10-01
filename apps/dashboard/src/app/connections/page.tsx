export default function Connections() {
  return (
    <>
      <header className="page-header">
        <div>
          <p className="eyebrow">Your platforms</p>
          <h1>Connections</h1>
          <p>
            Platform connections will be added one at a time, starting with
            YouTube.
          </p>
        </div>
      </header>
      {["YouTube", "Instagram", "TikTok"].map((platform) => (
        <section className="card" key={platform}>
          <h2>{platform}</h2>
          <span className="badge">Not connected · Coming later</span>
          <p>
            Authorization and publishing for {platform} are not available yet.
          </p>
        </section>
      ))}
      <p>
        These are placeholder states. Existing channel records do not represent
        an authorized platform connection.
      </p>
    </>
  );
}
