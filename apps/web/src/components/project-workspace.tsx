"use client";

import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Check,
  ChevronRight,
  CircleGauge,
  Download,
  ExternalLink,
  FileCheck2,
  Film,
  Info,
  Layers3,
  LoaderCircle,
  MessageSquareText,
  Mountain,
  Paperclip,
  Play,
  RefreshCw,
  Save,
  Sparkles,
  WandSparkles,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { ProjectHeader } from "@/components/project-header";
import { ProjectActivity } from "@/components/project-activity";
import { ReferencePreparation } from "@/components/reference-preparation";
import { ImageCropDialog } from "@/components/image-crop-dialog";
import { ShotPreview } from "@/components/shot-preview";
import { PreparationProgress, type PreparationRun } from "@/components/preparation-progress";
import { Button } from "@/components/ui/button";
import { Status } from "@/components/ui/status";
import { Tooltip } from "@/components/ui/tooltip";
import { api, post, put, uploadProjectAsset } from "@/lib/api";
import type {
  AdvisorRun,
  AssetVersion,
  Artifact,
  Brief,
  GenerationRun,
  Proposal,
  Shot,
  Storyboard,
  Workspace,
} from "@/lib/types";

type MaterialRun = {
  previewGenerationRunId?: string;
  previewShotId?: string;
  resultVersion?: number;
  id: string; status: string; phase: string; errorMessage: string | null;
  storyboardVersionId: string; generationRunId: string | null;
  changes: Array<{ shotId: string; order: number; message: string }>;
  checks: Array<{ shotId: string; order: number; ready: boolean; reason: string | null }>;
};
const materialPhases: Record<string, string> = {
  queued: "素材准备排队中", "preparing-assets": "正在检查素材、匹配参考图与生成方式",
  "checking-shots": "正在检查所有镜头", "starting-video": "正在启动视频生成",
  "reviewing-preview": "关键镜头已安排试片，请查看并采用满意的结果",
};
const sourceLabels: Record<string, string> = {
  "image-motion": "图片运镜", "image-to-video": "AI 动态视频", "user-video": "视频剪辑", "blender-3d": "三维渲染",
};

