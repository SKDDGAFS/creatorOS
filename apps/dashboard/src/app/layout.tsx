import type { Metadata } from "next";
import Link from "next/link";
import { Navigation } from "@/components/navigation";
import "./globals.css";
export const metadata: Metadata = {
  title: "CreatorOS",
  description: "Your private content scheduling and publishing assistant.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <div className="shell">
          <aside className="sidebar">
            <Link className="brand" href="/">
              CreatorOS<span>Personal publishing</span>
            </Link>
            <Navigation />
            <p className="local-note">
              Private · Local
              <br />
              One creator. Your own pace.
            </p>
          </aside>
          <main id="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
