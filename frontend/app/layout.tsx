import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import localFont from "next/font/local";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const ridiBatang = localFont({
  src: "./fonts/RIDIBatang.otf",
  variable: "--font-ridi-batang",
  display: "swap",
});

export const metadata: Metadata = {
  title: "TMTI | 협업 스타일 24문항",
  description: "팀 안에서의 협업 방식을 살펴보는 24문항 설문",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ko"
      className={`${geistSans.variable} ${geistMono.variable} ${ridiBatang.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
