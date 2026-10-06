import { Suspense } from "react";
import AdminPanel from "../components/AdminPanel";

export default function AdminPage() {
  return (
    <Suspense fallback={<p className="empty-msg">Loading admin page…</p>}>
      <AdminPanel />
    </Suspense>
  );
}