export function ProjectWorkspace() {
  const params = useParams<{ projectId: string; stage: string }>();
  const router = useRouter();
  const { projectId, stage } = params;
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [advisor, setAdvisor] = useState<AdvisorRun | null>(null);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null);
  const [generation, setGeneration] = useState<GenerationRun | null>(null);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [selectedShot, setSelectedShot] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [quality, setQuality] = useState("standard");
  const [audioAssetId, setAudioAssetId] = useState("");
  const [narration, setNarration] = useState(false);
  const [previewActive, setPreviewActive] = useState(false);
  const [preparation, setPreparation] = useState<PreparationRun | null>(null);
  const [notice, setNotice] = useState("");
  const [savedShots, setSavedShots] = useState("");
  const [materials, setMaterials] = useState<MaterialRun | null>(null);
  const materialsActive = Boolean(materials && ["queued", "running"].includes(materials.status));
  const unsaved = Boolean(storyboard && JSON.stringify([storyboard.shots, storyboard.soundPlan]) !== savedShots);
  const preparing = Boolean(preparation && ["queued", "running"].includes(preparation.status));
  const advisorStarted = useRef(false);
  const generationActive = Boolean(generation && ["queued", "running", "composing"].includes(generation.status));

  const hydrate = useCallback(async () => {
    const nextWorkspace = await api<Workspace>(
      `/projects/${projectId}/workspace`,
    );
    setWorkspace(nextWorkspace);
    const [nextAdvisor, nextBrief, nextStoryboard, nextGeneration] =
      await Promise.all([
        nextWorkspace.latestAdvisorRunId
          ? api<AdvisorRun>(`/advisor-runs/${nextWorkspace.latestAdvisorRunId}`)
          : Promise.resolve(null),
        nextWorkspace.project.currentBriefVersionId
          ? api<Brief>(
              `/projects/${projectId}/creative-briefs/${nextWorkspace.project.currentBriefVersionId}`,
            )
          : Promise.resolve(null),
        nextWorkspace.project.currentStoryboardVersionId
          ? api<Storyboard>(
              `/projects/${projectId}/storyboards/${nextWorkspace.project.currentStoryboardVersionId}`,
            )
          : Promise.resolve(null),
        nextWorkspace.activeGenerationRunId
          ? api<GenerationRun>(
              `/generation-runs/${nextWorkspace.activeGenerationRunId}`,
            )
          : Promise.resolve(null),
      ]);
    setAdvisor(nextAdvisor);
    setBrief(nextBrief);
    setStoryboard(nextStoryboard);
    setSavedShots(nextStoryboard ? JSON.stringify([nextStoryboard.shots, nextStoryboard.soundPlan]) : "");
    setGeneration(nextGeneration);
    setNarration(nextStoryboard?.soundPlan?.narration ?? Boolean(nextGeneration?.audioMode.includes("narration")));
    if (nextStoryboard?.shots.length)
      setSelectedShot((current) => current ?? nextStoryboard.shots[0].id);
    if (nextGeneration?.finalArtifactId)
      setArtifact(
        await api<Artifact>(`/artifacts/${nextGeneration.finalArtifactId}`),
      );
    else setArtifact(null);
  }, [projectId]);

  useEffect(() => {
    void Promise.resolve()
      .then(hydrate)
      .catch((reason: Error) => setError(reason.message));
  }, [hydrate]);

  useEffect(() => {
    if (stage !== "storyboard") return;
    let cancelled = false;
    api<{ run: MaterialRun | null }>(`/projects/${projectId}/material-runs/latest`)
      .then(({ run }) => { if (!cancelled) setMaterials(run); })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); });
    return () => { cancelled = true; };
  }, [projectId, stage]);

  useEffect(() => {
    if (!materialsActive) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const { run } = await api<{ run: MaterialRun | null }>(`/projects/${projectId}/material-runs/latest`);
        if (cancelled || !run) return;
        if (!["queued", "running"].includes(run.status)) {
          await hydrate();
          if (!cancelled) {
            setMaterials(run);
            if (run.previewShotId) setSelectedShot(run.previewShotId);
            if (run.generationRunId) router.push(`/projects/${projectId}/generation`);
          }
          return;
        }
        setMaterials(run);
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "素材状态查询失败"); }
      if (!cancelled) timer = setTimeout(poll, 1500);
    }
    timer = setTimeout(poll, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [materialsActive, projectId, hydrate, router]);

  useEffect(() => {
    if (stage !== "brief") return;
    let cancelled = false;
    api<{ run: PreparationRun | null }>(`/projects/${projectId}/storyboard-runs/latest`)
      .then(({ run }) => { if (!cancelled) setPreparation(run); })
      .catch((reason: Error) => { if (!cancelled) setError(reason.message); });
    return () => { cancelled = true; };
  }, [projectId, stage]);

  useEffect(() => {
    if (!preparing) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const { run } = await api<{ run: PreparationRun | null }>(`/projects/${projectId}/storyboard-runs/latest`);
        if (cancelled || !run) return;
        if (run.status === "completed") {
          await hydrate();
          if (!cancelled) {
            setPreparation(run);
            router.push(`/projects/${projectId}/storyboard`);
          }
          return;
        }
        setPreparation(run);
        if (!["queued", "running"].includes(run.status)) return;
      } catch (reason) { if (!cancelled) setError(reason instanceof Error ? reason.message : "脚本状态查询失败"); }
      if (!cancelled) timer = setTimeout(poll, 1200);
    }
    timer = setTimeout(poll, 500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [preparing, projectId, hydrate, router]);

  useEffect(() => {
    if (!unsaved) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [unsaved]);

  useEffect(() => {
    if (!generationActive || !generation?.id) return;
    const runId = generation.id;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<GenerationRun>(`/generation-runs/${runId}`);
        if (cancelled) return;
        setGeneration(next);
        if (next.finalArtifactId) {
          const media = await api<Artifact>(`/artifacts/${next.finalArtifactId}`);
          if (!cancelled) setArtifact(media);
        }
        if (!["queued", "running", "composing"].includes(next.status)) {
          const nextWorkspace = await api<Workspace>(`/projects/${projectId}/workspace`);
          if (!cancelled) setWorkspace(nextWorkspace);
          return;
        }
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "任务状态查询失败");
      }
      if (!cancelled) timer = setTimeout(poll, 1500);
    }
    timer = setTimeout(poll, 1000);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [generationActive, generation?.id, projectId]);

  async function uploadAsset(file: File, shotId?: string) {
    setBusy("upload");
    setError("");
    try {
      const asset = await uploadProjectAsset(projectId, file);
      setWorkspace(await api<Workspace>(`/projects/${projectId}/workspace`));
      if (shotId && asset.kind !== "audio") {
        setStoryboard((current) => current ? { ...current, status: "draft", shots: current.shots.map((shot) => shot.id === shotId
          ? { ...shot, sourceAssetId: asset.id, selectionOwner: "user", ...(asset.kind === "video" ? { sourceStrategy: "user-video", sourceStartMs: 0 }
            : asset.kind === "model" ? { sourceStrategy: "blender-3d", blenderTemplate: "orbit-360" as const }
            : { sourceStrategy: shot.sourceStrategy === "image-motion" ? "image-motion" : "image-to-video",
                videoPrompt: shot.videoPrompt || [shot.visual, shot.camera, shot.purpose].filter(Boolean).join("\n"), sourceStartMs: 0 }) } : shot) } : current);
        setNotice("素材已上传并绑定当前镜头，请保存分镜");
      } else setNotice("素材已加入项目素材库");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "素材上传失败");
    } finally { setBusy(""); }
  }

  async function runAction(action: string) {
    if (!generation) return;
    if (generation.mode === "ai-video" && action.endsWith("/retries")) {
      if (!window.confirm("重做可能再次调用视频模型并计费，继续吗？")) return;
      action += "?confirmVideoCost=true";
    }
    setBusy("run-action");
    setError("");
    try {
      const next = await post<GenerationRun>(`/generation-runs/${generation.id}/${action}`);
      setGeneration(next);
      setArtifact(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务操作失败");
    } finally { setBusy(""); }
  }

  useEffect(() => {
    if (
      stage !== "strategy" ||
      !workspace ||
      workspace.latestAdvisorRunId ||
      advisor ||
      advisorStarted.current
    )
      return;
    advisorStarted.current = true;
    void Promise.resolve()
      .then(() => {
        setBusy("advisor");
        return post<AdvisorRun>(`/projects/${projectId}/advisor-runs`);
      })
      .then((result) => {
        setAdvisor(result);
        return hydrate();
      })
      .catch((reason: Error) => {
        setError(reason.message);
      })
      .finally(() => setBusy(""));
  }, [advisor, hydrate, projectId, stage, workspace]);

  async function chooseProposal(proposal: Proposal) {
    if (!advisor) return;
    setBusy(proposal.proposalKey);
    setError("");
    try {
      const next = await post<Brief>(`/projects/${projectId}/creative-briefs`, {
        advisorRunId: advisor.id,
        proposalKey: proposal.proposalKey,
        overrides: {},
      });
      setBrief(next);
      await hydrate();
      router.push(`/projects/${projectId}/brief`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Brief 创建失败");
    } finally {
      setBusy("");
    }
  }

  async function regenerateAdvice(feedback: string) {
    setBusy("feedback");
    setError("");
    try {
      if (feedback.trim()) {
        await post(`/projects/${projectId}/messages`, {
          text: feedback,
          assetVersionIds: [],
        });
      }
      const next = await post<AdvisorRun>(
        `/projects/${projectId}/advisor-runs`,
      );
      setAdvisor(next);
      await hydrate();
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创意建议更新失败");
      return false;
    } finally {
      setBusy("");
    }
  }

  async function approveBrief() {
    if (!brief) return;
    setBusy("brief");
    setError("");
    try {
      await post(
        `/projects/${projectId}/creative-briefs/${brief.id}/approval`,
        {},
      );
      const run = await post<PreparationRun>(
        `/projects/${projectId}/storyboard-runs?background=true`,
      );
      setPreparation(run);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Brief 确认失败");
    } finally {
      setBusy("");
    }
  }

  async function saveStoryboard(
    nextShots = storyboard?.shots,
    manageBusy = true,
  ): Promise<Storyboard | null> {
    if (!storyboard || !nextShots) return null;
    if (manageBusy) setBusy("save-storyboard");
    setError("");
    setNotice("");
    const total = nextShots.reduce((sum, shot) => sum + shot.durationMs, 0);
    try {
      const next = await put<Storyboard>(
        `/projects/${projectId}/storyboards/${storyboard.id}`,
        {
          shots: nextShots.map((shot, index) => ({
            ...shot,
            order: index + 1,
          })),
          totalDurationMs: total,
          soundPlan: storyboard.soundPlan ?? null,
        },
      );
      setStoryboard(next);
      setSavedShots(JSON.stringify([next.shots, next.soundPlan]));
      setNotice("分镜已保存");
      return next;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分镜保存失败");
    } finally {
      if (manageBusy) setBusy("");
    }
    return null;
  }

  async function approveStoryboard() {
    if (!storyboard) return;
    setBusy("approve-storyboard");
    try {
      const saved = await saveStoryboard(storyboard.shots, false);
      if (!saved) return;
      const checks = await api<{ ready: boolean; shots: MaterialRun["checks"] }>(`/projects/${projectId}/storyboards/${saved.id}/readiness`);
      if (!checks.ready) {
        setMaterials({ id: "validation", storyboardVersionId: saved.id, resultVersion: saved.rowVersion, status: "needs_attention", phase: "needs-attention", checks: checks.shots, changes: [], errorMessage: null, generationRunId: null });
        setNotice("分镜已保存，待处理镜头已标出");
        return;
      }
      await post(`/projects/${projectId}/storyboards/${saved.id}/approval`, {});
      await hydrate();
      router.push(`/projects/${projectId}/generation`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分镜确认失败");
    } finally {
      setBusy("");
    }
  }

  async function autoMaterials(generateVideo = false) {
    if (!storyboard) return;
    setBusy("auto-materials");
    setError("");
    setNotice("正在准备并匹配镜头素材");
    try {
      if (!await saveStoryboard(storyboard.shots, false)) return;
      setNotice("正在准备并匹配镜头素材");
      const run = await post<MaterialRun>(`/projects/${projectId}/storyboards/${storyboard.id}/material-runs?generate=${generateVideo}`);
      setMaterials(run);
      setNotice("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "素材准备失败"); }
    finally { setBusy(""); }
  }

  async function generate() {
    if (!storyboard) return;
    const paidVideo = workspace?.generationReadiness.mode === "ai-video";
    if (paidVideo && !window.confirm(`本次视频模型估算 USD ${workspace?.generationReadiness.estimatedUsd ?? "未知"}，实际扣费以供应商为准。确认调用？`)) return;
    setBusy("generation");
    setError("");
    try {
      const run = await post<GenerationRun>("/generation-runs", {
        projectId,
        storyboardVersionId: storyboard.id,
        quality,
        audioAssetId: audioAssetId || null,
        narration,
        confirmVideoCost: paidVideo,
      });
      setGeneration(run);
      if (run.finalArtifactId)
        setArtifact(await api<Artifact>(`/artifacts/${run.finalArtifactId}`));
      await hydrate();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "生成任务失败");
    } finally {
      setBusy("");
    }
  }

  if (!workspace)
    return (
      <div className="workspace-loading" role={error ? "alert" : "status"}>
        {error ? <><AlertCircle /><span>工作区加载失败，请重新载入。</span><Button variant="secondary" onClick={() => {
          setError("");
          void hydrate().catch((reason: Error) => setError(reason.message));
        }}><RefreshCw size={16} />重新载入</Button></> : <><LoaderCircle className="spin" />正在恢复项目工作区</>}
      </div>
    );

  return (
    <div className="project-page">
      <ProjectHeader project={workspace.project} activeStage={stage} unsaved={unsaved} />
      {stage === "logs" ? <ProjectActivity projectId={projectId} /> : null}
      {notice ? <div className="workspace-notice" role="status"><Check size={16} />{notice}</div> : null}
      {stage === "storyboard" && storyboard?.materialWarnings?.length ? <div className="workspace-material-warnings">
        {storyboard.materialWarnings.map((warning) => <p key={warning}><AlertCircle size={15} />{warning}</p>)}
      </div> : null}
      {error ? (
        <div className="workspace-error" role="alert">
          <AlertCircle size={18} />
          <span className="model-error-text">{error}</span>
          <Link href={`/projects/${projectId}/logs`}>查看执行日志</Link>
          <button
            onClick={() => {
              if (stage !== "strategy" || advisor) setError("");
              void hydrate().catch((reason: Error) => setError(reason.message));
            }}
          >
            重新载入
          </button>
        </div>
      ) : null}
      {stage === "intake" ? <><Intake workspace={workspace} /><ReferencePreparation projectId={projectId} onImported={hydrate} /></> : null}
      {stage === "strategy" ? (
        <Strategy
          workspace={workspace}
          advisor={advisor}
          busy={busy}
          error={error}
          chooseProposal={chooseProposal}
          regenerateAdvice={regenerateAdvice}
        />
      ) : null}
      {stage === "brief" ? (
        <BriefView brief={brief} busy={preparing ? "preparing" : busy} approve={approveBrief} preparation={preparation} projectId={projectId} />
      ) : null}
      {stage === "storyboard" ? (
        <StoryboardView
          storyboard={storyboard}
          selectedShot={selectedShot}
          setSelectedShot={setSelectedShot}
          setStoryboard={setStoryboard}
          save={saveStoryboard}
          approve={approveStoryboard}
          busy={materialsActive ? "auto-materials" : busy}
          materials={materials?.storyboardVersionId === storyboard?.id && (materialsActive || materials?.resultVersion === storyboard?.rowVersion) ? materials : null}
          assets={workspace.assetVersions}
          locked={generationActive || previewActive}
          previewDisabled={generationActive || materialsActive}
          onPreviewActive={setPreviewActive}
          onPreviewAdopted={hydrate}
          upload={uploadAsset}
          autoMaterials={autoMaterials}
          unsaved={unsaved}
          projectId={projectId}
          applyCrop={(shotId, asset) => {
            setWorkspace((current) => current ? { ...current, assetVersions: [...current.assetVersions, asset] } : current);
            setStoryboard((current) => current ? { ...current, status: "draft", shots: current.shots.map((shot) => shot.id === shotId ? { ...shot, sourceAssetId: asset.id, selectionOwner: "user", fit: "contain" } : shot) } : current);
          }}
        />
      ) : null}
      {stage === "generation" ? (
        <GenerationView
          storyboard={storyboard}
          generation={generation}
          readiness={workspace.generationReadiness}
          busy={busy}
          generate={generate}
          assets={workspace.assetVersions}
          quality={quality}
          setQuality={setQuality}
          audioAssetId={audioAssetId}
          setAudioAssetId={setAudioAssetId}
          narration={narration}
          setNarration={setNarration}
          runAction={runAction}
        />
      ) : null}
      {stage === "final" ? (
        <FinalView
          projectId={projectId}
          generation={generation}
          artifact={artifact}
        />
      ) : null}
    </div>
  );
}

function Intake({ workspace }: { workspace: Workspace }) {
  return (
    <div className="content-frame two-column-detail">
      <section>
        <div className="section-heading">
          <div>
            <span className="section-kicker">原始输入</span>
            <h2>项目资料</h2>
          </div>
        </div>
        <div className="conversation-log">
          {workspace.messages.map((message) => (
            <article key={message.id}>
              <span>{message.role === "user" ? "你" : "AI"}</span>
              <p>{message.text}</p>
            </article>
          ))}
        </div>
      </section>
      <aside className="facts-panel">
        <div className="section-heading">
          <div>
            <span className="section-kicker">已提取</span>
            <h2>项目事实</h2>
          </div>
        </div>
        {workspace.facts.map((fact) => (
          <div className="fact-row" key={fact.id}>
            <span>
              {fact.key === "subject.vehicle.name" ? "车型" : "发布平台"}
            </span>
            <strong>{String(fact.value)}</strong>
            <Status
              value={fact.status === "confirmed" ? "ready" : fact.status}
            />
          </div>
        ))}
      </aside>
    </div>
  );
}

function Strategy({
  workspace,
  advisor,
  busy,
  error,
  chooseProposal,
  regenerateAdvice,
}: {
  workspace: Workspace;
  advisor: AdvisorRun | null;
  busy: string;
  error: string;
  chooseProposal: (proposal: Proposal) => void;
  regenerateAdvice: (feedback: string) => Promise<boolean>;
}) {
  const [feedback, setFeedback] = useState("");
  async function submitFeedback(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = feedback.trim();
    if (!value) return;
    if (await regenerateAdvice(value)) setFeedback("");
  }
  if (!advisor)
    return (
      <div className="workspace-loading" role="status">
        {error && !busy ? <AlertCircle /> : <LoaderCircle className="spin" />}
        <div>
          <strong>{error && !busy ? "创意建议未完成" : "正在形成创意判断"}</strong>
          {error && !busy ? (
            <Button variant="secondary" onClick={() => void regenerateAdvice("")}>
              <RefreshCw size={16} />重新生成建议
            </Button>
          ) : <span>整理车型事实、视觉机会和制作约束</span>}
        </div>
      </div>
    );
  return (
    <div className="advisor-layout">
      <aside className="conversation-rail">
        <div className="rail-heading">
          <MessageSquareText size={18} />
          <div>
            <strong>创意对话</strong>
            <span>{workspace.messages.length} 条输入</span>
          </div>
        </div>
        <details className="conversation-history"><summary>查看原始输入 · {workspace.messages.length} 条</summary>{workspace.messages.map((message) => (
          <div className="message-bubble user-message" key={message.id}>
            {message.text}
          </div>
        ))}</details>
        <div className="message-bubble ai-message">
          <Sparkles size={16} />
          <p>{advisor.result.diagnosis.understoodGoal}</p>
        </div>
        <form className="conversation-input" onSubmit={submitFeedback}>
          <textarea
            aria-label="补充创意要求"
            placeholder="补充必须保留的内容"
            rows={3}
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
          />
          <Button
            variant="secondary"
            size="compact"
            disabled={!feedback.trim() || Boolean(busy)}
          >
            {busy === "feedback" ? (
              <LoaderCircle className="spin" size={14} />
            ) : null}
            发送
          </Button>
        </form>
      </aside>
      <main className="advisor-main">
        <section className="diagnosis-band">
          <div>
            <span className="section-kicker">内容判断</span>
            <h2>创意建议</h2>
            <p>{advisor.result.diagnosis.opportunity}</p>
          </div>
          <div className="risk-note">
            <AlertCircle size={18} />
            <div>
              <strong>主要制作风险</strong>
              <span>{advisor.result.diagnosis.primaryRisk}</span>
            </div>
          </div>
        </section>
        <div className="proposal-heading">
          <div>
            <h2>选择一个叙事方向</h2>
          </div>
          <span>推荐方案已标记</span>
        </div>
        <section className="proposal-grid" aria-label="叙事方向比较" tabIndex={0}>
          {advisor.result.proposals.map((proposal) => (
            <article
              className="proposal-card"
              key={proposal.proposalKey}
              data-recommended={
                advisor.result.recommendedProposalKey === proposal.proposalKey
              }
            >
              <div className="proposal-topline">
                <span>{proposal.contentType}</span>
                {advisor.result.recommendedProposalKey ===
                proposal.proposalKey ? (
                  <span className="recommendation">
                    <Sparkles size={13} />
                    推荐
                  </span>
                ) : null}
              </div>
              <h3>{proposal.name}</h3>
              <p>{proposal.positioning}</p>
              <div className="hook-block">
                <span>前 {proposal.hook.durationMs / 1000} 秒</span>
                <strong>{proposal.hook.text}</strong>
                <small>{proposal.hook.visual}</small>
              </div>
              <dl>
                <div>
                  <dt>视觉回报</dt>
                  <dd>{proposal.visualPayoffs.slice(0, 2).join(" / ")}</dd>
                </div>
                <div>
                  <dt>资源等级</dt>
                  <dd>
                    {proposal.resourceEstimate === "medium"
                      ? "标准"
                      : proposal.resourceEstimate === "high" ? "较高" : "轻量"}
                  </dd>
                </div>
              </dl>
              <Button
                onClick={() => chooseProposal(proposal)}
                disabled={Boolean(busy)}
                variant={
                  advisor.result.recommendedProposalKey === proposal.proposalKey
                    ? "primary"
                    : "secondary"
                }
              >
                {busy === proposal.proposalKey ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <WandSparkles size={16} />
                )}
                采用这个方向
              </Button>
            </article>
          ))}
        </section>
      </main>
      <aside className="facts-panel advisor-facts">
        <div className="section-heading">
          <div>
            <span className="section-kicker">项目依据</span>
            <h2>事实与约束</h2>
          </div>
        </div>
        {workspace.facts.map((fact) => (
          <div className="fact-row" key={fact.id}>
            <span>{fact.key === "subject.vehicle.name" ? "车型" : "平台"}</span>
            <strong>{String(fact.value)}</strong>
            <Status value="ready" />
          </div>
        ))}
        <div className="evidence-empty">
          <Info size={18} />
          <div>
            <strong>{workspace.assetVersions.length} 项项目素材</strong>
            <Link href={`/projects/${workspace.project.id}/intake`}>查看素材与来源</Link>
          </div>
        </div>
      </aside>
    </div>
  );
}

function BriefView({
  brief,
  busy,
  approve,
  preparation,
  projectId,
}: {
  brief: Brief | null;
  busy: string;
  approve: () => void;
  preparation: PreparationRun | null;
  projectId: string;
}) {
  if (!brief)
    return <MissingState title="还没有 Creative Brief" href="strategy" />;
  return (
    <div className="content-frame brief-page">
      <section className="brief-document">
        <div className="section-heading">
          <div>
            <span className="section-kicker">
              Creative Brief · 版本 {brief.version}
            </span>
            <h2>{brief.corePromise}</h2>
          </div>
          <Status value={brief.status} />
        </div>
        <div className="brief-grid">
          <BriefField label="内容类型" value={brief.contentType} />
          <BriefField label="主要目标" value={brief.primaryGoal} />
          <BriefField label="受众" value={brief.audience.join("、")} />
          <BriefField
            label="资源等级"
            value={
              brief.resourceEstimate === "medium"
                ? "标准"
                : brief.resourceEstimate
            }
          />
        </div>
        <section className="brief-section">
          <h3>开场 Hook</h3>
          <blockquote>{brief.hook.text}</blockquote>
          <p>{brief.hook.visual}</p>
        </section>
        <section className="brief-section">
          <h3>视觉回报</h3>
          <ol>
            {brief.visualPayoffs.map((item) => (
              <li key={item}>
                <Check size={16} />
                {item}
              </li>
            ))}
          </ol>
        </section>
        <section className="brief-section split">
          <div>
            <h3>节奏</h3>
            <p>{brief.pacing}</p>
          </div>
          <div>
            <h3>情绪峰值</h3>
            <p>{brief.emotionalPeak}</p>
          </div>
        </section>
      </section>
      <aside className="approval-summary">
        <FileCheck2 size={24} />
        <h2>确认后生成脚本分镜</h2>
        <dl>
          <div>
            <dt>目标时长</dt>
            <dd>{brief.targetDurationMs / 1000} 秒</dd>
          </div>
          <div>
            <dt>画幅</dt>
            <dd>9:16</dd>
          </div>
          <div>
            <dt>平台</dt>
            <dd>抖音</dd>
          </div>
        </dl>
        <p>当前方向：{brief.contentType}</p>
        <Button
          onClick={approve}
          disabled={Boolean(busy)}
        >
          {busy ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <ChevronRight size={17} />
          )}
          确认并生成脚本
        </Button>
        {preparation ? <PreparationProgress run={preparation} /> : null}
        {preparation?.status === "completed" ? <Link className="button button-secondary" href={`/projects/${projectId}/storyboard`}>查看已有脚本</Link> : null}
      </aside>
    </div>
  );
}

function BriefField({ label, value }: { label: string; value: string }) {
  return (
    <div className="brief-field">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StoryboardView({
  storyboard,
  selectedShot,
  setSelectedShot,
  setStoryboard,
  save,
  approve,
  busy,
  assets,
  locked,
  upload,
  projectId,
  applyCrop,
  previewDisabled,
  onPreviewActive,
  onPreviewAdopted,
  autoMaterials,
  unsaved,
  materials,
}: {
  storyboard: Storyboard | null;
  selectedShot: string | null;
  setSelectedShot: (id: string) => void;
  setStoryboard: (value: Storyboard) => void;
  save: (shots?: Shot[]) => Promise<Storyboard | null>;
  approve: () => void;
  busy: string;
  assets: AssetVersion[];
  locked: boolean;
  upload: (file: File, shotId?: string) => Promise<void>;
  autoMaterials: (generateVideo?: boolean) => Promise<void>;
  materials: MaterialRun | null;
  unsaved: boolean;
  projectId: string;
  applyCrop: (shotId: string, asset: AssetVersion) => void;
  previewDisabled: boolean;
  onPreviewActive: (active: boolean) => void;
  onPreviewAdopted: () => Promise<void>;
}) {
  const selected =
    storyboard?.shots.find((shot) => shot.id === selectedShot) ??
    storyboard?.shots[0];
  if (!storyboard || !selected)
    return <MissingState title="还没有可编辑的 Storyboard" href="brief" />;
  const currentStoryboard = storyboard;
  const currentShot = selected;
  const selectedAsset = assets.find((asset) => asset.id === selected.sourceAssetId);
  function exportScript() {
    const lines = ["# 视频制作脚本", "", `时长：${currentStoryboard.shots.reduce((sum, shot) => sum + shot.durationMs, 0) / 1000} 秒`,
      `配乐：${currentStoryboard.soundPlan?.background === "local-pulse" ? "本地电子节奏" : "无"}`, ""];
    currentStoryboard.shots.forEach((shot, index) => {
      lines.push(`## 镜头 ${index + 1}：${shot.purpose}`, "", `时长：${shot.durationMs / 1000} 秒`,
        `制作方式：${sourceLabels[shot.sourceStrategy] ?? shot.sourceStrategy}`, `画面意图：${shot.visual}`,
        `运镜意图：${shot.camera}`,
        ...(shot.sourceStrategy === "image-motion" ? ["实际执行：原图居中缓慢推近，不生成新视角，不执行真实横移、环绕或主体动作。"] : []),
        `字幕：${shot.caption}`, `旁白：${currentStoryboard.soundPlan?.narration ? shot.voiceover || "无" : "关闭"}`,
        `素材：${assets.find(asset => asset.id === shot.sourceAssetId)?.fileName ?? "待准备"}`,
        `素材 ID：${shot.sourceAssetId || "待准备"}`, "");
    });
    const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `script-${currentStoryboard.id}.md`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function updateSelected(field: keyof Shot, value: string | number) {
    setStoryboard({
      ...currentStoryboard,
      status: "draft",
      shots: currentStoryboard.shots.map((shot) =>
        shot.id === currentShot.id ? { ...shot, [field]: value,
          ...(["sourceStrategy", "sourceAssetId", "visual", "camera"].includes(field) ? { productionPlan: undefined } : {}),
          ...(field === "sourceAssetId" ? { selectionOwner: value ? "user" as const : "platform" as const } : {}),
          ...(field === "sourceStrategy" ? {
          strategyOwner: "user" as const,
          sourceAssetId: assets.find((asset) => asset.id === shot.sourceAssetId)?.kind ===
            (value === "blender-3d" ? "model" : value === "user-video" ? "video" : "image") ? shot.sourceAssetId : "",
          ...(value === "image-to-video" ? { referenceFraming: "portrait-soft", backgroundFill: "soft", videoPrompt: shot.videoPrompt || [shot.visual, shot.camera, ...(shot.continuity ?? [])].join("\n") } : {}),
        } : {}) } : shot,
      ),
    });
  }
  function move(offset: number) {
    const index = currentStoryboard.shots.findIndex(
      (shot) => shot.id === currentShot.id,
    );
    const target = index + offset;
    if (target < 0 || target >= currentStoryboard.shots.length) return;
    const shots = [...currentStoryboard.shots];
    [shots[index], shots[target]] = [shots[target], shots[index]];
    setStoryboard({ ...currentStoryboard, status: "draft", shots });
  }
  return (
    <div className="storyboard-page">
      {materials ? <section className="material-report" aria-label="素材准备结果" aria-live="polite">
        <div className="material-report-heading">
          {["queued", "running"].includes(materials.status) ? <LoaderCircle className="spin" size={18} /> : materials.status === "completed" ? <Check size={18} /> : <AlertCircle size={18} />}
          <strong>{materialPhases[materials.phase] ?? (materials.status === "completed" ? "素材已就绪" : materials.status === "needs_attention" ? `${materials.checks.filter((check) => !check.ready).length} 个镜头待处理` : "素材准备未完成")}</strong>
          {materials.checks.length ? <span>{materials.checks.filter((check) => check.ready).length} / {materials.checks.length} 镜头可生成{unsaved ? "（修改前）" : ""}</span> : null}
        </div>
        {materials.errorMessage ? <p role="alert">{materials.errorMessage}</p> : null}
        {materials.changes.length ? <ul>{materials.changes.map((change, index) => <li key={`${change.shotId}-${index}`}>镜头 {change.order}：{change.message}</li>)}</ul>
          : materials.status === "completed" ? <p>现有素材已通过检查，无需重复准备。</p> : null}
        {materials.checks.filter((check) => !check.ready).map((check) => <button className="material-issue" key={check.shotId} onClick={() => setSelectedShot(check.shotId)}><span>镜头 {check.order}</span><span>{check.reason}</span><ChevronRight size={16} /></button>)}
      </section> : null}
      <aside className="shot-timeline">
        <div className="timeline-heading">
          <div>
            <span className="section-kicker">镜头时间线</span>
            <h2>{storyboard.shots.length} 个镜头</h2>
          </div>
          <span>{(storyboard.totalDurationMs / 1000).toFixed(1)}s</span>
        </div>
        <div className="shot-list">
          {storyboard.shots.map((shot, index) => (
            <button
              key={shot.id}
              onClick={() => setSelectedShot(shot.id)}
              aria-pressed={selected.id === shot.id}
              className="shot-item"
            >
              <span className="shot-number">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="shot-thumb">
                {assets.find((asset) => asset.id === shot.sourceAssetId)?.kind === "image" ? (
                  <Image src={assets.find((asset) => asset.id === shot.sourceAssetId)!.previewUrl} alt="" fill sizes="80px" unoptimized />
                ) : <Film size={20} />}
              </span>
              <span className="shot-copy">
                <strong>{shot.purpose}</strong>
                <small>
                  {(shot.durationMs / 1000).toFixed(1)} 秒 ·{" "}
                  {sourceLabels[shot.sourceStrategy] ?? "待准备"}
                </small>
              </span>
              <span className="shot-readiness">{unsaved ? "已修改" : materials?.checks.find((check) => check.shotId === shot.id)?.ready === false ? "待处理" : materials?.checks.find((check) => check.shotId === shot.id)?.ready ? "已就绪" : assets.some((asset) => asset.id === shot.sourceAssetId) ? "已选素材" : "待准备"}</span>
            </button>
          ))}
        </div>
      </aside>
      <main className="video-workspace">
        <div className="video-toolbar">
          <span>
            <CircleGauge size={16} />
            {storyboard.output.width} x {storyboard.output.height} ·{" "}
            {storyboard.output.fps}fps
          </span>
          <div>
            <Tooltip label="上移镜头">
              <button
                className="icon-button inverse"
                onClick={() => move(-1)}
                aria-label="上移镜头"
                disabled={locked || Boolean(busy)}
              >
                <ArrowUp size={17} />
              </button>
            </Tooltip>
            <Tooltip label="下移镜头">
              <button
                className="icon-button inverse"
                onClick={() => move(1)}
                aria-label="下移镜头"
                disabled={locked || Boolean(busy)}
              >
                <ArrowDown size={17} />
              </button>
            </Tooltip>
            <Tooltip label="导出当前脚本"><button className="icon-button inverse" aria-label="导出当前脚本" onClick={exportScript}><Download size={17} /></button></Tooltip>
          </div>
        </div>
        <div className="vertical-stage">
          {selectedAsset?.kind === "image" ? (
            <Image src={selectedAsset.previewUrl} alt={`${selected.purpose} 所选素材`} fill sizes="450px" loading="eager" unoptimized style={{ objectFit: selected.fit ?? "contain" }} />
          ) : selectedAsset?.kind === "video" ? (
            <video src={selectedAsset.previewUrl} controls playsInline aria-label="所选视频素材" style={{ objectFit: selected.fit ?? "contain" }} />
          ) : selectedAsset?.kind === "model" ? <div className="empty-media"><Layers3 size={32} /><span>GLB 已选择</span></div>
            : <div className="empty-media"><Film size={32} /><span>未选择素材</span></div>}
          <div className="safe-area" />
          <div className="stage-caption">
            <span>{selected.caption}</span>
          </div>
        </div>
        <div className="stage-description">
          <strong>{selected.purpose}</strong>
          <span>{selected.visual}</span>
        </div>
        {selected.productionPlan ? <section className="production-summary" aria-label="镜头制作计划">
          <strong>{sourceLabels[selected.sourceStrategy]}{selected.productionPlan.needsPreview && !selected.previewRunId ? " · 先试片" : ""}</strong>
          <p>{selected.productionPlan.reason}</p>
          {selected.productionPlan.blocker ? <p role="alert">{selected.productionPlan.blocker}</p> : null}
          {selected.selectionOwner === "user" ? <Button variant="secondary" size="compact" disabled={locked || Boolean(busy)} onClick={() => updateSelected("sourceAssetId", "")}>交由平台重新选择</Button> : null}
        </section> : null}
        <ShotPreview key={`${storyboard.id}-${selected.id}-${materials?.previewGenerationRunId ?? ""}`} projectId={projectId} storyboardId={storyboard.id} shotId={selected.id}
          disabled={previewDisabled || Boolean(busy)} save={() => save(storyboard.shots)}
          onActiveChange={onPreviewActive} onAdopted={onPreviewAdopted} />
      </main>
      <aside className="shot-inspector">
        <div className="section-heading">
          <div>
            <span className="section-kicker">镜头 {storyboard.shots.indexOf(selected) + 1}</span>
            <h2>{selected.purpose}</h2>
          </div>
        </div>
        <fieldset className="media-fields" disabled={locked || Boolean(busy)}>
        <div className="sound-plan">
          <label>整片配乐<select aria-label="整片配乐" value={storyboard.soundPlan?.background ?? "none"} onChange={(event) => setStoryboard({ ...currentStoryboard, status: "draft", soundPlan: { narration: storyboard.soundPlan?.narration ?? false, background: event.target.value as "none" | "local-pulse" } })}>
            <option value="none">无配乐</option><option value="local-pulse">本地电子节奏</option>
          </select></label>
          <label className="narration-option"><input type="checkbox" checked={storyboard.soundPlan?.narration ?? false} onChange={(event) => setStoryboard({ ...currentStoryboard, status: "draft", soundPlan: { background: storyboard.soundPlan?.background ?? "none", narration: event.target.checked } })} />整片使用中文旁白</label>
        </div>
        <label>
          镜头目的
          <input
            value={selected.purpose}
            onChange={(e) => updateSelected("purpose", e.target.value)}
          />
        </label>
        <label>
          画面描述
          <textarea
            rows={5}
            value={selected.visual}
            onChange={(e) => updateSelected("visual", e.target.value)}
          />
        </label>
          <label>
            时长（秒）
            <input
              type="number"
              min="0.5"
              max="15"
              step="0.1"
              value={selected.durationMs / 1000}
              onChange={(e) =>
                updateSelected("durationMs", Math.round(Number(e.target.value) * 1000))
              }
            />
          </label>
        <details className="shot-advanced">
          <summary>高级设置</summary>
          <label>
            来源
            <select
              value={selected.sourceStrategy}
              onChange={(e) => updateSelected("sourceStrategy", e.target.value)}
            >
              <option value="image-motion">图片运动</option>
              <option value="generated-video" disabled>生成视频（尚未接入）</option>
              <option value="image-to-video">参考图生视频</option>
              <option value="user-video">视频素材</option>
              <option value="blender-3d">Blender 360° 环绕</option>
            </select>
          </label>
        {selected.sourceStrategy === "image-to-video" ? <>
          <label>视频提示词<textarea rows={5} maxLength={2500} value={selected.videoPrompt ?? ""} onChange={(event) => updateSelected("videoPrompt", event.target.value)} /></label>
        </> : null}
        {selected.sourceStrategy === "blender-3d" ? <label>渲染模板<select aria-label="渲染模板" value={selected.blenderTemplate ?? ""} onChange={(event) => updateSelected("blenderTemplate", event.target.value)}><option value="">选择模板</option><option value="orbit-360">完整 360° 环绕</option></select></label> : null}
        <label>
          镜头素材
          <select aria-label="镜头素材" value={selected.sourceAssetId ?? ""} onChange={(event) => updateSelected("sourceAssetId", event.target.value)}>
            <option value="">选择项目素材</option>
            {assets.filter((asset) => asset.kind === (selected.sourceStrategy === "blender-3d" ? "model" : selected.sourceStrategy === "user-video" ? "video" : "image")).map((asset) => (
              <option key={asset.id} value={asset.id}>{asset.fileName}</option>
            ))}
          </select>
        </label>
        {!selectedAsset ? <p className="material-gap" role="status">当前镜头尚无素材，可自动准备或添加素材。</p>
          : selectedAsset.kind !== (selected.sourceStrategy === "blender-3d" ? "model" : selected.sourceStrategy === "user-video" ? "video" : "image")
          ? <p className="material-gap" role="status">当前为参考图片，准备时将检查可用的生成方式。</p>
          : <p className="material-selected"><Check size={14} />{selectedAsset.fileName}</p>}
        <div className="asset-picker" role="group" aria-label="项目素材预览">
          {assets.filter((asset) => asset.kind === (selected.sourceStrategy === "blender-3d" ? "model" : selected.sourceStrategy === "user-video" ? "video" : "image")).map((asset) =>
            <button key={asset.id} type="button" title={asset.fileName} aria-label={`选择素材 ${asset.fileName}`} aria-pressed={asset.id === selected.sourceAssetId}
              onClick={() => updateSelected("sourceAssetId", asset.id)}>
              {asset.kind === "image" ? <Image src={asset.previewUrl} alt="" width={72} height={54} unoptimized /> : <Film size={20} />}
            </button>)}
        </div>
        {selected.sourceStrategy === "user-video" ? <label>素材入点（毫秒）<input type="number" min="0" step="100" value={selected.sourceStartMs ?? 0} onChange={(event) => updateSelected("sourceStartMs", Number(event.target.value))} /></label> : null}
        <label>构图<select aria-label="构图" value={selected.fit ?? "contain"} onChange={(event) => updateSelected("fit", event.target.value)}><option value="contain">完整画面</option><option value="cover">居中裁切</option></select></label>
        {selectedAsset?.kind === "image" ? <ImageCropDialog key={`${selected.id}-${selectedAsset.id}`} projectId={projectId} asset={selectedAsset} disabled={locked || Boolean(busy)} onApply={(asset) => applyCrop(selected.id, asset)} /> : null}
        <Button variant="secondary" size="compact" disabled={!selectedAsset} onClick={() => setStoryboard({ ...currentStoryboard, status: "draft", shots: currentStoryboard.shots.map((shot) => shot.sourceStrategy === selected.sourceStrategy ? { ...shot, sourceAssetId: selected.sourceAssetId, selectionOwner: "user" } : shot) })}>应用到同类镜头</Button>
        </details>
        <label className="upload-button media-upload"><Paperclip size={16} />添加素材<input type="file" accept="image/*,video/*,audio/*,.glb" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file, selected.id); event.target.value = ""; }} /></label>
        <label>
          旁白
          <textarea
            rows={3}
            value={selected.voiceover}
            onChange={(e) => updateSelected("voiceover", e.target.value)}
          />
        </label>
        <label>
          字幕
          <input
            value={selected.caption}
            maxLength={40}
            onChange={(e) => updateSelected("caption", e.target.value)}
          />
        </label>
        <div className="inspector-actions">
          <Button
            variant="secondary"
            onClick={() => save(storyboard.shots)}
            disabled={Boolean(busy)}
          >
            <Save size={16} />
            保存分镜
          </Button>
        </div>
        </fieldset>
      </aside>
      <footer className="approval-bar">
        <div>
          <strong>{storyboard.title}</strong>
          <span>{locked ? "生成中，暂不可编辑" : unsaved ? "有未保存修改" : "已保存"}</span>
        </div>
        <div className="storyboard-commands">
        <Button variant="ghost" onClick={approve} disabled={locked || Boolean(busy)}>生成选项</Button>
        <Button variant="secondary" onClick={() => void autoMaterials()} disabled={locked || Boolean(busy)}>
          {busy === "auto-materials" ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}自动准备素材
        </Button>
        <Button
          onClick={() => void autoMaterials(true)}
          disabled={locked || Boolean(busy)}
        >
          {busy === "approve-storyboard" ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Film size={17} />
          )}
          准备并生成视频
        </Button>
        </div>
      </footer>
    </div>
  );
}

