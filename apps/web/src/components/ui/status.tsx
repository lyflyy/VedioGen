import { AlertTriangle, CheckCircle2, CircleDashed, CircleX, Clock3 } from "lucide-react";

import { cn } from "@/lib/cn";

const labels: Record<string, string> = {
  intake: "待完善",
  advising: "策略确认",
  brief_draft: "Brief 待确认",
  brief_approved: "Brief 已确认",
  storyboard_draft: "分镜待确认",
  storyboard_approved: "分镜已确认",
  generating: "生成中",
  needs_attention: "需要处理",
  completed: "已完成",
  active: "可用",
  ready: "就绪",
  degraded: "降级",
  disabled: "已停用",
  draft: "草稿",
  published: "已发布",
  succeeded: "已完成",
  superseded: "已取代",
  failed: "失败",
};

export function Status({ value }: { value: string }) {
  const tone = value.includes("failed") || value === "needs_attention" ? "danger" : value.includes("completed") || value === "ready" || value === "active" || value === "published" || value === "succeeded" ? "success" : value === "degraded" ? "warning" : "neutral";
  const Icon = tone === "success" ? CheckCircle2 : tone === "danger" ? CircleX : tone === "warning" ? AlertTriangle : value.includes("ing") ? CircleDashed : Clock3;
  return (
    <span className={cn("status", `status-${tone}`)}>
      <Icon size={14} aria-hidden="true" />
      {labels[value] ?? value}
    </span>
  );
}
