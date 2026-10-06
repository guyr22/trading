"use client";

import { useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "../contexts/AuthContext";
import LeveragedEtfs from "./LeveragedEtfs";
import StockSplits from "./StockSplits";

const TABS = [
  { id: "etfs", label: "Lev. ETFs" },
  { id: "splits", label: "Splits" },
] as const;

export default function AdminPanel() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const tab = params.get("tab") === "splits" ? "splits" : "etfs";
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);

  useEffect(() => {
    if (!loading && user && !user.is_admin) router.replace("/");
  }, [loading, user, router]);

  if (loading) return <p className="empty-msg">Loading admin page…</p>;
  if (!user?.is_admin) return null;

  const selectTab = (index: number) => {
    router.replace(`/admin?tab=${TABS[index].id}`, { scroll: false });
  };

  return (
    <>
      <h2>Admin</h2>
      <div className="admin-tabs" role="tablist" aria-label="Admin tools">
        {TABS.map((item, index) => (
          <button
            key={item.id}
            ref={node => { buttons.current[index] = node; }}
            type="button"
            role="tab"
            id={`admin-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`admin-panel-${item.id}`}
            tabIndex={tab === item.id ? 0 : -1}
            className={`nav-btn ${tab === item.id ? "active" : ""}`}
            onClick={() => selectTab(index)}
            onKeyDown={event => {
              let next: number;
              if (event.key === "ArrowRight" || event.key === "ArrowLeft") next = (index + 1) % TABS.length;
              else if (event.key === "Home") next = 0;
              else if (event.key === "End") next = TABS.length - 1;
              else return;
              event.preventDefault();
              buttons.current[next]?.focus();
              selectTab(next);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <section role="tabpanel" id="admin-panel-etfs" aria-labelledby="admin-tab-etfs" hidden={tab !== "etfs"}>
        <LeveragedEtfs />
      </section>
      <section role="tabpanel" id="admin-panel-splits" aria-labelledby="admin-tab-splits" hidden={tab !== "splits"}>
        <StockSplits />
      </section>
    </>
  );
}