function GenerationView({
  storyboard,
  generation,
  readiness,
  busy,
  generate,
  assets,
  quality,
  setQuality,
  audioAssetId,
  setAudioAssetId,
  narration,
  setNarration,
  runAction,
}: {
  storyboard: Storyboard | null;
  generation: GenerationRun | null;
  readiness: Workspace["generationReadiness"];
  busy: string;
  generate: () => void;
  assets: AssetVersion[];
  quality: string;
  setQuality: (value: string) => void;
  audioAssetId: string;
  setAudioAssetId: (value: string) => void;
  narration: boolean;
  setNarration: (value: boolean) => void;
  runAction: (action: string) => Promise<void>;
}) {
  const active = Boolean(generation && ["queued", "running", "composing"].includes(generation.status));
  const latest = Array.from(new Map(generation?.shotRuns.map((shot) => [shot.shotId, shot]) ?? []).values());
  return (
    <div className="content-frame generation-page">
      <header className="generation-header">
        <div>
          <span className="section-kicker">媒体生产</span>
          <h2>{generation ? "生成运行" : "准备生成"}</h2>
          <p>
            {generation
              ? `运行 ${generation.id.slice(0, 8)}`
              : "当前分镜"}
          </p>
        </div>
        <div className="generation-actions">
        {generation ? <Status value={generation.status} /> : null}
        {active ? <Button variant="secondary" disabled={Boolean(busy)} onClick={() => runAction("cancellation")}>停止任务</Button> : (
          <Button
            onClick={generate}
            disabled={!storyboard || storyboard.status !== "approved" || !readiness.ready || Boolean(busy)}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Play size={17} />
            )}
            {generation ? "按当前分镜生成" : "开始生成"}
          </Button>
        )}
        </div>
      </header>
      <fieldset className="generation-options settings-form" disabled={active || Boolean(busy)}>
        <label>输出尺寸<select value={quality} onChange={(event) => setQuality(event.target.value)}><option value="standard">1080 x 1920</option><option value="preview">540 x 960</option></select></label>
        <label>背景音频<select value={audioAssetId} onChange={(event) => setAudioAssetId(event.target.value)}><option value="">无背景音频</option>{assets.filter((asset) => asset.kind === "audio").map((asset) => <option key={asset.id} value={asset.id}>{asset.fileName}</option>)}</select></label>
        <label className="narration-option"><input type="checkbox" checked={narration} onChange={(event) => setNarration(event.target.checked)} />生成本地中文旁白</label>
      </fieldset>
      {!readiness.ready ? <div className="workspace-error" role="status"><AlertCircle size={18} /><span>{readiness.reason}</span><Link href="storyboard">返回分镜</Link></div> : null}
      {generation?.errorMessage ? <div className="workspace-error" role="alert"><AlertCircle size={18} /><span>{generation.errorMessage}</span></div> : null}
      {generation?.mode === "ai-video" ? <p>累计参考费用：USD {generation.estimatedUsd}；实际扣费以供应商账单为准。</p> : null}
      {generation && ["failed", "interrupted", "cancelled"].includes(generation.status) ? <Button variant="secondary" disabled={Boolean(busy)} onClick={() => runAction("resumption")}><RefreshCw size={16} />继续未完成任务</Button> : null}
      {generation ? (
        <section className="run-list">
          {latest.map((run, index) => (
            <article className="run-item" key={run.id} aria-label={`镜头 ${index + 1} 结果`}>
            <div className="run-row">
              <span className="run-index">{index + 1}</span>
              <div>
                <strong>
                  {run.purpose || storyboard?.shots.find((shot) => shot.id === run.shotId)
                    ?.purpose || "镜头"}
                </strong>
                <span>
                  {run.strategy} · 尝试 {run.attempt}
                </span>
              </div>
              <Status value={run.status} />
              <Tooltip label={`重做镜头 ${index + 1}`}><button className="icon-button" disabled={active || Boolean(busy) || generation.mode === "legacy-test-preview"} aria-label={`重做镜头 ${index + 1}`} onClick={() => runAction(`shots/${run.shotId}/retries`)}><RefreshCw size={16} /></button></Tooltip>
            </div>
            {run.errorMessage ? <p className="shot-error">{run.errorMessage}</p> : null}
            {run.providerRequestId ? <p className="shot-error">上游任务：{run.providerRequestId} · {run.providerStatus ?? "已提交"}</p> : null}
            {run.artifactId ? <video className="shot-result-video" src={`/api/v1/artifacts/${run.artifactId}/content`} controls playsInline preload="metadata" aria-label={`镜头 ${index + 1} 视频`} /> : null}
            </article>
          ))}
        </section>
      ) : (
        <section className="generation-ready" data-ready={readiness.ready}>
          <Layers3 size={28} />
          <div>
            <strong>{storyboard?.shots.length ?? 0} 个镜头</strong>
            <span>
              {readiness.ready
                ? readiness.mode === "ai-video" ? `图生视频 · 估算 USD ${readiness.estimatedUsd}` : readiness.mode === "local-ai-video" ? "本地 Wan 图生视频 · 依赖与推理在启动时检查" : "已上传素材 · 图片运动 / 视频剪辑 · 字幕合成"
                : readiness.reason}
            </span>
          </div>
          <Mountain size={28} />
        </section>
      )}
      {generation?.status === "completed" ? (
        <div className="completion-strip">
          <Check size={18} />
          镜头合成完成
          {generation.canRecompose ? <Button variant="secondary" size="compact" disabled={Boolean(busy)} onClick={() => runAction("recomposition")}><RefreshCw size={16} />优化画幅并合成</Button> : null}
          <Button asChild size="compact">
            <Link href="final">
              查看成片
              <ChevronRight size={16} />
            </Link>
          </Button>
        </div>
      ) : null}
    </div>
  );
}

