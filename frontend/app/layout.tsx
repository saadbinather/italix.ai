import type { Metadata } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import "./globals.css";

export const metadata: Metadata = {
  title: "ITALIX.ai — AI Infrastructure",
  description: "Local-first AI infrastructure control plane",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable} h-full dark antialiased`}
    >
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
