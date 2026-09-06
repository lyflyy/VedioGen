"use client";

import {
  FileImage,
  FileVideo2,
  Lightbulb,
  Paperclip,
  Sparkles,
  X,
} from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { post } from "@/lib/api";
import type { Project } from "@/lib/types";

const sample =
  "张雪 800X 最酷视频：车辆 360 度环绕，聚焦灯组、发动机和轮胎细节，最后是穿皮衣的骑手高速驾驶镜头。";

export default function NewProjectPage() {
  const router = useRouter();
  const [idea, setIdea] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState("real-subject");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<{
    label: string;
    percent: number;
  } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!idea.trim()) return;
    setSubmitting(true);
    setError("");
    try {
      const oversized = files.find((file) => file.size > 50 * 1024 * 1024);
      if (oversized) throw new Error(`${oversized.name} 超过 50 MB 上传限制`);
      setProgress({ label: "正在创建项目", percent: 5 });
      const title =
        idea
          .split(/[：:，,。\n]/)[0]
          .trim()
          .slice(0, 48) || "未命名视频";
      const project = await post<Project>("/projects", {
        title,
        contentPackId: "motorcycle",
        mode,
        targetPlatform: "douyin",
        locale: "zh-CN",
        initialMessage: idea,
        assetVersionIds: [],
      });
      for (const [index, file] of files.entries()) {
        setProgress({
          label: `正在准备 ${file.name}`,
          percent: Math.round((index / Math.max(files.length, 1)) * 90) + 5,
        });
        const digest = await sha256(file);
        const intent = await post<{
          assetVersionId: string;
          uploadUrl: string;
        }>("/assets/upload-intents", {
          projectId: project.id,
          fileName: file.name,
          mimeType: file.type,
          sizeBytes: file.size,
          sha256: digest,
        });
        await uploadFile(intent.uploadUrl, file, (filePercent) => {
          const overall =
            5 + ((index + filePercent / 100) / Math.max(files.length, 1)) * 90;
          setProgress({
            label: `正在上传 ${file.name}`,
            percent: Math.round(overall),
          });
        });
      }
      setProgress({ label: "素材已保存，正在进入 AI 策略分析", percent: 100 });
      router.push(`/projects/${project.id}/strategy`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "项目创建失败");
      setSubmitting(false);
      setProgress(null);
    }
  }

  return (
    <div className="new-project-layout">
      <section className="new-project-form">
        <header className="page-header compact">
          <div>
            <span className="section-kicker">新建项目</span>
            <h1>你想制作什么视频？</h1>
            <p>先说清车型、最想强调的内容，以及必须出现的镜头。</p>
          </div>
        </header>
        <form onSubmit={submit}>
          <label className="idea-field">
            <span className="sr-only">视频想法</span>
            <textarea
              autoFocus
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              placeholder={sample}
              rows={9}
            />
            <span className="character-count">{idea.length} / 10000</span>
          </label>
          <div className="upload-strip">
            <label className="upload-button">
              <Paperclip size={17} />
              <span>添加照片或视频</span>
              <input
                type="file"
                multiple
                accept="image/*,video/*"
                onChange={(event) =>
                  setFiles(Array.from(event.target.files ?? []))
                }
              />
            </label>
            <span>可选，多角度素材有助于保持车型一致</span>
          </div>
          {files.length > 0 ? (
            <div className="file-list">
              {files.map((file) => (
                <div key={`${file.name}-${file.size}`}>
                  <span>
                    {file.type.startsWith("video") ? (
                      <FileVideo2 size={16} />
                    ) : (
                      <FileImage size={16} />
                    )}
                    {file.name}
                  </span>
                  <button
                    type="button"
                    aria-label={`移除 ${file.name}`}
                    onClick={() =>
                      setFiles((current) =>
                        current.filter((item) => item !== file),
                      )
                    }
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
            </div>
          ) : null}
          <fieldset className="project-options">
            <legend>创作边界</legend>
            <label>
              <input
                type="radio"
                name="mode"
                value="real-subject"
                checked={mode === "real-subject"}
                onChange={(event) => setMode(event.target.value)}
              />
              <span>
                <strong>真实车型</strong>
                <small>优先保持外观和结构一致</small>
              </span>
            </label>
            <label>
              <input
                type="radio"
                name="mode"
                value="concept"
                checked={mode === "concept"}
                onChange={(event) => setMode(event.target.value)}
              />
              <span>
                <strong>概念创作</strong>
                <small>允许生成不存在的设计</small>
              </span>
            </label>
          </fieldset>
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
          {progress ? (
            <div className="upload-progress" role="status" aria-live="polite">
              <div>
                <span>{progress.label}</span>
                <strong>{progress.percent}%</strong>
              </div>
              <progress max="100" value={progress.percent} />
            </div>
          ) : null}
          <div className="form-actions">
            <span>
              <Lightbulb size={16} />
              下一步将生成 3 个可比较方向
            </span>
            <Button type="submit" disabled={!idea.trim() || submitting}>
              <Sparkles size={17} />
              {submitting
                ? files.length
                  ? "正在上传并分析"
                  : "正在建立项目"
                : "获取创意建议"}
            </Button>
          </div>
        </form>
      </section>
      <aside className="new-project-visual">
        <Image
          src="/images/motorcycle-road.jpg"
          alt="公路上的摩托车骑手"
          fill
          priority
          sizes="40vw"
        />
        <div className="visual-caption">
          <span>竖屏短视频</span>
          <strong>真实车型 · 机械细节 · 动态高潮</strong>
        </div>
      </aside>
    </div>
  );
}

async function sha256(file: File) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    await file.arrayBuffer(),
  );
  return `sha256:${Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

function uploadFile(
  url: string,
  file: File,
  onProgress: (percent: number) => void,
) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", url);
    request.setRequestHeader(
      "Content-Type",
      file.type || "application/octet-stream",
    );
    request.upload.onprogress = (event) => {
      if (event.lengthComputable)
        onProgress((event.loaded / event.total) * 100);
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) resolve();
      else {
        let detail = "";
        try {
          detail = JSON.parse(request.responseText)?.detail ?? "";
        } catch {
          detail = "";
        }
        reject(
          new Error(
            `${file.name} 上传失败 (${request.status})${detail ? `：${detail}` : ""}`,
          ),
        );
      }
    };
    request.onerror = () =>
      reject(new Error(`${file.name} 上传失败：网络连接中断`));
    request.send(file);
  });
}
