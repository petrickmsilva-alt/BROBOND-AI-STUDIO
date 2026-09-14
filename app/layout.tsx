import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BROBOND AI STUDIO",
  description: "A private creative operating system for cinematic generative media.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
