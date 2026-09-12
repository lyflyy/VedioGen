"use client";

import { AlertCircle, ArrowUpRight, CalendarDays, ChevronLeft, ChevronRight, Film, Plus, RefreshCw, Search, Trash2, Undo2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Status } from "@/components/ui/status";
import { Tooltip } from "@/components/ui/tooltip";
import { api, post } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState("");
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true); setError("");
      const params = new URLSearchParams({ query, offset: String(offset), pageSize: "20", ...(filter ? { status: filter } : {}) });
      api<{ items: Project[]; total: number }>(`/projects?${params}`, { signal: controller.signal })
        .then((result) => { if (!controller.signal.aborted) { setProjects(result.items); setTotal(result.total); } })
        .catch((reason: Error) => { if (!controller.signal.aborted) setError(reason.message); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 180);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query, filter, offset, revision]);

  async function removeOrRestore(item: Project) {
    const restore = filter === "deleted";
    if (!restore && !window.confirm(`将“${item.title}”移入回收站？可以恢复，素材文件不会被永久删除。`)) return;
    setBusy(item.id); setActionError("");
    try {
      if (restore) await post(`/projects/${item.id}/restoration`);
      else await api(`/projects/${item.id}`, { method: "DELETE" });
      if (projects.length === 1 && offset > 0) setOffset(Math.max(0, offset - 20));
      setRevision(value => value + 1);
    } catch (reason) { setActionError(reason instanceof Error ? reason.message : "操作失败"); }
    finally { setBusy(""); }
  }

  return (
    <div className="page-frame">
      <header className="page-header">
        <div><h1>项目</h1><p>{total} 个项目</p></div>
        <Button asChild><Link href="/projects/new"><Plus size={17} />新建项目</Link></Button>
      </header>

      <div className="filter-bar">
        <label className="search-field"><Search size={17} aria-hidden="true" /><span className="sr-only">搜索项目</span><input value={query} onChange={(event) => { setQuery(event.target.value); setOffset(0); }} placeholder="搜索项目" /></label>
        <div className="filter-segments" role="group" aria-label="项目状态">{[["", "全部"], ["pending", "待确认"], ["generating", "生成中"], ["completed", "已完成"], ["deleted", "回收站"]].map(([value, label]) => <button key={value} aria-pressed={filter === value} onClick={() => { setFilter(value); setOffset(0); }}>{label}</button>)}</div>
        <Tooltip label="刷新项目"><button className="icon-button" aria-label="刷新项目" onClick={() => setRevision(value => value + 1)}><RefreshCw size={17} /></button></Tooltip>
      </div>
      {actionError ? <p role="alert" className="inline-error">{actionError}</p> : null}

      {loading ? <ProjectSkeleton /> : error ? (
        <div className="inline-error" role="alert"><AlertCircle size={18} /><div><strong>项目暂时无法载入</strong><span>{error}</span></div></div>
      ) : projects.length ? (
        <section className="project-grid" aria-label="项目列表">
          {projects.map((item, index) => (
            <article key={item.id} className="project-card">
            <Link href={filter === "deleted" ? "#" : `/projects/${item.id}/${item.activityRunning ? "logs" : nextStage(item.status)}`} aria-disabled={filter === "deleted"} onClick={event => { if (filter === "deleted") event.preventDefault(); }}>
              <div className="project-cover">
                <Image src={index % 2 ? "/images/motorcycle-studio.jpg" : "/images/motorcycle-road.jpg"} alt="摩托车项目预览" fill sizes="(max-width: 760px) 100vw, 360px" />
                <Status value={item.activityRunning ? "generating" : item.status} />
              </div>
              <div className="project-card-body">
                <div><h2>{item.title}</h2><p>摩托车内容包 · 抖音竖屏</p></div>
                <ArrowUpRight size={19} aria-hidden="true" />
              </div>
              <div className="project-card-meta"><span><CalendarDays size={14} />{formatDate(item.updatedAt)}</span><span><Film size={14} />{stageLabel(item.status)}</span></div>
            </Link>
            <div className="project-card-actions">
              {filter !== "deleted" ? <Link href={`/projects/${item.id}/logs`}>执行日志</Link> : <span>已移入回收站</span>}
              <Tooltip label={filter === "deleted" ? "恢复项目" : "删除项目"}><button className="icon-button" aria-label={`${filter === "deleted" ? "恢复项目" : "删除项目"}：${item.title}`} disabled={Boolean(busy)} onClick={() => void removeOrRestore(item)}>{filter === "deleted" ? <Undo2 size={17} /> : <Trash2 size={17} />}</button></Tooltip>
            </div>
            </article>
          ))}
        </section>
      ) : (
        query || filter ? <p role="status" className="empty-filter">没有符合条件的项目</p> : <section className="empty-projects">
          <div className="empty-project-image"><Image src="/images/motorcycle-studio.jpg" alt="摄影棚中的摩托车" fill priority sizes="(max-width: 760px) 100vw, 55vw" /></div>
          <div className="empty-project-copy"><span className="section-kicker">首条内容</span><h2>从一个车型和一个镜头想法开始</h2><p>系统会先整理事实、给出可比较的创意方向，再进入脚本和生成。</p><Button asChild><Link href="/projects/new"><Plus size={17} />新建项目</Link></Button></div>
        </section>
      )}
      {!loading && !error && total > 20 ? <nav className="pagination" aria-label="项目分页"><button className="icon-button" aria-label="上一页" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}><ChevronLeft size={18} /></button><span>{Math.floor(offset / 20) + 1} / {Math.ceil(total / 20)}</span><button className="icon-button" aria-label="下一页" disabled={offset + 20 >= total} onClick={() => setOffset(offset + 20)}><ChevronRight size={18} /></button></nav> : null}
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
  return { intake: "资料", advising: "策略", brief_draft: "Brief", brief_approved: "Brief", storyboard_draft: "分镜", storyboard_approved: "分镜", generating: "生成", needs_attention: "生成", completed: "成片", deleted: "回收站" }[status];
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}
