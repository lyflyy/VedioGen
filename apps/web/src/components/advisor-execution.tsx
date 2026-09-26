"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check, Circle, Clock3, LoaderCircle, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";

export type AdvisorCall = { id: string; at: string; title: string; status: string; detail: string;
  model?: string; provider?: string; requestId?: string; errorCode?: string; durationMs?: number;
  inputTokens?: number; outputTokens?: number };
export const advisorActivityPath = (projectId: string) =>
  `/projects/${projectId}/activity?category=model&capabilityAlias=creative-advisor&pageSize=10`;

export function AdvisorExecution({ projectId, busy, error, saved, baselineIds, inputCount, assetCount }: {
  projectId: string; busy: boolean; error: string; saved: boolean; baselineIds: string[] | null;
  inputCount: number; assetCount: number;
}) {
  const [calls, setCalls] = useState<AdvisorCall[]>([]);
  const [logError, setLogError] = useState("");
  const [clock, setClock] = useState(0);
  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function load() {
      try {
        const data = await api<{ items: AdvisorCall[] }>(advisorActivityPath(projectId), { signal: controller.signal });
        if (!stopped) { setCalls(data.items); setLogError(""); setClock(Date.now()); }
      } catch (reason) {
        if (!stopped) setLogError(reason instanceof Error ? reason.message : "执行日志读取失败");
      } finally {
        if (!stopped && busy) timer = setTimeout(load, 2000);
      }
    }
    void load();
    return () => { stopped = true; controller.abort(); clearTimeout(timer); };
  }, [projectId, busy, baselineIds]);
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [busy]);

  const current = baselineIds ? calls.find(call => !baselineIds.includes(call.id)) : (!busy ? calls[0] : undefined);
  const waiting = busy && current?.status === "calling";
  const validated = current?.status === "succeeded";
  const failed = !busy && Boolean(error);
  const title = failed ? "创意建议未完成" : waiting ? "等待模型响应" : busy ? "正在提交创意请求" : saved ? "创意建议已保存" : "等待生成建议";
  const elapsed = waiting && current ? Math.max(0, Math.floor((clock - Date.parse(current.at)) / 1000)) : null;
  const steps = [
    { title: "项目输入", detail: `${inputCount} 条文字输入 · ${assetCount} 项素材`, state: "completed" },
    { title: "模型调用", detail: current ? `${current.provider ?? "模型平台"} · ${current.model ?? "未记录模型"}` : busy ? "等待调用记录" : "尚无本轮调用记录", state: waiting ? "running" : validated ? "completed" : failed ? "failed" : busy ? "running" : "pending" },
    { title: "结构化校验", detail: validated ? "输出已通过本地 Schema 校验" : current?.errorCode === "SCHEMA_INVALID" ? "输出格式未通过校验" : "等待有效模型输出", state: validated ? "completed" : current?.errorCode === "SCHEMA_INVALID" ? "failed" : "pending" },
    { title: "建议保存", detail: saved && !busy && !error ? "建议可供选择" : "等待本轮结果", state: saved && !busy && !error ? "completed" : "pending" },
  ];
  return <section className="advisor-execution" aria-label="创意生成执行过程">
    <header className="advisor-execution-heading">
      <div role="status">{failed ? <AlertCircle size={20} /> : busy ? <LoaderCircle size={20} className="spin" /> : saved ? <Check size={20} /> : <Circle size={20} />}<h2>{title}</h2></div>
      {elapsed !== null ? <span className="execution-elapsed"><Clock3 size={14} />已等待 {elapsed} 秒</span> : null}
      <Link href={`/projects/${projectId}/logs`}>全部执行日志</Link>
    </header>
    <ol className="advisor-execution-steps">{steps.map(step => <li key={step.title} data-state={step.state}>
      {step.state === "completed" ? <Check size={17} /> : step.state === "running" ? <LoaderCircle size={17} className="spin" /> : step.state === "failed" ? <AlertCircle size={17} /> : <Circle size={17} />}
      <div><strong>{step.title}</strong><span>{step.detail}</span></div>
    </li>)}</ol>
    {logError ? <p className="inline-error" role="alert">执行日志暂不可用：{logError}</p> : null}
    <details className="advisor-call-details" open={busy || failed}>
      <summary>最近调用记录 · {Math.min(calls.length, 3)} 条</summary>
      {!calls.length ? <p>{busy ? "尚未收到模型调用记录" : "暂无模型调用记录"}</p> : <ol>{calls.slice(0, 3).map(call => <li key={call.id}>
        <div className="advisor-call-heading"><time dateTime={call.at}>{new Date(call.at).toLocaleString("zh-CN")}</time><strong>{call.provider} · {call.model}</strong><span>{({ calling: "调用中", succeeded: "成功", failed: "失败" } as Record<string, string>)[call.status] ?? call.status}</span></div>
        {call.detail ? <pre>{call.detail}</pre> : null}
        <dl><div><dt>记录 ID</dt><dd>{call.id}</dd></div>{call.status !== "calling" ? <div><dt>耗时</dt><dd>{((call.durationMs ?? 0) / 1000).toFixed(1)} 秒</dd></div> : null}
          {call.requestId ? <div><dt>上游请求 ID</dt><dd>{call.requestId}</dd></div> : null}
          {call.errorCode ? <div><dt>错误码</dt><dd>{call.errorCode}</dd></div> : null}
          {call.status === "succeeded" ? <div><dt>Token</dt><dd>{call.inputTokens ?? 0} 输入 / {call.outputTokens ?? 0} 输出</dd></div> : null}</dl>
      </li>)}</ol>}
    </details>
  </section>;
}
