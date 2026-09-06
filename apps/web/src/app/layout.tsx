import type { Metadata } from "next";
import type { ReactNode } from "react";

import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

export const metadata: Metadata = {
  title: "VedioGen",
  description: "AI 辅助短视频创作工作台",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body><TooltipProvider>{children}</TooltipProvider></body>
    </html>
  );
}
