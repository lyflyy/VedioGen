"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Tooltip } from "@/components/ui/tooltip";

type Activity = { id: string; at: string; title: string; category: string; status: string; detail: string;
  model?: string; provider?: string; requestId?: string; errorCode?: string; durationMs?: number;
  inputTokens?: number; outputTokens?: number; sourceType?: string; sourceUrl?: string; previewUrl?: string;
  strategy?: string; attempt?: number; sourceAssetId?: string; nativeWidth?: number; nativeHeight?: number;
  elapsedSeconds?: number; timestampKind?: string; runId?: string; reusedFromProjectId?: string; prompt?: string; caption?: string; seed?: number; decodeMode?: string; modelSource?: string;
  script?: Array<{ order: number; visual: string; caption: string; voiceover: string; strategy: string; sourceAssetId: string }> };
const titles: Record<string, string> = { "final-video": "完整视频文件", "shot-video": "镜头视频文件", "creative-advisor": "创意建议", "storyboard-generator": "脚本文案生成", "asset-planner": "素材需求整理", "asset-matcher": "参考观察与镜头匹配", queued: "排队", "preparing-assets": "准备参考素材", "writing-script": "生成脚本", "matching-assets": "匹配镜头素材", "checking-shots": "检查镜头", "reviewing-preview": "等待试片确认", completed: "准备完成", failed: "执行失败" };
const statuses: Record<string, string> = { draft: "草稿", approved: "已确认", completed: "完成", succeeded: "成功", ready: "就绪", failed: "失败", calling: "调用中", running: "执行中", queued: "排队", composing: "合成中", cancelled: "已取消", interrupted: "已中断", needs_attention: "待处理", searching: "检索中" };

export function ProjectActivity({ projectId }: { projectId: string }) {
  const [items, setItems] = useState<Activity[]>([]);
  const [category, setCategory] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let stopped = false;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function load() {
      try {
        const result = await api<{ items: Activity[]; total: number }>(`/projects/${projectId}/activity?category=${category}&offset=${offset}`, { signal: controller.signal });
        if (!stopped) { setItems(result.items); setTotal(result.total); setError(""); }
      } catch (reason) { if (!stopped) setError(reason instanceof Error ? reason.message : "日志加载失败"); }
      finally { if (!stopped) { setLoading(false); timer = setTimeout(() => { if (!document.hidden) void load(); else timer = setTimeout(load, 5000); }, 5000); } }
    }
    timer = setTimeout(() => { setLoading(true); void load(); }, 0);
    return () => { stopped = true; controller.abort(); clearTimeout(timer); };
  }, [projectId, category, offset, revision]);
  return <section className="activity-page" aria-label="项目执行日志">
    <header className="activity-heading"><h2>执行日志</h2><span>{total} 条记录</span><Tooltip label="刷新日志"><button className="icon-button" aria-label="刷新日志" onClick={() => setRevision(value => value + 1)}><RefreshCw size={17} /></button></Tooltip></header>
    <div className="filter-segments" role="group" aria-label="日志类型">{[["", "全部"], ["model", "模型调用"], ["preparation", "准备步骤"], ["asset", "图片与素材"], ["video", "视频制作"], ["output", "输出文件"]].map(([value, label]) => <button key={value} aria-pressed={category === value} onClick={() => { setCategory(value); setOffset(0); }}>{label}</button>)}</div>
    {error ? <p className="inline-error" role="alert">{error}</p> : null}
    {loading ? <p role="status">正在载入日志</p> : !items.length ? <p role="status">暂无执行记录</p> : <ol className="activity-list">{items.map(item => <li key={item.id}>
      <div className="activity-summary"><time dateTime={item.at}>{new Date(item.at).toLocaleString("zh-CN")}</time><strong>{titles[item.title] ?? item.title}</strong><span className={item.status === "failed" ? "activity-failed" : ""}>{statuses[item.status] ?? item.status}</span></div>
      {item.provider || item.model ? <p>{item.provider}{item.model ? <> · <strong>{item.model}</strong></> : null}</p> : null}
      {item.detail ? <pre className="activity-message">{item.detail}</pre> : null}
      {item.errorCode && !item.detail.includes("上游返回") ? <p className="muted">该记录未保存上游原始说明，不能从状态码推断具体原因。</p> : null}
      {item.modelSource?.startsWith("当前") ? <p className="muted">{item.modelSource}</p> : null}
      {item.script ? <details><summary>查看脚本文案</summary>{item.script.map(shot => <div key={shot.order}><h3>镜头 {shot.order}</h3><p className="activity-message">{shot.visual}</p><p>字幕：{shot.caption || "无"}</p><p>旁白文本：{shot.voiceover || "无"}</p><p>制作方式：{shot.strategy} · 素材：{shot.sourceAssetId || "未选择"}</p></div>)}</details> : null}
      <details><summary>执行详情</summary><dl className="activity-fields">{Object.entries({ "记录 ID": item.id, "任务 ID": item.runId, "上游请求 ID": item.requestId, "错误码": item.errorCode, "调用耗时（毫秒）": item.durationMs, "输入 Token": item.inputTokens, "输出 Token": item.outputTokens, "素材来源类型": item.sourceType, "复用来源项目": item.reusedFromProjectId, "制作方式": item.strategy, "尝试次数": item.attempt, "参考素材 ID": item.sourceAssetId, "原生宽度": item.nativeWidth, "原生高度": item.nativeHeight, "镜头耗时（秒）": item.elapsedSeconds, "随机种子": item.seed, "解码方式": item.decodeMode, "字幕": item.caption, "镜头输入快照": item.prompt, "时间说明": item.timestampKind }).filter(([, value]) => value !== undefined && value !== null).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></details>
      <div className="activity-links">{item.sourceUrl?.startsWith("https://") ? <a href={item.sourceUrl} target="_blank" rel="noreferrer">素材来源页</a> : null}{item.previewUrl ? <a href={item.previewUrl} target="_blank" rel="noreferrer">查看实际文件</a> : null}</div>
    </li>)}</ol>}
    {total > 50 ? <nav className="pagination" aria-label="日志分页"><button className="icon-button" aria-label="上一页" disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 50))}><ChevronLeft size={18} /></button><span>{Math.floor(offset / 50) + 1} / {Math.ceil(total / 50)}</span><button className="icon-button" aria-label="下一页" disabled={offset + 50 >= total} onClick={() => setOffset(offset + 50)}><ChevronRight size={18} /></button></nav> : null}
  </section>;
}
