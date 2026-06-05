"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "../contexts/AuthContext";
import { useState } from "react";
import { createInvite } from "../api";

const NAV_ALL = [
  { href: "/", label: "Dashboard" },
  { href: "/history", label: "History" },
  { href: "/indexes", label: "Indexes" },
  { href: "/statistics", label: "Statistics" },
  { href: "/alerts", label: "Alerts" },
  { href: "/chat", label: "AI" },
];

const NAV_ADMIN = [
  ...NAV_ALL,
  { href: "/leveraged-etfs", label: "Lev. ETFs" },
];

export default function NavBar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  if (pathname === "/login" || pathname === "/register") return null;
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [inviteLoading, setInviteLoading] = useState(false);

  const handleInvite = async () => {
    setInviteLoading(true);
    try {
      const token = await createInvite();
      const base = window.location.origin;
      setInviteLink(`${base}/register?token=${token}`);
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Failed to create invite");
    } finally {
      setInviteLoading(false);
    }
  };

  const copyInvite = () => {
    if (inviteLink) {
      navigator.clipboard.writeText(inviteLink);
      alert("Invite link copied to clipboard!");
    }
  };

  return (
    <header>
      <h1>Portfolio Tracker</h1>
      <nav>
        {(user?.is_admin ? NAV_ADMIN : NAV_ALL).map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={`nav-btn ${pathname === href ? "active" : ""}`}
          >
            {label}
          </Link>
        ))}
      </nav>
      {user && (
        <div className="nav-user">
          <span className="nav-email">{user.email}</span>
          {user.is_admin && (
            <button
              className="nav-btn"
              onClick={handleInvite}
              disabled={inviteLoading}
              title="Generate invite link for a new user"
            >
              {inviteLoading ? "…" : "Invite"}
            </button>
          )}
          <button className="nav-btn nav-logout" onClick={logout}>
            Sign out
          </button>
        </div>
      )}
      {inviteLink && (
        <div className="invite-banner">
          <span className="invite-link">{inviteLink}</span>
          <button className="nav-btn" onClick={copyInvite}>Copy</button>
          <button className="nav-btn" onClick={() => setInviteLink(null)}>✕</button>
        </div>
      )}
    </header>
  );
}
