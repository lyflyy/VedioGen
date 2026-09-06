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
import { Button } from "@/components/ui/button";
import { Status } from "@/components/ui/status";
import { Tooltip } from "@/components/ui/tooltip";
import { api, post, put } from "@/lib/api";
import type {
  AdvisorRun,
  Artifact,
  Brief,
  GenerationRun,
  Proposal,
  Shot,
  Storyboard,
  Workspace,
} from "@/lib/types";

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
  const advisorStarted = useRef(false);

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
    setGeneration(nextGeneration);
    if (nextStoryboard?.shots.length)
      setSelectedShot((current) => current ?? nextStoryboard.shots[0].id);
    if (nextGeneration?.finalArtifactId)
      setArtifact(
        await api<Artifact>(`/artifacts/${nextGeneration.finalArtifactId}`),
      );
  }, [projectId]);

  useEffect(() => {
    void Promise.resolve()
      .then(hydrate)
      .catch((reason: Error) => setError(reason.message));
  }, [hydrate]);

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
        advisorStarted.current = false;
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
      await post(`/projects/${projectId}/messages`, {
        text: feedback,
        assetVersionIds: [],
      });
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
    try {
      await post(
        `/projects/${projectId}/creative-briefs/${brief.id}/approval`,
        {},
      );
      const run = await post<{ storyboardVersionId: string }>(
        `/projects/${projectId}/storyboard-runs`,
      );
      const next = await api<Storyboard>(
        `/projects/${projectId}/storyboards/${run.storyboardVersionId}`,
      );
      setStoryboard(next);
      await hydrate();
      router.push(`/projects/${projectId}/storyboard`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Brief 确认失败");
    } finally {
      setBusy("");
    }
  }

  async function saveStoryboard(
    nextShots = storyboard?.shots,
  ): Promise<Storyboard | null> {
    if (!storyboard || !nextShots) return null;
    setBusy("save-storyboard");
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
        },
      );
      setStoryboard(next);
      return next;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分镜保存失败");
    } finally {
      setBusy("");
    }
    return null;
  }

  async function approveStoryboard() {
    if (!storyboard) return;
    setBusy("approve-storyboard");
    try {
      const saved = await saveStoryboard(storyboard.shots);
      if (!saved) return;
      await post(`/projects/${projectId}/storyboards/${saved.id}/approval`, {});
      await hydrate();
      router.push(`/projects/${projectId}/generation`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分镜确认失败");
    } finally {
      setBusy("");
    }
  }

  async function generate() {
    if (!storyboard) return;
    setBusy("generation");
    setError("");
    try {
      const run = await post<GenerationRun>("/generation-runs", {
        projectId,
        storyboardVersionId: storyboard.id,
      });
      setGeneration(run);
      if (run.finalArtifactId)
        setArtifact(await api<Artifact>(`/artifacts/${run.finalArtifactId}`));
      await hydrate();
      router.push(`/projects/${projectId}/final`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "生成任务失败");
    } finally {
      setBusy("");
    }
  }

  if (!workspace)
    return (
      <div className="workspace-loading" role="status">
        <LoaderCircle className="spin" />
        正在恢复项目工作区
      </div>
    );

  return (
    <div className="project-page">
      <ProjectHeader project={workspace.project} activeStage={stage} />
      {error ? (
        <div className="workspace-error" role="alert">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button
            onClick={() => {
              setError("");
              hydrate();
            }}
          >
            重新载入
          </button>
        </div>
      ) : null}
      {stage === "intake" ? <Intake workspace={workspace} /> : null}
      {stage === "strategy" ? (
        <Strategy
          workspace={workspace}
          advisor={advisor}
          busy={busy}
          chooseProposal={chooseProposal}
          regenerateAdvice={regenerateAdvice}
        />
      ) : null}
      {stage === "brief" ? (
        <BriefView brief={brief} busy={busy} approve={approveBrief} />
      ) : null}
      {stage === "storyboard" ? (
        <StoryboardView
          storyboard={storyboard}
          selectedShot={selectedShot}
          setSelectedShot={setSelectedShot}
          setStoryboard={setStoryboard}
          save={saveStoryboard}
          approve={approveStoryboard}
          busy={busy}
        />
      ) : null}
      {stage === "generation" ? (
        <GenerationView
          storyboard={storyboard}
          generation={generation}
          readiness={workspace.generationReadiness}
          busy={busy}
          generate={generate}
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
  chooseProposal,
  regenerateAdvice,
}: {
  workspace: Workspace;
  advisor: AdvisorRun | null;
  busy: string;
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
        <LoaderCircle className="spin" />
        <div>
          <strong>正在形成创意判断</strong>
          <span>整理车型事实、视觉机会和制作约束</span>
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
        {workspace.messages.map((message) => (
          <div className="message-bubble user-message" key={message.id}>
            {message.text}
          </div>
        ))}
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
            <h2>{advisor.result.diagnosis.opportunity}</h2>
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
            <p>三个方案使用不同的内容机制，而不只是更换风格词。</p>
          </div>
          <span>推荐方案已标记</span>
        </div>
        <section className="proposal-grid">
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
                      : proposal.resourceEstimate}
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
            <strong>未使用外部资料</strong>
            <span>当前方向仅依据用户输入与内容方法。</span>
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
}: {
  brief: Brief | null;
  busy: string;
  approve: () => void;
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
        <p>确认将锁定此版本。后续修改会创建新的修订版。</p>
        <Button
          onClick={approve}
          disabled={Boolean(busy) || brief.status === "approved"}
        >
          {busy ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <ChevronRight size={17} />
          )}
          确认并生成脚本
        </Button>
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
}: {
  storyboard: Storyboard | null;
  selectedShot: string | null;
  setSelectedShot: (id: string) => void;
  setStoryboard: (value: Storyboard) => void;
  save: (shots?: Shot[]) => void;
  approve: () => void;
  busy: string;
}) {
  const selected =
    storyboard?.shots.find((shot) => shot.id === selectedShot) ??
    storyboard?.shots[0];
  if (!storyboard || !selected)
    return <MissingState title="还没有可编辑的 Storyboard" href="brief" />;
  const currentStoryboard = storyboard;
  const currentShot = selected;
  function updateSelected(field: keyof Shot, value: string | number) {
    setStoryboard({
      ...currentStoryboard,
      shots: currentStoryboard.shots.map((shot) =>
        shot.id === currentShot.id ? { ...shot, [field]: value } : shot,
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
    setStoryboard({ ...currentStoryboard, shots });
  }
  return (
    <div className="storyboard-page">
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
                <Image
                  src={
                    index === storyboard.shots.length - 1
                      ? "/images/motorcycle-road.jpg"
                      : "/images/motorcycle-studio.jpg"
                  }
                  alt=""
                  fill
                  sizes="80px"
                />
              </span>
              <span className="shot-copy">
                <strong>{shot.purpose}</strong>
                <small>
                  {(shot.durationMs / 1000).toFixed(1)} 秒 ·{" "}
                  {shot.sourceStrategy}
                </small>
              </span>
              <Status value={shot.status} />
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
              >
                <ArrowUp size={17} />
              </button>
            </Tooltip>
            <Tooltip label="下移镜头">
              <button
                className="icon-button inverse"
                onClick={() => move(1)}
                aria-label="下移镜头"
              >
                <ArrowDown size={17} />
              </button>
            </Tooltip>
          </div>
        </div>
        <div className="vertical-stage">
          <Image
            src={
              selected.order === storyboard.shots.length
                ? "/images/motorcycle-road.jpg"
                : "/images/motorcycle-studio.jpg"
            }
            alt={`${selected.purpose} 参考预览`}
            fill
            priority
            sizes="450px"
          />
          <div className="safe-area" />
          <div className="stage-caption">
            <span>{selected.caption}</span>
          </div>
          <button className="stage-play" aria-label="播放镜头预览">
            <Play fill="currentColor" size={24} />
          </button>
        </div>
        <div className="stage-description">
          <strong>{selected.purpose}</strong>
          <span>{selected.visual}</span>
        </div>
      </main>
      <aside className="shot-inspector">
        <div className="section-heading">
          <div>
            <span className="section-kicker">镜头 {selected.order}</span>
            <h2>{selected.purpose}</h2>
          </div>
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
        <div className="field-row">
          <label>
            时长（毫秒）
            <input
              type="number"
              min="500"
              max="10000"
              step="100"
              value={selected.durationMs}
              onChange={(e) =>
                updateSelected("durationMs", Number(e.target.value))
              }
            />
          </label>
          <label>
            来源
            <select
              value={selected.sourceStrategy}
              onChange={(e) => updateSelected("sourceStrategy", e.target.value)}
            >
              <option value="image-motion">图片运动</option>
              <option value="generated-video">生成视频</option>
              <option value="user-video">用户视频</option>
              <option value="blender-3d">Blender 3D</option>
            </select>
          </label>
        </div>
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
      </aside>
      <footer className="approval-bar">
        <div>
          <strong>{storyboard.title}</strong>
          <span>修改将保存为当前草稿，确认后启动生成前检查。</span>
        </div>
        <Button
          onClick={approve}
          disabled={Boolean(busy) || storyboard.status === "approved"}
        >
          {busy === "approve-storyboard" ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <Film size={17} />
          )}
          确认分镜
        </Button>
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
}: {
  storyboard: Storyboard | null;
  generation: GenerationRun | null;
  readiness: Workspace["generationReadiness"];
  busy: string;
  generate: () => void;
}) {
  return (
    <div className="content-frame generation-page">
      <header className="generation-header">
        <div>
          <span className="section-kicker">媒体生产</span>
          <h2>{generation ? "生成运行" : "准备生成"}</h2>
          <p>
            {generation
              ? `运行 ${generation.id.slice(0, 8)}`
              : "确认资源和镜头后生成可下载的竖屏预览。"}
          </p>
        </div>
        {generation ? (
          <Status value={generation.status} />
        ) : (
          <Button
            onClick={generate}
            disabled={!storyboard || !readiness.ready || Boolean(busy)}
          >
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Play size={17} />
            )}
            开始生成
          </Button>
        )}
      </header>
      {generation ? (
        <section className="run-list">
          {generation.shotRuns.map((run, index) => (
            <div className="run-row" key={run.id}>
              <span className="run-index">{index + 1}</span>
              <div>
                <strong>
                  {storyboard?.shots.find((shot) => shot.id === run.shotId)
                    ?.purpose ?? "镜头"}
                </strong>
                <span>
                  {run.strategy} · 尝试 {run.attempt}
                </span>
              </div>
              <Status value={run.status} />
            </div>
          ))}
        </section>
      ) : (
        <section className="generation-ready" data-ready={readiness.ready}>
          <Layers3 size={28} />
          <div>
            <strong>{storyboard?.shots.length ?? 0} 个镜头</strong>
            <span>
              {readiness.ready
                ? "图片运动 + 确定性合成 · 测试预览"
                : readiness.reason}
            </span>
          </div>
          <Mountain size={28} />
        </section>
      )}
      {generation?.status === "completed" ? (
        <div className="completion-strip">
          <Check size={18} />
          所有镜头与合成检查已完成
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
            媒体检查通过
          </span>
          <span>Preview v1</span>
        </div>
      </main>
      <aside className="final-details">
        <span className="section-kicker">生成完成</span>
        <h1>视频可以交付</h1>
        <p>竖屏画幅、视频编码和音轨已经通过自动检查。</p>
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
            <dd>¥{generation.costCny}</dd>
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
            创建新版本
          </Link>
        </Button>
        <div className="artifact-trace">
          <ExternalLink size={16} />
          <span>Artifact {artifact.id.slice(0, 8)} · 可追溯到分镜版本</span>
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
