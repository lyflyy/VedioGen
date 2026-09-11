"use client";

import { Check, LoaderCircle, AlertCircle } from "lucide-react";
import { useEffect, useState } from "react";

export interface PreparationRun {
  id: string;
  status: string;
  phase: string;
  createdAt: string;
  storyboardVersionId: string | null;
  errorMessage: string | null;
  warnings: string[];
}
const phases = [
  ["queued", "任务已提交"], ["preparing-assets", "准备项目参考素材"],
  ["writing-script", "大模型正在生成脚本"], ["matching-assets", "匹配镜头与素材"],
  ["checking-shots", "检查镜头执行条件"], ["completed", "脚本已就绪"],
];

export function PreparationProgress({ run }: { run: PreparationRun }) {
  const [now, setNow] = useState(() => Date.now());
  const active = ["queued", "running"].includes(run.status);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  const index = phases.findIndex(([phase]) => phase === run.phase);
  return <section className="preparation-progress" aria-label="脚本生成进度" aria-busy={active}>
    <div className="preparation-heading">
      <strong>{active ? "正在准备脚本与素材" : run.status === "completed" ? "脚本准备完成" : "脚本准备未完成"}</strong>
      {active ? <span>已等待 {Math.max(0, Math.floor((now - Date.parse(run.createdAt)) / 1000))} 秒</span> : null}
    </div>
    <ol>{phases.map(([phase, label], i) => <li key={phase} data-current={i === index} data-completed={i < index}>
      {i < index || run.status === "completed" ? <Check size={15} /> : i === index && active ? <LoaderCircle size={15} className="spin" /> : <span className="phase-dot" />}
      <span>{label}</span>
    </li>)}</ol>
    <p role="status">{active ? phases[index]?.[1] ?? "等待执行" : run.errorMessage ?? "可以查看并调整分镜"}</p>
    {run.warnings.map((warning) => <p key={warning} className="preparation-warning"><AlertCircle size={14} />{warning}</p>)}
  </section>;
}
