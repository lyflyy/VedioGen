"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Film, LoaderCircle, X } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { post } from "@/lib/api";
import type { AssetVersion, Storyboard } from "@/lib/types";

export function ReferenceCutDialog({ projectId, storyboard, assets, disabled, save }: {
  projectId: string; storyboard: Storyboard; assets: AssetVersion[]; disabled: boolean;
  save: () => Promise<Storyboard | null>;
}) {
  const router = useRouter();
  const images = assets.filter(a => a.kind === "image");
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(() => [...new Set([
    ...storyboard.shots.map(s => s.sourceAssetId).filter((id): id is string => Boolean(id && images.some(a => a.id === id))),
    ...images.map(a => a.id),
  ])].slice(0, 6));
  const [narration, setNarration] = useState(storyboard.soundPlan?.narration ?? false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submitting = useRef(false);
  async function generate() {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true); setError("");
    try {
      const saved = await save();
      if (!saved) { setError("分镜未保存，请先处理保存错误"); return; }
      const result = await post<{ projectId: string }>(`/projects/${projectId}/reference-cuts`, {
        storyboardVersionId: saved.id, rowVersion: saved.rowVersion, assetIds: selected,
        confirmSimplification: true, narration,
      });
      router.push(`/projects/${result.projectId}/generation`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "展示版生成失败"); }
    finally { submitting.current = false; setBusy(false); }
  }
  return <Dialog.Root open={open} onOpenChange={value => { if (!busy) setOpen(value); }}>
    <Dialog.Trigger asChild><Button variant="secondary" size="compact" disabled={disabled || !images.length}><Film size={16} />制作参考图展示版</Button></Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="crop-overlay" />
      <Dialog.Content className="reference-cut-dialog" onEscapeKeyDown={event => { if (busy) event.preventDefault(); }} onInteractOutside={event => { if (busy) event.preventDefault(); }}>
        <header className="crop-header"><Dialog.Title>参考图展示版</Dialog.Title><Dialog.Close asChild><button className="icon-button" aria-label="关闭展示版" title="关闭展示版" disabled={busy}><X size={18} /></button></Dialog.Close></header>
        <Dialog.Description>另建展示版项目，原脚本保留。画面改为所选照片的缓慢推近和切换，文案改为简短展示字幕，配本地节奏音乐。不包含原脚本的人物动作、新场景或真实 360° 环绕。</Dialog.Description>
        <fieldset disabled={busy} className="reference-cut-options"><legend>展示照片 · {selected.length} / 6 · {selected.length * 3} 秒</legend>
          <div className="reference-cut-grid">{images.map(asset => <label key={asset.id}>
            <Image src={asset.previewUrl} alt={asset.fileName} width={180} height={120} unoptimized />
            <span><input type="checkbox" checked={selected.includes(asset.id)} aria-label={`展示 ${asset.fileName} ${asset.id.slice(0, 6)}`}
              disabled={!selected.includes(asset.id) && selected.length >= 6}
              onChange={event => setSelected(current => event.target.checked ? [...current, asset.id] : current.filter(id => id !== asset.id))} />{asset.fileName}</span>
          </label>)}</div>
          <label className="reference-cut-narration"><input type="checkbox" checked={narration} onChange={event => setNarration(event.target.checked)} />中文旁白</label>
        </fieldset>
        {error ? <p role="alert">{error}</p> : null}
        <footer className="crop-footer"><Dialog.Close asChild><Button variant="secondary" disabled={busy}>保留原方案</Button></Dialog.Close><Button disabled={busy || !selected.length || disabled} onClick={() => void generate()}>{busy ? <LoaderCircle size={16} className="spin" /> : <Film size={16} />}确认并制作展示版</Button></footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
