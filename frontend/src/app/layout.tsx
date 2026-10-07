import type { Metadata } from "next";
import { Anek_Devanagari, Anek_Latin, IBM_Plex_Mono } from "next/font/google";

import "./globals.css";

const anek = Anek_Latin({ subsets: ["latin"], variable: "--font-anek", axes: ["wdth"] });
const anekDeva = Anek_Devanagari({ subsets: ["devanagari"], variable: "--font-anek-deva", axes: ["wdth"] });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-mono" });

export const metadata: Metadata = {
  title: "AutoTax",
  description: "Nepal payroll and salary TDS, worked out from the Finance Act.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${anek.variable} ${anekDeva.variable} ${plexMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
