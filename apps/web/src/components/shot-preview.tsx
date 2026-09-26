"use client";

import { Check, Download, LoaderCircle, Play, RefreshCw, Square } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Status } from "@/components/ui/status";
import { Tooltip } from "@/components/ui/tooltip";
import { api, post } from "@/lib/api";
import type { GenerationRun, Storyboard } from "@/lib/types";

interface PreviewState {
  run: GenerationRun | null;
  readiness: { ready: boolean; mode: string; reason?: string | null; estimatedUsd?: string | null };
}

export function ShotPreview({ projectId, storyboardId, shotId, disabled, save, onActiveChange, onAdopted }: {
  projectId: string;
  storyboardId: string;
  shotId: string;
  disabled: boolean;
  save: () => Promise<Storyboard | null>;
  onActiveChange: (active: boolean) => void;
  onAdopted: () => Promise<void>;
}) {
  const endpoint = `/projects/${projectId}/storyboards/${storyboardId}/shots/${shotId}/preview`;
  const [run, setRun] = useState<GenerationRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const active = Boolean(run && ["queued", "running", "composing"].includes(run.status));
  const latest = run?.shotRuns.at(-1);

  useEffect(() => {
    let cancelled = false;
    api<PreviewState>(endpoint).then((state) => {
      if (!cancelled) { setRun(state.run); setLoaded(true); }
    }).catch((reason: Error) => { if (!cancelled) { setError(reason.message); setLoaded(true); } });
    return () => { cancelled = true; };
  }, [endpoint]);

  useEffect(() => {
    onActiveChange(active || busy);
    return () => onActiveChange(false);
  }, [active, busy, onActiveChange]);

  useEffect(() => {
    if (!active || !run?.id) return;
    const id = run.id;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api<GenerationRun>(`/generation-runs/${id}`);
        if (cancelled) return;
        setRun(next);
        if (!["queued", "running", "composing"].includes(next.status)) return;
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "试片状态查询失败");
      }
      if (!cancelled) timer = setTimeout(poll, 1500);
    };
    timer = setTimeout(poll, 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [active, run?.id]);

  async function perform(action: "start" | "adopt" | "retry" | "resume" | "cancel") {
    setBusy(true);
    setError("");
    try {
      if (action === "start") {
        const saved = await save();
        if (!saved) return;
        const state = await api<PreviewState>(endpoint);
        if (!state.readiness.ready) throw new Error(state.readiness.reason || "当前镜头尚未就绪");
        const paid = state.readiness.mode === "ai-video";
        if (paid && !window.confirm(`此镜头估算 USD ${state.readiness.estimatedUsd ?? "未知"}，确认调用付费视频模型？`)) return;
        setRun(await post<GenerationRun>("/generation-runs", {
          projectId, storyboardVersionId: saved.id, shotId, quality: "preview", confirmVideoCost: paid,
        }));
      } else if (run && action === "adopt") {
        if (!await save()) return;
        await post(`/generation-runs/${run.id}/adoption`);
        await onAdopted();
      } else if (run) {
        const paid = action === "retry" && run.mode === "ai-video";
        if (paid && !window.confirm("重做此镜头可能再次计费，确认继续？")) return;
        const suffix = action === "retry" ? `shots/${shotId}/retries${paid ? "?confirmVideoCost=true" : ""}`
          : action === "resume" ? "resumption" : "cancellation";
        setRun(await post<GenerationRun>(`/generation-runs/${run.id}/${suffix}`));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "试片操作失败");
    } finally { setBusy(false); }
  }

  return <section className="shot-preview" aria-label="单镜头试片">
    <div className="shot-preview-heading">
      <strong>镜头试片</strong>
      {run ? <span className="shot-preview-source">{latest?.strategy === "blender-3d" ? "Blender 环绕" : run.mode === "local-ai-video" ? "本地模型" : run.mode === "ai-video" ? "云端模型" : latest?.strategy === "image-motion" ? "图片运动" : "视频素材"}</span> : null}
      {run ? <Status value={run.status} /> : null}
      <Button variant="secondary" size="compact" disabled={disabled || busy || active || !loaded} onClick={() => void perform("start")}>
        {busy ? <LoaderCircle size={16} className="spin" /> : <Play size={16} />}保存并试片
      </Button>
    </div>
    {error || run?.errorMessage ? <p role="alert">{error || run?.errorMessage}</p> : null}
    {active && latest?.totalFrames ? <p role="status">已渲染 {latest.renderedFrames ?? 0} / {latest.totalFrames} 帧</p> : null}
    {active && run?.mode === "local-ai-video" ? <p role="status">本地视频模型{latest?.providerStatus === "QUEUED" ? "排队中" : "正在生成"}{typeof latest?.elapsedSeconds === "number" ? `，已用时 ${Math.floor(latest.elapsedSeconds / 60)} 分 ${latest.elapsedSeconds % 60} 秒` : ""}</p> : null}
    {latest?.artifactId && latest.status === "succeeded" ? <video key={latest.artifactId} src={`/api/v1/artifacts/${latest.artifactId}/content`} controls playsInline preload="metadata" aria-label="镜头试片视频" /> : null}
    {run ? <div className="shot-preview-actions">
      {active ? <Button variant="secondary" size="compact" disabled={busy} onClick={() => void perform("cancel")}><Square size={15} />停止试片</Button> : null}
      {["failed", "interrupted", "cancelled"].includes(run.status) ? <Button variant="secondary" size="compact" disabled={busy || disabled} onClick={() => void perform("resume")}><Play size={15} />继续试片</Button> : null}
      {run.status === "interrupted" && latest?.strategy === "blender-3d" ? <Button variant="secondary" size="compact" disabled={busy} onClick={() => void perform("cancel")}><Square size={15} />停止原渲染</Button> : null}
      {!active ? <Tooltip label="按原参数重做试片"><button className="icon-button inverse" aria-label="按原参数重做试片" disabled={busy || disabled} onClick={() => void perform("retry")}><RefreshCw size={16} /></button></Tooltip> : null}
      {run.status === "completed" && latest?.artifactId ? <>
        <Button size="compact" disabled={busy || disabled} onClick={() => void perform("adopt")}><Check size={16} />采用到当前镜头</Button>
        <Tooltip label="下载试片"><a className="icon-button inverse" aria-label="下载试片" href={`/api/v1/artifacts/${latest.artifactId}/content?download=true`}><Download size={16} /></a></Tooltip>
      </> : null}
    </div> : null}
  </section>;
}
