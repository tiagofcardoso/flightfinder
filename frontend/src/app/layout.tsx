import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AeroMilhas - AI Flight Finder Agent",
  description: "Encontre as passagens aéreas mais baratas e melhores opções com assistência de inteligência artificial.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt" className="h-full antialiased dark">
      <body className="min-h-full flex flex-col font-sans">
        {children}
      </body>
    </html>
  );
}
