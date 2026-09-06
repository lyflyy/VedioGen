"use client";

import { Check, Save } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, put } from "@/lib/api";

interface AccountBrief {
  accountGoal: string;
  audience: string[];
  tone: string[];
  publishingCadence: string;
  preferences: { durationSeconds?: number };
  rowVersion: number;
}

const defaults: AccountBrief = { accountGoal: "建立有辨识度的摩托车日更账号", audience: ["摩托车爱好者", "潜在购车用户"], tone: ["专业", "有冲击力", "不浮夸"], publishingCadence: "daily", preferences: { durationSeconds: 24 }, rowVersion: 0 };

export default function AccountBriefPage() {
  const [value, setValue] = useState(defaults);
  const [saved, setSaved] = useState(false);
  useEffect(() => { api<AccountBrief>("/account-brief").then(setValue).catch(() => undefined); }, []);

  async function save(event: FormEvent) {
    event.preventDefault();
    const next = await put<AccountBrief>("/account-brief", { contentPackId: "motorcycle", accountGoal: value.accountGoal, audience: value.audience, tone: value.tone, publishingCadence: value.publishingCadence, preferences: value.preferences, rowVersion: value.rowVersion || null });
    setValue(next); setSaved(true); window.setTimeout(() => setSaved(false), 1800);
  }

  return <div className="page-frame narrow-page"><header className="page-header"><div><h1>账号资料</h1><p>这些默认信息会复制到新项目，已有项目不会被静默修改。</p></div></header><form className="settings-form" onSubmit={save}>
    <section><h2>内容方向</h2><label>账号长期目标<textarea value={value.accountGoal} onChange={(e) => setValue({ ...value, accountGoal: e.target.value })} rows={3} /></label><label>主要受众<input value={value.audience.join("、")} onChange={(e) => setValue({ ...value, audience: e.target.value.split("、").filter(Boolean) })} /></label><label>表达语气<input value={value.tone.join("、")} onChange={(e) => setValue({ ...value, tone: e.target.value.split("、").filter(Boolean) })} /></label></section>
    <section><h2>发布习惯</h2><label>更新频率<select value={value.publishingCadence} onChange={(e) => setValue({ ...value, publishingCadence: e.target.value })}><option value="daily">每日更新</option><option value="weekdays">工作日</option><option value="weekly">每周</option><option value="custom">自定义</option></select></label><label>默认时长（秒）<input type="number" min="10" max="120" value={value.preferences.durationSeconds ?? 24} onChange={(e) => setValue({ ...value, preferences: { ...value.preferences, durationSeconds: Number(e.target.value) } })} /></label></section>
    <div className="sticky-form-actions"><span>{saved ? <><Check size={16} />已保存</> : `版本 ${value.rowVersion || 1}`}</span><Button type="submit"><Save size={17} />保存账号资料</Button></div>
  </form></div>;
}
