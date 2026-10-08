import type { Metadata } from "next";
import { Anek_Latin, Noto_Sans_Devanagari, Public_Sans } from "next/font/google";

import "./globals.css";

const publicSans = Public_Sans({ subsets: ["latin", "latin-ext"], variable: "--font-public-sans" });
const devanagari = Noto_Sans_Devanagari({ subsets: ["devanagari"], weight: ["400", "500", "600"], variable: "--font-deva" });
// Only for the tax-rules seal: its condensed rubber-stamp lettering.
const stampFace = Anek_Latin({ subsets: ["latin"], variable: "--font-stamp", axes: ["wdth"] });

export const metadata: Metadata = {
  title: "AutoTax",
  description: "Nepal payroll and salary TDS, worked out from the Finance Act.",
};

// Apply the saved theme before first paint (light / dark / match device).
const THEME_BOOT = `try{var t=localStorage.getItem("autotax-theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${publicSans.variable} ${devanagari.variable} ${stampFace.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
