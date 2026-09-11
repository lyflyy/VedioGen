"use client";

import { ExternalLink, LoaderCircle, Search, Check } from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Status } from "@/components/ui/status";
import { api, post } from "@/lib/api";

type Candidate = {
  id: string;
  title: string;
  imageUrl: string;
  thumbnailUrl: string;
  sourceUrl: string;
  assetId: string | null;
  sourceType?: string;
  modelName?: string;
  requiresVariantConfirmation?: boolean;
};
type Discovery = {
  id: string;
  status: string;
  errorMessage: string | null;
  result: { subject?: string; searchFocus?: string; source?: "web" | "manufacturer"; clarification?: string; requiredShots?: string[]; candidates?: Candidate[]; warnings?: string[] };
};

export function ReferencePreparation({ projectId, onImported }: { projectId: string; onImported: () => Promise<void> }) {
  const [run, setRun] = useState<Discovery | null>(null);
  const [subject, setSubject] = useState("");
  const [focus, setFocus] = useState("");
  const [source, setSource] = useState<"web" | "manufacturer">("web");
  const [busy, setBusy] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [images, setImages] = useState<Record<string, "ready" | "failed">>({});
  const [originals, setOriginals] = useState<Record<string, boolean>>({});
  const active = run?.status === "queued" || run?.status === "running";
  const path = `/projects/${projectId}/asset-discoveries`;
  const refresh = useCallback(async () => {
    const value = await api<{ run: Discovery | null }>(`${path}/latest`);
    setRun(value.run);
  }, [path]);
  useEffect(() => {
    let disposed = false;
    void api<{ run: Discovery | null }>(`${path}/latest`).then((value) => {
      if (!disposed) {
        setRun(value.run);
        setSubject(value.run?.result.subject ?? "");
        setFocus(value.run?.result.searchFocus ?? "");
        setSource(value.run?.result.source ?? "web");
      }
    }).catch((reason) => { if (!disposed) setError(reason.message); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [path]);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => { void refresh().catch((reason) => setError(reason.message)); }, 1500);
    return () => clearInterval(timer);
  }, [active, refresh]);

  async function start() {
    setBusy("search");
    setError("");
    try { setRun(await post<Discovery>(path, { subject: subject.trim() || null, focus: focus.trim(), source })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "素材准备失败"); }
    finally { setBusy(""); }
  }
  async function adopt(candidate: Candidate) {
    const question = candidate.requiresVariantConfirmation
      ? `此图对应 ${candidate.modelName}，与输入的 ${run?.result.subject} 不是同一个精确版本名称。确认采用该版本为本项目车型和参考素材？`
      : "确认图片中的车型、颜色和版本符合本项目要求，并采用为参考素材？";
    if (!run || !window.confirm(question)) return;
    setBusy(candidate.id);
    setError("");
    try {
      await post(`${path}/${run.id}/candidates/${candidate.id}/import`, { confirmSubject: true, ...(candidate.requiresVariantConfirmation ? { confirmVariant: true } : {}) });
      await refresh();
      await onImported();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "素材下载失败"); }
    finally { setBusy(""); }
  }
  return <section className="content-frame reference-preparation" aria-label="参考素材准备">
    <div className="section-heading"><h2>参考素材</h2>{run ? <Status value={run.status === "ready" ? "search_completed" : run.status} /> : null}</div>
    <form className="reference-search settings-form" onSubmit={(event) => { event.preventDefault(); void start(); }}>
      <label>素材来源<select value={source} onChange={(event) => setSource(event.target.value as "web" | "manufacturer")} disabled={active || Boolean(busy)}><option value="web">网络图片</option><option value="manufacturer">品牌官网</option></select></label>
      <label>检索主体<input maxLength={100} value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="车型名称" disabled={active || Boolean(busy)} /></label>
      <label>镜头关键词<input maxLength={160} value={focus} onChange={(event) => setFocus(event.target.value)} placeholder="仪表特写、沙漠骑行、涉水" disabled={active || Boolean(busy)} /></label>
      <Button type="submit" disabled={loading || active || Boolean(busy)}>{active || busy === "search" ? <LoaderCircle size={16} className="spin" /> : <Search size={16} />}{subject.trim() ? "搜索参考素材" : "从描述准备素材"}</Button>
    </form>
    {error ? <p role="alert" className="shot-error">{error}</p> : null}
    {run?.errorMessage ? <p role="alert" className="shot-error">{run.errorMessage}</p> : null}
    {run?.result.subject ? <h3>{run.result.subject}</h3> : null}
    {run?.result.searchFocus ? <p>本次检索：{run.result.searchFocus}</p> : null}
    {run?.result.clarification ? <p role="status">{run.result.clarification}</p> : null}
    {run?.status === "empty" ? <p role="status">未找到名称匹配的图片，尚未准备好车型素材。</p> : null}
    {run?.result.warnings?.map((warning) => <p key={warning} role="status">{warning}</p>)}
    {run?.result.requiredShots?.length ? <ol className="reference-shot-list">{run.result.requiredShots.map((shot, index) => <li key={index}><span>{shot}</span><button className="icon-button" type="button" title="设为镜头关键词" aria-label={`选择镜头 ${index + 1} 关键词`} disabled={active || Boolean(busy)} onClick={() => { setFocus(shot.slice(0, 160)); setSubject(run.result.subject ?? ""); }}><Search size={16} /></button></li>)}</ol> : null}
    <div className="reference-candidates">
      {run?.result.candidates?.map((candidate, index) => <article className="reference-candidate" key={candidate.id}>
        <div className="reference-image">
          <Image src={originals[candidate.id] ? candidate.imageUrl : candidate.thumbnailUrl} alt={candidate.title} width={640} height={360} unoptimized loading={index < 4 ? "eager" : "lazy"}
            onLoad={() => setImages((current) => ({ ...current, [candidate.id]: "ready" }))}
            onError={() => {
              if (!originals[candidate.id] && candidate.thumbnailUrl !== candidate.imageUrl) {
                setOriginals((current) => ({ ...current, [candidate.id]: true }));
              } else {
                setImages((current) => ({ ...current, [candidate.id]: "failed" }));
              }
            }} />
          {images[candidate.id] === "failed" ? <span>预览加载失败</span> : null}
        </div>
        <h3>{candidate.title}</h3>
        <p>{candidate.assetId ? "已由用户确认并加入素材" : candidate.requiresVariantConfirmation ? `官网版本：${candidate.modelName} · 尚未确认采用` : candidate.sourceType === "manufacturer" ? `官网车型：${candidate.modelName} · 画面内容待确认` : "名称匹配，车型版本与画面内容待确认"}</p>
        <div className="reference-actions">
          <a href={candidate.sourceUrl} target="_blank" rel="noreferrer"><ExternalLink size={14} />来源页面</a>
          <Button size="compact" variant="secondary" disabled={Boolean(busy) || Boolean(candidate.assetId) || images[candidate.id] !== "ready"} onClick={() => adopt(candidate)}>
            {busy === candidate.id ? <LoaderCircle size={14} className="spin" /> : <Check size={14} />}{candidate.assetId ? "已采用" : candidate.requiresVariantConfirmation ? "确认版本并采用" : "确认主体并采用"}
          </Button>
        </div>
      </article>)}
    </div>
  </section>;
}
