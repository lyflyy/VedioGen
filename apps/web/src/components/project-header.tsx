"use client";

import { Check, Cloud, MoreHorizontal } from "lucide-react";
import Link from "next/link";

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

export function ProjectHeader({ project, activeStage }: { project: Project; activeStage: string }) {
  return (
    <header className="project-header">
      <div className="project-title-row">
        <div className="project-title-wrap">
          <Link href="/projects" className="back-link">项目</Link>
          <span className="crumb-separator">/</span>
          <h1>{project.title}</h1>
        </div>
        <div className="project-meta">
          <span className="save-state"><Cloud size={15} /><Check size={12} /> 已保存</span>
          <Status value={project.status} />
          <Tooltip label="项目操作">
            <button className="icon-button" aria-label="项目操作"><MoreHorizontal size={18} /></button>
          </Tooltip>
        </div>
      </div>
      <nav className="step-nav" aria-label="项目步骤">
        {stages.map(([stage, label], index) => (
          <Link key={stage} href={`/projects/${project.id}/${stage}`} aria-current={activeStage === stage ? "step" : undefined} className="step-link">
            <span className="step-index">{index + 1}</span>{label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
