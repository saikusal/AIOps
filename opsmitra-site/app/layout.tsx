import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OpsMitra | The AIDevOps Control Plane",
  description:
    "OpsMitra is an AI-native AIDevOps control plane for code-aware incident intelligence, safe remediation, and sovereign operations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
