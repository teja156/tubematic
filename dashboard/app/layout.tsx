import type { Metadata } from "next";
import { TopBar } from "@/components/TopBar";
import { TimeZoneProvider } from "@/components/TimeZoneProvider";
import { UpdateBanner } from "@/components/UpdateBanner";
import "./globals.css";

export const metadata: Metadata = {
  title: "TubeMatic",
  description: "YouTube video production pipeline",
  icons: {
    icon: [
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-48.png", sizes: "48x48", type: "image/png" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
    ],
    apple: { url: "/favicon-180.png", sizes: "180x180", type: "image/png" },
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body>
        <TimeZoneProvider>
          <TopBar />
          <UpdateBanner />
          <main
            className="mx-auto"
            style={{
              maxWidth: 1640,
              paddingLeft: "var(--gutter)",
              paddingRight: "var(--gutter)",
              paddingBottom: 96,
              paddingTop: 28,
            }}
          >
            {children}
          </main>
        </TimeZoneProvider>
      </body>
    </html>
  );
}
