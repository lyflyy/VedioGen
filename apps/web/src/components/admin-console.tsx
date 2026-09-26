"use client";

import {
  AlertCircle,
  Check,
  ChevronRight,
  FlaskConical,
  KeyRound,
  LoaderCircle,
  Network,
  Plus,
  Pencil,
  RefreshCw,
  Rocket,
  Save,
  ServerCog,
  Waypoints,
} from "lucide-react";
import {
  FormEvent,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import { Status } from "@/components/ui/status";
import { Tooltip } from "@/components/ui/tooltip";
import Link from "next/link";
import { api, post } from "@/lib/api";
import type {
  Credential,
  Deployment,
  ModelInvocation,
  PlaygroundRun,
  Provider,
  RoutingDraft,
  RoutingVersion,
} from "@/lib/types";

type Section =
  | "model-providers"
  | "credentials"
  | "deployments"
  | "video-settings"
  | "routing"
  | "playground"
  | "invocations";

const sectionMeta: Record<Section, { title: string; description: string }> = {
  "video-settings": { title: "视频执行", description: "图生视频部署与单任务估算预算" },
  "model-providers": {
    title: "模型平台",
    description: "维护兼容接口和适配器，不在业务流程中绑定具体厂商。",
  },
  credentials: {
    title: "API Key",
    description: "密钥仅写入加密存储，界面与调用记录不会返回原文。",
  },
  deployments: {
    title: "模型部署",
    description: "将物理模型、凭据和能力标签组合成可探测的部署。",
  },
  routing: {
    title: "能力路由",
    description: "业务只引用能力别名，通过版本化策略切换主模型与回退模型。",
  },
  playground: {
    title: "模型测试台",
    description: "使用固定样例验证鉴权、结构化输出和中文内容能力。",
  },
  invocations: {
    title: "调用记录",
    description: "查看路由选择、耗时、成本和脱敏输入输出。",
  },
};

export function AdminConsole({ section }: { section: string }) {
  if (!(section in sectionMeta)) return null;
  const current = section as Section;
  return (
    <div className="admin-page page-frame">
      <header className="page-header admin-page-header">
        <div>
          <span className="section-kicker">模型网关</span>
          <h1>{sectionMeta[current].title}</h1>
          <p>{sectionMeta[current].description}</p>
        </div>
      </header>
      {current === "model-providers" ? <ProvidersPanel /> : null}
      {current === "credentials" ? <CredentialsPanel /> : null}
      {current === "deployments" ? <DeploymentsPanel /> : null}
      {current === "video-settings" ? <VideoSettingsPanel /> : null}
      {current === "routing" ? <RoutingPanel /> : null}
      {current === "playground" ? <PlaygroundPanel /> : null}
      {current === "invocations" ? <InvocationsPanel /> : null}
    </div>
  );
}

function useResource<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api<T>(path));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "载入失败");
    } finally {
      setLoading(false);
    }
  }, [path]);
  useEffect(() => {
    void Promise.resolve().then(reload);
  }, [reload]);
  return { data, error, loading, reload };
}

function PanelState({ loading, error }: { loading: boolean; error: string }) {
  if (loading)
    return (
      <div className="admin-state" role="status">
        <LoaderCircle className="spin" size={20} />
        正在载入配置
      </div>
    );
  if (error)
    return (
      <div className="inline-error" role="alert">
        <AlertCircle size={18} />
        <div>
          <strong>配置无法载入</strong>
          <span>{error}</span>
        </div>
      </div>
    );
  return null;
}

type VideoSettings = {
  enabled: boolean;
  backend: "fal" | "comfyui";
  localUrl: string;
  width: number;
  height: number;
  steps: number;
  decodeMode: "full" | "tiled";
  timeoutSeconds: number;
  deploymentId: string | null;
  estimatedUsdPerSecond: string;
  maxRunUsd: string;
  externalCallsAllowed: boolean;
  localCallsAllowed: boolean;
  narrationEnabled: boolean;
  narrationModelPath: string;
  blenderEnabled: boolean;
  blenderExecutable: string;
  blenderTimeoutSeconds: number;
};

