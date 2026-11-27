import type { Metadata, Viewport } from "next";
import BottomNav from "@/components/BottomNav";
import SwRegister from "@/components/SwRegister";
import "./globals.css";

export const metadata: Metadata = {
  title: "Hermes",
  description: "해외 AI·Tech·Bio 인물의 글을 한국어 카드로",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "Hermes", statusBarStyle: "default" },
  icons: { icon: "/icon-192.png", apple: "/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f6f6f4" },
    { media: "(prefers-color-scheme: dark)", color: "#111214" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-dvh">
        <main className="mx-auto w-full max-w-md px-4 pt-[max(env(safe-area-inset-top),12px)] pb-24">{children}</main>
        <BottomNav />
        <SwRegister />
      </body>
    </html>
  );
}
