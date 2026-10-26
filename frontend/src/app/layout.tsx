import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VANTAGE | Portfolio Intelligence",
  description:
    "Read-only portfolio risk and quantitative research. Transparent data. Reproducible analytics.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