function VideoSettingsPanel() {
  const settings = useResource<VideoSettings>("/admin/video-settings");
  const deployments = useResource<{ items: Deployment[] }>("/admin/model-deployments");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [backend, setBackend] = useState<"fal" | "comfyui" | null>(null);
  const local = (backend ?? settings.data?.backend) === "comfyui";
  const [probe, setProbe] = useState<{ ready: boolean; missing: string[]; version: string | null } | null>(null);
  async function checkBlender() {
    setBusy(true);
    setMessage("");
    try {
      const result = await post<{ version: string }>("/admin/video-settings/blender-probe", {});
      setMessage(`${result.version} · 可执行文件检查通过`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Blender 检查失败"); }
    finally { setBusy(false); }
  }
  async function checkLocal() {
    setBusy(true);
    setMessage("");
    setProbe(null);
    try { setProbe(await post("/admin/video-settings/local-probe", {})); }
    catch (error) { setMessage(error instanceof Error ? error.message : "检查失败"); }
    finally { setBusy(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    try {
      await api("/admin/video-settings", { method: "PUT", body: JSON.stringify({
        enabled: form.get("enabled") === "on", deploymentId: form.get("deploymentId") || null,
        backend: local ? "comfyui" : "fal",
        localUrl: form.get("localUrl") ?? settings.data?.localUrl,
        width: Number(form.get("width") ?? settings.data?.width), height: Number(form.get("height") ?? settings.data?.height),
        steps: Number(form.get("steps") ?? settings.data?.steps), timeoutSeconds: Number(form.get("timeoutSeconds") ?? settings.data?.timeoutSeconds),
        decodeMode: form.get("decodeMode") ?? settings.data?.decodeMode ?? "tiled",
        estimatedUsdPerSecond: form.get("price") ?? settings.data?.estimatedUsdPerSecond,
        maxRunUsd: form.get("budget") ?? settings.data?.maxRunUsd,
        narrationEnabled: form.get("narrationEnabled") === "on",
        narrationModelPath: form.get("narrationModelPath") || "",
        blenderEnabled: form.get("blenderEnabled") === "on",
        blenderExecutable: form.get("blenderExecutable") || "",
        blenderTimeoutSeconds: Number(form.get("blenderTimeoutSeconds")),
      }) });
      await settings.reload();
      setProbe(null);
      setMessage(local ? "配置已保存；尚未验证真实推理。" : "配置已保存；尚未执行付费生成验证。");
    } catch (error) { setMessage(error instanceof Error ? error.message : "保存失败"); }
    finally { setBusy(false); }
  }
  return <AdminPanel icon={ServerCog} title="图生视频">
    <PanelState loading={settings.loading || deployments.loading} error={settings.error || deployments.error} />
    {settings.data && !settings.loading && !deployments.loading && !deployments.error ? <form className="admin-form video-settings-form" onSubmit={submit}>
      <label>执行方式<select value={local ? "comfyui" : "fal"} onChange={(event) => { setBackend(event.target.value as "fal" | "comfyui"); setProbe(null); setMessage(""); }} disabled={busy}>
        <option value="comfyui">本地 ComfyUI · Wan 2.2</option><option value="fal">云端 fal · Kling</option>
      </select></label>
      {local ? <>
        <label>本地服务地址<input name="localUrl" type="url" required defaultValue={settings.data.localUrl} /></label>
        <label>原生宽度<input name="width" type="number" min="256" max="832" step="32" required defaultValue={settings.data.width} /></label>
        <label>原生高度<input name="height" type="number" min="256" max="832" step="32" required defaultValue={settings.data.height} /></label>
        <label>采样步数<input name="steps" type="number" min="4" max="30" required defaultValue={settings.data.steps} /></label>
        <label>视频解码<select name="decodeMode" aria-label="视频解码" defaultValue={settings.data.decodeMode ?? "tiled"}><option value="tiled">分块解码（低显存）</option><option value="full">整段解码</option></select></label>
        <label>等待上限（秒）<input name="timeoutSeconds" type="number" min="300" max="7200" required defaultValue={settings.data.timeoutSeconds} /></label>
      </> : <>
      <label>执行部署<select name="deploymentId" defaultValue={settings.data.deploymentId ?? ""}>
        <option value="">尚未配置</option>
        {deployments.data?.items.filter((item) => item.capabilities.includes("image-to-video")).map((item) => <option key={item.id} value={item.id}>{item.displayName}</option>)}
      </select></label>
      <label>参考单价（USD / 秒）<input name="price" type="number" required min="0" max="100" step="0.0001" defaultValue={settings.data.estimatedUsdPerSecond} /></label>
      <label>单任务累计估算上限（USD）<input name="budget" type="number" required min="0" max="1000" step="0.0001" defaultValue={settings.data.maxRunUsd} /></label>
      </>}
      <label className="video-enabled"><input name="enabled" type="checkbox" defaultChecked={settings.data.enabled} />{local ? "启用本地视频生成" : "启用付费视频调用"}</label>
      <label className="narration-model">中文声音模型路径<input name="narrationModelPath" maxLength={1024} defaultValue={settings.data.narrationModelPath} /></label>
      <label className="video-enabled"><input name="narrationEnabled" type="checkbox" defaultChecked={settings.data.narrationEnabled} />启用本地 Piper 旁白</label>
      <label className="admin-form-wide">Blender 可执行文件<input name="blenderExecutable" maxLength={1024} defaultValue={settings.data.blenderExecutable} /></label>
      <label>Blender 超时（秒）<input name="blenderTimeoutSeconds" type="number" min="60" max="7200" required defaultValue={settings.data.blenderTimeoutSeconds} /></label>
      <label className="video-enabled"><input name="blenderEnabled" type="checkbox" defaultChecked={settings.data.blenderEnabled} />启用 Blender 环绕</label>
      <Button type="submit" disabled={busy}><Check size={16} />保存视频配置</Button>
      <Button type="button" variant="secondary" disabled={busy} onClick={() => void checkBlender()}><FlaskConical size={16} />检查已保存的 Blender</Button>
      {local ? <Button type="button" variant="secondary" disabled={busy} onClick={() => void checkLocal()}><FlaskConical size={16} />检查已保存的本地配置</Button> : null}
    </form> : null}
    <div className="video-settings-notes">
    <p>配置状态：{settings.data?.enabled ? "已启用" : "未启用"} · 真实生成尚待验证</p>
    <p>{local ? "本地推理 · 无视频 API 费用 · 消耗本机 GPU 与运行时间" : "费用为管理员参考单价估算，实际扣费以供应商账单为准。"}</p>
    {settings.data && !(local ? settings.data.localCallsAllowed : settings.data.externalCallsAllowed) ? <p role="status">{local ? "当前环境禁止本地模型访问。" : "当前环境禁止外部调用。"}</p> : null}
    {probe ? <div role="status"><p>{probe.ready ? "服务与模型清单就绪，实际推理尚待验证" : "本地依赖未就绪"} · ComfyUI {probe.version ?? "未知版本"}</p>{probe.missing.length ? <ul>{probe.missing.map((item) => <li key={item}>{item}</li>)}</ul> : null}</div> : null}
    {message ? <p role="status">{message}</p> : null}
    </div>
  </AdminPanel>;
}

function ProvidersPanel() {
  const resource = useResource<{ items: Provider[] }>("/admin/model-providers");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Provider | null>(null);
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const payload = {
        ...(!editing ? { id: form.get("id") } : {}),
        displayName: form.get("displayName"),
        adapterType: form.get("adapterType"),
        baseUrl: form.get("baseUrl"),
        region: form.get("region"),
        enabled: form.get("enabled") === "on",
      };
      if (editing && (payload.baseUrl !== editing.baseUrl || payload.adapterType !== editing.adapterType) && !window.confirm("修改请求地址或适配器会影响此平台下所有模型，保存后需重新能力探测。继续？")) return;
      if (editing) await api(`/admin/model-providers/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      else await post("/admin/model-providers", payload);
      formElement.reset();
      setOpen(false);
      setEditing(null);
      setMessage("平台配置已保存");
      await resource.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "平台创建失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <AdminPanel
      icon={ServerCog}
      title="已接入平台"
      action={
        <Button disabled={busy} onClick={() => { setEditing(null); setError(""); setOpen(true); }}>
          <Plus size={16} />
          添加平台
        </Button>
      }
    >
      {open ? (
        <form key={editing?.id ?? "new"} className="admin-form model-config-form" onSubmit={submit}>
          <h3 className="admin-form-wide">{editing ? `编辑平台：${editing.displayName}` : "新建平台"}</h3>
          <label>
            平台 ID
            <input
              required
              name="id"
              defaultValue={editing?.id ?? ""}
              disabled={Boolean(editing)}
              pattern="[a-z][a-z0-9-]*"
              placeholder="openai-compatible"
            />
          </label>
          <label>
            显示名称
            <input
              required
              name="displayName"
              defaultValue={editing?.displayName ?? ""}
              placeholder="OpenAI Compatible"
            />
          </label>
          <label>
            适配器
            <select name="adapterType" defaultValue={editing?.adapterType ?? "openai-compatible"}>
              <option value="openai-compatible">OpenAI Compatible</option>
              <option value="fal-video">fal 视频队列</option>
              <option value="fake">Fake Provider</option>
            </select>
          </label>
          <label>
            区域
            <input required name="region" defaultValue={editing?.region ?? "global"} />
          </label>
          <label className="admin-form-wide">
            Base URL
            <input
              required
              name="baseUrl"
              defaultValue={editing?.baseUrl ?? ""}
              type="url"
              placeholder="https://api.example.com/v1"
            />
          </label>
          <label className="admin-checkbox"><input type="checkbox" name="enabled" defaultChecked={editing?.enabled ?? true} />启用平台</label>
          <FormFooter busy={busy} error={error} label={editing ? "保存平台" : "创建平台"} cancelAction={<Button type="button" variant="ghost" disabled={busy} onClick={() => { setOpen(false); setEditing(null); setError(""); }}>取消</Button>} />
        </form>
      ) : null}
      <PanelState loading={resource.loading} error={resource.error} />
      {message ? <p role="status">{message}</p> : null}
      <div className="admin-list">
        {resource.data?.items.map((item) => (
          <article className="admin-row config-row" key={item.id}>
            <span className="admin-row-icon">
              <ServerCog size={18} />
            </span>
            <div>
              <strong>{item.displayName}</strong>
              <span>
                {item.adapterType} · {item.region}
              </span>
              <small className="config-address">{item.baseUrl}</small>
            </div>
            <code>{item.id}</code>
            <Status value={item.status} />
            <Tooltip label="编辑平台"><button className="icon-button" aria-label={`编辑平台：${item.displayName}`} disabled={busy} onClick={() => { setEditing(item); setOpen(true); setError(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}><Pencil size={16} /></button></Tooltip>
          </article>
        ))}
      </div>
      <div className="config-links"><Link href="/admin/credentials">配置 API Key</Link><Link href="/admin/deployments">配置模型</Link></div>
    </AdminPanel>
  );
}

function CredentialsPanel() {
  const credentials = useResource<{ items: Credential[] }>(
    "/admin/model-credentials",
  );
  const providers = useResource<{ items: Provider[] }>(
    "/admin/model-providers",
  );
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Credential | null>(null);
  const [message, setMessage] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create");
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const secret = String(form.get("secret") ?? "");
      if (editing) {
        if (secret && !window.confirm("更换 Key 会影响引用此凭据的模型，保存后需重新能力探测。继续？")) return;
        await api(`/admin/model-credentials/${editing.id}`, { method: "PATCH", body: JSON.stringify({ alias: form.get("alias"), ...(secret ? { secret } : {}) }) });
      } else await post("/admin/model-credentials", {
        providerId: form.get("providerId"),
        alias: form.get("alias"),
        secret: form.get("secret"),
      });
      formElement.reset();
      setEditing(null);
      setMessage("凭据已加密保存，未返回 Key 原文");
      await credentials.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "密钥保存失败");
    } finally {
      setBusy("");
    }
  }
  async function probe(id: string) {
    setBusy(id);
    setError("");
    try {
      await post(`/admin/model-credentials/${id}/probe`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "探测失败");
    } finally {
      await credentials.reload();
      setBusy("");
    }
  }
  async function resume(id: string) {
    if (!window.confirm("已在中转站处理余额或额度问题？恢复后下一次请求将重新尝试模型。")) return;
    setBusy(id);
    setError("");
    try {
      await post(`/admin/model-credentials/${id}/cooldown-reset`);
      await credentials.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复调度失败");
    } finally { setBusy(""); }
  }
  return (
    <AdminPanel icon={KeyRound} title="密钥与凭据">
      <form key={editing?.id ?? "new"} className="admin-form credential-form model-config-form" onSubmit={submit}>
        <h3 className="admin-form-wide">{editing ? `编辑凭据：${editing.alias}` : "添加 API Key"}</h3>
        <label>
          模型平台
          <select name="providerId" required disabled={Boolean(editing)} defaultValue={editing?.providerId}>
            {providers.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.displayName}
              </option>
            ))}
          </select>
        </label>
        <label>
          凭据别名
          <input name="alias" required defaultValue={editing?.alias ?? ""} placeholder="生产环境 Key" />
        </label>
        <label className="admin-form-wide">
          API Key
          <input
            name="secret"
            type="password"
            required={!editing}
            autoComplete="new-password"
            placeholder={editing ? "留空保留原 Key；填写则更换" : "输入后只可覆盖，不可读取"}
          />
        </label>
        <FormFooter busy={Boolean(busy)} error={error} label={editing ? "保存凭据" : "加密保存"} cancelAction={editing ? <Button type="button" variant="ghost" disabled={Boolean(busy)} onClick={() => { setEditing(null); setError(""); }}>取消编辑</Button> : null} />
      </form>
      {message ? <p role="status">{message}</p> : null}
      <PanelState
        loading={credentials.loading || providers.loading}
        error={credentials.error || providers.error}
      />
      <div className="admin-list">
        {credentials.data?.items.map((item) => (
          <article className="admin-row config-row" key={item.id}>
            <span className="admin-row-icon">
              <KeyRound size={18} />
            </span>
            <div>
              <strong>{item.alias}</strong>
              <span>
                {item.providerId} · 尾号 {item.lastFour}
              </span>
              {item.cooldown ? <small role="status">{item.cooldown.message}</small> : null}
            </div>
            <Status value={item.cooldown ? "needs_attention" : item.status} />
            <Tooltip label="编辑凭据"><button className="icon-button" aria-label={`编辑凭据：${item.alias}`} disabled={Boolean(busy)} onClick={() => { setEditing(item); setError(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}><Pencil size={16} /></button></Tooltip>
            <Button
              variant="secondary"
              size="compact"
              onClick={() => item.cooldown?.errorCode === "QUOTA_EXCEEDED" ? resume(item.id) : probe(item.id)}
              disabled={Boolean(busy)}
            >
              {busy === item.id ? (
                <LoaderCircle className="spin" size={14} />
              ) : (
                <RefreshCw size={14} />
              )}
              {item.cooldown?.errorCode === "QUOTA_EXCEEDED" ? "恢复调度" : "连通性测试"}
            </Button>
          </article>
        ))}
      </div>
    </AdminPanel>
  );
}

function DeploymentsPanel() {
  const deployments = useResource<{ items: Deployment[] }>(
    "/admin/model-deployments",
  );
  const providers = useResource<{ items: Provider[] }>(
    "/admin/model-providers",
  );
  const credentials = useResource<{ items: Credential[] }>(
    "/admin/model-credentials",
  );
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<Deployment | null>(null);
  const [providerId, setProviderId] = useState("");
  const [message, setMessage] = useState("");
  const availableKeys = credentials.data?.items.filter(item => item.providerId === providerId && item.status === "active") ?? [];
  const selectedProvider = providers.data?.items.find(item => item.id === providerId);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create");
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const payload = {
        displayName: form.get("displayName"),
        providerId: form.get("providerId"),
        physicalModelId: form.get("physicalModelId"),
        credentialId: form.get("credentialId"),
        capabilities: form.getAll("capabilities"),
        timeoutSeconds: Number(form.get("timeoutSeconds")),
        maxContextTokens: form.get("maxContextTokens") ? Number(form.get("maxContextTokens")) : null,
      };
      if (editing) await api(`/admin/model-deployments/${editing.id}`, { method: "PATCH", body: JSON.stringify(payload) });
      else await post("/admin/model-deployments", payload);
      formElement.reset();
      setEditing(null); setProviderId("");
      setMessage("模型配置已保存；连接参数变更后需能力探测，通过后原有路由会使用新配置。");
      await deployments.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "部署创建失败");
    } finally {
      setBusy("");
    }
  }
  async function probe(id: string) {
    setBusy(id);
    setError("");
    try {
      await post(`/admin/model-deployments/${id}/probe`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "部署探测失败");
    } finally {
      await deployments.reload();
      setBusy("");
    }
  }
  return (
    <AdminPanel icon={Waypoints} title="可路由部署" action={<Button disabled={Boolean(busy)} onClick={() => { setEditing(null); setProviderId(""); setError(""); }}><Plus size={16} />添加模型</Button>}>
      <form key={editing?.id ?? "new"} className="admin-form model-config-form" onSubmit={submit}>
        <h3 className="admin-form-wide">{editing ? `编辑模型：${editing.displayName}` : "新建模型"}</h3>
        <label>
          部署名称
          <input name="displayName" required defaultValue={editing?.displayName ?? ""} placeholder="Creative Model CN" />
        </label>
        <label>
          模型平台
          <select name="providerId" required value={providerId} onChange={event => setProviderId(event.target.value)}>
            <option value="">选择模型平台</option>
            {providers.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.displayName}
              </option>
            ))}
          </select>
        </label>
        <label>
          物理模型 ID
          <input name="physicalModelId" required defaultValue={editing?.physicalModelId ?? ""} placeholder="gpt-5.4-mini" />
        </label>
        <label>
          调用凭据
          <select key={providerId} name="credentialId" required defaultValue={editing?.providerId === providerId ? editing.credentialId : ""}>
            <option value="">选择该平台的 Key</option>
            {availableKeys.map((item) => (
              <option key={item.id} value={item.id}>
                {item.alias} · {item.lastFour}
              </option>
            ))}
          </select>
        </label>
        {selectedProvider ? <p className="admin-form-wide config-address">请求基址：{selectedProvider.baseUrl} · <Link href="/admin/model-providers">编辑平台地址</Link></p> : null}
        {providerId && !availableKeys.length ? <p role="status" className="admin-form-wide">该平台暂无有效 Key。<Link href="/admin/credentials">添加 API Key</Link></p> : null}
        <label>超时（秒）<input name="timeoutSeconds" type="number" min="1" max="600" required defaultValue={editing?.timeoutSeconds ?? 120} /></label>
        <label>上下文上限（Token）<input name="maxContextTokens" type="number" min="1" defaultValue={editing?.maxContextTokens ?? ""} /></label>
        <fieldset className="admin-form-wide capability-options"><legend>能力标签</legend>{Array.from(new Set(["text", "image-input", "structured-output", "zh-CN", "image-to-video", ...(editing?.capabilities ?? [])])).map(value => <label key={value}><input type="checkbox" name="capabilities" value={value} defaultChecked={(editing?.capabilities ?? ["text", "image-input", "structured-output", "zh-CN"]).includes(value)} />{{ text: "文本", "image-input": "图片理解", "structured-output": "结构化输出", "zh-CN": "中文", "image-to-video": "图生视频" }[value] ?? value}</label>)}</fieldset>
        <FormFooter busy={Boolean(busy)} error={error} label={editing ? "保存模型" : "创建部署"} cancelAction={editing ? <Button type="button" variant="ghost" disabled={Boolean(busy)} onClick={() => { setEditing(null); setProviderId(""); setError(""); }}>取消编辑</Button> : null} />
      </form>
      {message ? <p role="status">{message}</p> : null}
      <div className="config-links"><Link href="/admin/credentials">管理 API Key</Link><Link href="/admin/routing">选择默认模型与路由</Link></div>
      <PanelState
        loading={
          deployments.loading || providers.loading || credentials.loading
        }
        error={deployments.error || providers.error || credentials.error}
      />
      <div className="admin-list">
        {deployments.data?.items.map((item) => (
          <article className="admin-row deployment-row config-row" key={item.id}>
            <span className="admin-row-icon">
              <Waypoints size={18} />
            </span>
            <div>
              <strong>{item.displayName}</strong>
              <span>
                {item.providerId} / {item.physicalModelId}
              </span>
              <small>{item.capabilities.join(" · ")}</small>
              {item.cooldown ? <small role="status">{item.cooldown.message}</small> : null}
            </div>
            <Status value={item.cooldown ? "needs_attention" : item.status} />
            <Tooltip label="编辑模型"><button className="icon-button" aria-label={`编辑模型：${item.displayName}`} disabled={Boolean(busy)} onClick={() => { setEditing(item); setProviderId(item.providerId); setError(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}><Pencil size={16} /></button></Tooltip>
            <Button
              variant="secondary"
              size="compact"
              onClick={() => probe(item.id)}
              disabled={Boolean(busy)}
            >
              {busy === item.id ? (
                <LoaderCircle className="spin" size={14} />
              ) : (
                <RefreshCw size={14} />
              )}
              能力探测
            </Button>
          </article>
        ))}
      </div>
    </AdminPanel>
  );
}

function RoutingPanel() {
  const draft = useResource<RoutingDraft>("/admin/model-routing/drafts");
  const versions = useResource<{ items: RoutingVersion[] }>(
    "/admin/model-routing/versions",
  );
  const deployments = useResource<{ items: Deployment[] }>(
    "/admin/model-deployments",
  );
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy("draft");
    setError("");
    try {
      const deploymentId = form.get("deploymentId");
      const shared = {
        requirements: ["text", "structured-output", "zh-CN"],
        primaryDeploymentId: deploymentId,
        fallbackDeploymentIds: [],
        timeoutSeconds: 120,
        maxAttempts: 2,
        budgetClass: "low",
        fallbackOn: ["TIMEOUT", "PROVIDER_UNAVAILABLE", "SCHEMA_INVALID"],
      };
      await post("/admin/model-routing/drafts", {
        bindings: [
          { capabilityAlias: "creative-advisor", ...shared },
          { capabilityAlias: "storyboard-generator", ...shared },
        ],
      });
      await draft.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "路由草稿创建失败");
    } finally {
      setBusy("");
    }
  }
  async function validateAndPublish() {
    if (!draft.data) return;
    setBusy("publish");
    setError("");
    try {
      await post(`/admin/model-routing/${draft.data.id}/validation`);
      await post(`/admin/model-routing/${draft.data.id}/publication`, {
        changeNote: "Admin console publication",
      });
      await Promise.all([draft.reload(), versions.reload()]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "路由发布失败");
    } finally {
      setBusy("");
    }
  }
  const bindings = draft.data?.bindings ?? [];
  return (
    <div className="admin-split">
      <AdminPanel
        icon={Network}
        title="当前草稿"
        action={
          draft.data ? (
            <Button onClick={validateAndPublish} disabled={Boolean(busy)}>
              <Rocket size={16} />
              验证并发布
            </Button>
          ) : undefined
        }
      >
        <form className="routing-create" onSubmit={createDraft}>
          <label>
            主部署
            <select name="deploymentId" required>
              {deployments.data?.items
                .filter((item) => item.status === "ready")
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.displayName}
                  </option>
                ))}
            </select>
          </label>
          <Button variant="secondary" disabled={Boolean(busy)}>
            <Plus size={16} />
            新建草稿
          </Button>
        </form>
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        <PanelState
          loading={draft.loading || deployments.loading}
          error={draft.error || deployments.error}
        />
        {bindings.map((binding) => (
          <div className="route-diagram" key={binding.capabilityAlias}>
            <span>{binding.capabilityAlias}</span>
            <ChevronRight size={18} />
            <strong>
              {deployments.data?.items.find(
                (item) => item.id === binding.primaryDeploymentId,
              )?.displayName ?? binding.primaryDeploymentId}
            </strong>
            <Status value={draft.data?.status ?? "draft"} />
          </div>
        ))}
        {bindings[0] ? (
          <dl className="route-details">
            <div>
              <dt>所需能力</dt>
              <dd>{bindings[0].requirements.join("、")}</dd>
            </div>
            <div>
              <dt>超时 / 尝试</dt>
              <dd>
                {bindings[0].timeoutSeconds}s / {bindings[0].maxAttempts} 次
              </dd>
            </div>
            <div>
              <dt>成本等级</dt>
              <dd>{bindings[0].budgetClass}</dd>
            </div>
          </dl>
        ) : null}
      </AdminPanel>
      <AdminPanel icon={Rocket} title="发布历史">
        <PanelState loading={versions.loading} error={versions.error} />
        <div className="admin-list">
          {versions.data?.items.map((item) => (
            <article className="admin-row version-row" key={item.id}>
              <span className="version-number">v{item.version}</span>
              <div>
                <strong>{item.changeNote}</strong>
                <span>{item.bindings.length} 条能力绑定</span>
              </div>
              <Status value={item.status} />
            </article>
          ))}
        </div>
      </AdminPanel>
    </div>
  );
}

function PlaygroundPanel() {
  const [result, setResult] = useState<PlaygroundRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function run(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      setResult(
        await post<PlaygroundRun>("/admin/model-playground-runs", {
          capabilityAlias: "creative-advisor",
          routeTarget: "published",
          fixtureId: form.get("fixtureId"),
          checks: ["authentication", "structured-output", "zh-CN"],
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "测试运行失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <AdminPanel icon={FlaskConical} title="固定样例检查">
      <form className="playground-controls" onSubmit={run}>
        <label>
          测试素材
          <select name="fixtureId">
            <option value="zhangxue-800x">张雪 800X</option>
            <option value="cfmoto-800mt">春风 800MT</option>
          </select>
        </label>
        <label>
          能力别名
          <input value="creative-advisor" readOnly />
        </label>
        <label>
          路由版本
          <input value="已发布版本" readOnly />
        </label>
        <Button disabled={busy}>
          {busy ? (
            <LoaderCircle className="spin" size={16} />
          ) : (
            <FlaskConical size={16} />
          )}
          运行测试
        </Button>
      </form>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      {result ? (
        <div className="playground-result">
          <header>
            <div>
              <strong>检查完成</strong>
              <span>所有输出均已脱敏</span>
            </div>
            <Status value={result.status} />
          </header>
          <div className="check-grid">
            {result.checks.map((item) => (
              <div key={item.check}>
                <Check size={16} />
                <span>{item.check}</span>
                <small>{item.durationMs}ms</small>
              </div>
            ))}
          </div>
          <dl className="redacted-output">
            <div>
              <dt>输入</dt>
              <dd>{result.redactedInput}</dd>
            </div>
            <div>
              <dt>输出</dt>
              <dd>{result.redactedOutput}</dd>
            </div>
          </dl>
        </div>
      ) : (
        <div className="admin-empty">
          <FlaskConical size={24} />
          <strong>选择样例后运行检查</strong>
          <span>结果会同时写入调用记录。</span>
        </div>
      )}
    </AdminPanel>
  );
}

function InvocationsPanel() {
  const resource = useResource<{ items: ModelInvocation[] }>(
    "/admin/model-invocations?capabilityAlias=creative-advisor",
  );
  const [selected, setSelected] = useState<ModelInvocation | null>(null);
  const [error, setError] = useState("");
  async function inspect(id: string) {
    setError("");
    try {
      setSelected(await api<ModelInvocation>(`/admin/model-invocations/${id}`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "详情载入失败");
    }
  }
  return (
    <div className="admin-split invocation-layout">
      <AdminPanel icon={Network} title="最近调用">
        <PanelState loading={resource.loading} error={resource.error} />
        <div className="admin-list">
          {resource.data?.items.map((item) => (
            <button
              className="admin-row invocation-row"
              key={item.id}
              onClick={() => inspect(item.id)}
            >
              <span className="admin-row-icon">
                <Network size={18} />
              </span>
              <div>
                <strong>{item.capabilityAlias}</strong>
                <span>
                  {item.durationMs}ms · ¥{item.costCny}
                </span>
              </div>
              <Status value={item.status} />
              <ChevronRight size={16} />
            </button>
          ))}
        </div>
      </AdminPanel>
      <AdminPanel icon={ServerCog} title="调用详情">
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}
        {selected ? (
          <dl className="invocation-detail">
            <div>
              <dt>Trace ID</dt>
              <dd>{selected.traceId}</dd>
            </div>
            <div>
              <dt>部署</dt>
              <dd>{selected.deploymentId}</dd>
            </div>
            <div>
              <dt>实际模型</dt>
              <dd>{selected.providerModelId ?? "未记录"}</dd>
            </div>
            <div>
              <dt>Provider Request ID</dt>
              <dd>{selected.providerRequestId ?? "未返回"}</dd>
            </div>
            <div>
              <dt>Token</dt>
              <dd>
                {selected.inputTokens} / {selected.outputTokens}
              </dd>
            </div>
            <div>
              <dt>脱敏输入</dt>
              <dd>{selected.redactedInput}</dd>
            </div>
            <div>
              <dt>脱敏输出</dt>
              <dd>{selected.redactedOutput}</dd>
            </div>
          </dl>
        ) : (
          <div className="admin-empty">
            <Network size={24} />
            <strong>选择一条调用</strong>
            <span>查看路由和脱敏追踪信息。</span>
          </div>
        )}
      </AdminPanel>
    </div>
  );
}

function AdminPanel({
  icon: Icon,
  title,
  action,
  children,
}: {
  icon: typeof ServerCog;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="admin-panel">
      <header className="admin-panel-header">
        <div>
          <Icon size={18} />
          <h2>{title}</h2>
        </div>
        {action}
      </header>
      {children}
    </section>
  );
}

function FormFooter({
  busy,
  error,
  label,
  cancelAction,
}: {
  busy: boolean;
  error: string;
  label: string;
  cancelAction?: ReactNode;
}) {
  return (
    <div className="admin-form-footer">
      {error ? (
        <span className="form-error" role="alert">
          {error}
        </span>
      ) : (
        <span>必填字段会在提交前校验</span>
      )}
      {cancelAction}
      <Button disabled={busy}>
        {busy ? (
          <LoaderCircle className="spin" size={16} />
        ) : label.includes("保存") ? (
          <Save size={16} />
        ) : (
          <Plus size={16} />
        )}
        {label}
      </Button>
    </div>
  );
}