function FinalView({
  projectId,
  generation,
  artifact,
}: {
  projectId: string;
  generation: GenerationRun | null;
  artifact: Artifact | null;
}) {
  if (!generation || !artifact)
    return <MissingState title="还没有可查看的成片" href="generation" />;
  return (
    <div className="final-page">
      <main className="final-stage">
        <video
          src={artifact.previewUrl}
          controls
          playsInline
          aria-label="生成的视频成片"
        />
        <div className="final-stage-meta">
          <span>
            <Check size={16} />
            媒体结构检查通过
          </span>
          <span>{generation.mode === "local-blender" ? "Blender 渲染与素材合成" : generation.mode === "local-ai-video" ? "本地 AI 视频与素材合成" : generation.mode === "ai-video" ? "AI 视频与素材合成" : generation.mode === "uploaded-media" ? "上传素材合成" : "旧测试预览"}</span>
        </div>
      </main>
      <aside className="final-details">
        <span className="section-kicker">生成完成</span>
        <h1>成片已生成</h1>
          <p>{generation.audioMode === "narration-background-mix" ? "本地中文旁白、背景音频与素材原声混合" : generation.audioMode === "local-narration" ? "本地中文旁白与素材原声混合" : generation.audioMode === "local-soundtrack" ? "本地电子节奏与素材原声混合" : generation.audioMode === "background-mix" ? "背景音频与素材原声混合" : "保留素材原声；无原声片段静音"}</p>
        <dl>
          <div>
            <dt>尺寸</dt>
            <dd>
              {artifact.width} x {artifact.height}
            </dd>
          </div>
          <div>
            <dt>时长</dt>
            <dd>{(artifact.durationMs / 1000).toFixed(1)} 秒</dd>
          </div>
          <div>
            <dt>文件</dt>
            <dd>{formatBytes(artifact.sizeBytes)}</dd>
          </div>
          <div>
            <dt>运行成本</dt>
            <dd>{generation.costCny == null ? "尚未计量" : `¥${generation.costCny}`}</dd>
          </div>
        </dl>
        <Button asChild>
          <a href={`${artifact.previewUrl}?download=true`} download>
            <Download size={17} />
            下载 MP4
          </a>
        </Button>
        <Button asChild variant="secondary">
          <Link href={`/projects/${projectId}/storyboard`}>
            <RefreshCw size={16} />
            编辑当前分镜
          </Link>
        </Button>
        <div className="artifact-trace">
          <ExternalLink size={16} />
          <span>Artifact {artifact.id.slice(0, 8)} · 运行 {generation.id.slice(0, 8)}</span>
        </div>
      </aside>
    </div>
  );
}

function MissingState({ title, href }: { title: string; href: string }) {
  const params = useParams<{ projectId: string }>();
  return (
    <div className="center-state">
      <AlertCircle size={28} />
      <h2>{title}</h2>
      <Button asChild>
        <Link href={`/projects/${params.projectId}/${href}`}>返回上一步</Link>
      </Button>
    </div>
  );
}

function formatBytes(bytes: number) {
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
