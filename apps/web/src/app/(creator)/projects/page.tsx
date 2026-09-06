"use client";

import { AlertCircle, ArrowUpRight, CalendarDays, Film, Plus, Search } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Status } from "@/components/ui/status";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    api<{ items: Project[] }>("/projects")
      .then((result) => setProjects(result.items))
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  const visible = projects.filter((item) => item.title.toLowerCase().includes(query.toLowerCase()));

  return (
    <div className="page-frame">
      <header className="page-header">
        <div><h1>项目</h1><p>继续处理待确认内容，或开始一条新视频。</p></div>
        <Button asChild><Link href="/projects/new"><Plus size={17} />新建项目</Link></Button>
      </header>

      <div className="filter-bar">
        <label className="search-field"><Search size={17} aria-hidden="true" /><span className="sr-only">搜索项目</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索项目" /></label>
        <div className="filter-segments" aria-label="项目状态"><button aria-pressed="true">全部</button><button>待确认</button><button>生成中</button><button>已完成</button></div>
      </div>

      {loading ? <ProjectSkeleton /> : error ? (
        <div className="inline-error" role="alert"><AlertCircle size={18} /><div><strong>项目暂时无法载入</strong><span>{error}</span></div></div>
      ) : visible.length ? (
        <section className="project-grid" aria-label="项目列表">
          {visible.map((item, index) => (
            <Link key={item.id} href={`/projects/${item.id}/${nextStage(item.status)}`} className="project-card">
              <div className="project-cover">
                <Image src={index % 2 ? "/images/motorcycle-studio.jpg" : "/images/motorcycle-road.jpg"} alt="摩托车项目预览" fill sizes="(max-width: 760px) 100vw, 360px" />
                <Status value={item.status} />
              </div>
              <div className="project-card-body">
                <div><h2>{item.title}</h2><p>摩托车内容包 · 抖音竖屏</p></div>
                <ArrowUpRight size={19} aria-hidden="true" />
              </div>
              <div className="project-card-meta"><span><CalendarDays size={14} />{formatDate(item.updatedAt)}</span><span><Film size={14} />{stageLabel(item.status)}</span></div>
            </Link>
          ))}
        </section>
      ) : (
        <section className="empty-projects">
          <div className="empty-project-image"><Image src="/images/motorcycle-studio.jpg" alt="摄影棚中的摩托车" fill priority sizes="(max-width: 760px) 100vw, 55vw" /></div>
          <div className="empty-project-copy"><span className="section-kicker">首条内容</span><h2>从一个车型和一个镜头想法开始</h2><p>系统会先整理事实、给出可比较的创意方向，再进入脚本和生成。</p><Button asChild><Link href="/projects/new"><Plus size={17} />新建项目</Link></Button></div>
        </section>
      )}
    </div>
  );
}

function ProjectSkeleton() {
  return <div className="project-grid" aria-label="正在载入项目"><div className="project-card skeleton-card" /><div className="project-card skeleton-card" /></div>;
}

function nextStage(status: Project["status"]) {
  if (status === "intake" || status === "advising") return "strategy";
  if (status.startsWith("brief")) return "brief";
  if (status.startsWith("storyboard")) return "storyboard";
  if (status === "generating" || status === "needs_attention") return "generation";
  return "final";
}

function stageLabel(status: Project["status"]) {
  return { intake: "资料", advising: "策略", brief_draft: "Brief", brief_approved: "Brief", storyboard_draft: "分镜", storyboard_approved: "分镜", generating: "生成", needs_attention: "生成", completed: "成片" }[status];
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
