"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/history", label: "History" },
  { href: "/indexes", label: "Indexes" },
  { href: "/statistics", label: "Statistics" },
  { href: "/chat", label: "AI" },
  { href: "/leveraged-etfs", label: "Lev. ETFs" },
];

export default function NavBar() {
  const pathname = usePathname();

  return (
    <header>
      <h1>Portfolio Tracker</h1>
      <nav>
        {NAV.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={`nav-btn ${pathname === href ? "active" : ""}`}
          >
            {label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
