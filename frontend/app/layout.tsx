import type { Metadata, Viewport } from "next";
import "./globals.css";
import NavBar from "./components/NavBar";
import { AuthProvider } from "./contexts/AuthContext";

export const metadata: Metadata = {
  title: "Portfolio Tracker",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <NavBar />
          <main>{children}</main>
        </AuthProvider>
      </body>
    </html>
  );
}
