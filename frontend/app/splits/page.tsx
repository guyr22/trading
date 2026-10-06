"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../contexts/AuthContext";
import StockSplits from "../components/StockSplits";

export default function SplitsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && user?.is_admin) router.replace("/admin?tab=splits");
  }, [loading, user, router]);

  if (loading || !user || user.is_admin) return null;
  return <StockSplits />;
}
