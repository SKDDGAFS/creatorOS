"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const pages = [
  ["/", "Home"],
  ["/schedule", "Schedule"],
  ["/content", "Content"],
  ["/connections", "Connections"],
  ["/settings", "Settings"],
];
export function Navigation() {
  const pathname = usePathname();
  return (
    <nav aria-label="Main navigation">
      {pages.map(([href, label]) => (
        <Link
          key={href}
          href={href}
          aria-current={pathname === href ? "page" : undefined}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
