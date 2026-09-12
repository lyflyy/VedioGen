"use client";

import { Check, Cloud, Copy, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { post } from "@/lib/api";

import { Status } from "@/components/ui/status";
import { Tooltip } from "@/components/ui/tooltip";
import type { Project } from "@/lib/types";

const stages = [
  ["intake", "资料"],
  ["strategy", "策略"],
  ["brief", "Brief"],
  ["storyboard", "脚本分镜"],
  ["generation", "生成"],
  ["final", "成片"],
] as const;

export function ProjectHeader({ project, activeStage, unsaved = false }: { project: Project; activeStage: string; unsaved?: boolean }) {
  const router = useRouter();
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState("");
  async function reuse() {
    setCopying(true); setError("");
    try {
      const next = await post<Project>(`/projects/${project.id}/copies`);
      router.push(`/projects/${next.id}/storyboard`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "复用项目失败"); }
    finally { setCopying(false); }
  }
  return (
    <header className="project-header">
      <div className="project-title-row">
        <div className="project-title-wrap">
          <Link href="/projects" className="back-link">项目</Link>
          <span className="crumb-separator">/</span>
          <h1>{project.title}</h1>
        </div>
        <div className="project-meta">
          <span className="save-state"><Cloud size={15} />{unsaved ? "有未保存修改" : <><Check size={12} /> 已保存</>}</span>
          <Status value={project.status} />
          {project.currentStoryboardVersionId ? <Tooltip label="复用脚本与素材">
            <button className="icon-button" aria-label="复用脚本与素材" disabled={copying || unsaved} onClick={() => void reuse()}>{copying ? <LoaderCircle className="spin" size={18} /> : <Copy size={18} />}</button>
          </Tooltip> : null}
        </div>
      </div>
      {error ? <p role="alert">{error}</p> : null}
      <nav className="step-nav" aria-label="项目步骤">
        {stages.map(([stage, label], index) => (
          <Link key={stage} href={`/projects/${project.id}/${stage}`} aria-current={activeStage === stage ? "step" : undefined} className="step-link">
            <span className="step-index">{index + 1}</span>{label}
          </Link>
        ))}
        <Link href={`/projects/${project.id}/logs`} className="step-link" aria-current={activeStage === "logs" ? "page" : undefined}>执行日志</Link>
      </nav>
    </header>
  );
}
