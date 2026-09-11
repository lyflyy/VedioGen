"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { Crop, LoaderCircle, RotateCcw, Save, X } from "lucide-react";
import { useRef, useState } from "react";
import ReactCrop, { centerCrop, makeAspectCrop, type PercentCrop } from "react-image-crop";
import "react-image-crop/dist/ReactCrop.css";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { post } from "@/lib/api";
import type { AssetVersion } from "@/lib/types";

export function ImageCropDialog({ projectId, asset, disabled, onApply }: {
  projectId: string;
  asset: AssetVersion;
  disabled: boolean;
  onApply: (asset: AssetVersion) => void;
}) {
  const [open, setOpen] = useState(false);
  const [crop, setCrop] = useState<PercentCrop>();
  const [aspect, setAspect] = useState(9 / 16);
  const [size, setSize] = useState({ width: 0, height: 0 });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const image = useRef<HTMLImageElement>(null);
  const submission = useRef(false);

  function reset(ratio = aspect, dimensions = size) {
    if (!dimensions.width) return;
    setCrop(centerCrop(makeAspectCrop({ unit: "%", width: 100 }, ratio,
      dimensions.width, dimensions.height), dimensions.width, dimensions.height));
  }

  async function save() {
    if (!crop || submission.current || disabled) return;
    submission.current = true;
    setSaving(true);
    setError("");
    try {
      const { x, y, width, height } = crop;
      const prepared = await post<AssetVersion>(`/projects/${projectId}/assets/${asset.id}/crops`, { x, y, width, height });
      onApply(prepared);
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "裁剪保存失败");
    } finally { submission.current = false; setSaving(false); }
  }

  const width = crop ? Math.round(size.width * (crop.x + crop.width) / 100) - Math.round(size.width * crop.x / 100) : 0;
  const height = crop ? Math.round(size.height * (crop.y + crop.height) / 100) - Math.round(size.height * crop.y / 100) : 0;

  return <Dialog.Root open={open} onOpenChange={(value) => {
    if (submission.current) return;
    setOpen(value);
    if (value) { setCrop(undefined); setSize({ width: 0, height: 0 }); setError(""); }
  }}>
    <Dialog.Trigger asChild><Button variant="secondary" size="compact" disabled={disabled}><Crop size={16} />调整参考图</Button></Dialog.Trigger>
    <Dialog.Portal>
      <Dialog.Overlay className="crop-overlay" />
      <Dialog.Content className="crop-dialog" aria-describedby={undefined} onEscapeKeyDown={(event) => { if (saving) event.preventDefault(); }} onInteractOutside={(event) => { if (saving) event.preventDefault(); }}>
        <header className="crop-header"><Dialog.Title>参考图构图</Dialog.Title>
          <Dialog.Close asChild><button className="icon-button" aria-label="关闭裁剪" title="关闭裁剪" disabled={saving}><X size={18} /></button></Dialog.Close>
        </header>
        <div className="crop-surface">
          <ReactCrop crop={crop} onChange={(_, percent) => setCrop(percent)} aspect={aspect} keepSelection ruleOfThirds disabled={saving || disabled}
            ariaLabels={{ cropArea: "裁剪选区", nwDragHandle: "左上角", nDragHandle: "上边缘", neDragHandle: "右上角", eDragHandle: "右边缘", seDragHandle: "右下角", sDragHandle: "下边缘", swDragHandle: "左下角", wDragHandle: "左边缘" }}>
            {/* Natural dimensions are needed for source-pixel coordinates, not optimized variants. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img ref={image} src={asset.previewUrl} alt="待裁剪参考图" draggable={false} onLoad={(event) => {
              const dimensions = { width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight };
              setSize(dimensions); reset(aspect, dimensions);
            }} onError={() => { setCrop(undefined); setError("参考图加载失败，请关闭后重试"); }} />
          </ReactCrop>
        </div>
        <fieldset className="crop-controls" disabled={saving || disabled || !size.width}>
          <label>画面比例<select aria-label="裁剪比例" value={aspect} onChange={(event) => { const next = Number(event.target.value); setAspect(next); reset(next); }}>
            <option value={9 / 16}>9:16 竖屏</option><option value={480 / 832}>480:832 本地模型</option><option value={16 / 9}>16:9 横屏</option><option value={1}>1:1 方形</option>
          </select></label>
          <Tooltip label="重置裁剪"><Button size="icon" variant="secondary" aria-label="重置裁剪" onClick={() => reset()}><RotateCcw size={17} /></Button></Tooltip>
          <output aria-label="裁剪尺寸">{width} × {height} px</output>
          {crop ? <div className="crop-position">
            <label>水平位置<input type="range" aria-label="裁剪水平位置" min={0} max={Math.max(0, 100 - crop.width)} step="0.1" value={crop.x} onChange={(event) => setCrop({ ...crop, x: Number(event.target.value) })} /></label>
            <label>垂直位置<input type="range" aria-label="裁剪垂直位置" min={0} max={Math.max(0, 100 - crop.height)} step="0.1" value={crop.y} onChange={(event) => setCrop({ ...crop, y: Number(event.target.value) })} /></label>
          </div> : null}
        </fieldset>
        {error ? <p className="crop-error" role="alert">{error}</p> : null}
        <footer className="crop-footer"><Dialog.Close asChild><Button variant="secondary" disabled={saving}>取消</Button></Dialog.Close>
          <Button disabled={!crop || width < 32 || height < 32 || saving || disabled} onClick={() => void save()}>{saving ? <LoaderCircle className="spin" size={16} /> : <Save size={16} />}保存并应用到当前镜头</Button>
        </footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
