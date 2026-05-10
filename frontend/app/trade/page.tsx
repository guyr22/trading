"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import TradeForm from "../components/TradeForm";

export default function TradePage() {
  const router = useRouter();
  return (
    <>
      <div style={{ marginBottom: "1.5rem" }}>
        <Link href="/" className="nav-btn" style={{ textDecoration: "none" }}>
          ← Return
        </Link>
      </div>
      <TradeForm onTradeCreated={() => router.push("/")} />
    </>
  );
}
