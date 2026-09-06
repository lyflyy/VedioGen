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
  RefreshCw,
  Rocket,
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
  | "routing"
  | "playground"
  | "invocations";

const sectionMeta: Record<Section, { title: string; description: string }> = {
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
        <Status value="active" />
      </header>
      {current === "model-providers" ? <ProvidersPanel /> : null}
      {current === "credentials" ? <CredentialsPanel /> : null}
      {current === "deployments" ? <DeploymentsPanel /> : null}
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

function ProvidersPanel() {
  const resource = useResource<{ items: Provider[] }>("/admin/model-providers");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await post("/admin/model-providers", {
        id: form.get("id"),
        displayName: form.get("displayName"),
        adapterType: form.get("adapterType"),
        baseUrl: form.get("baseUrl"),
        region: form.get("region"),
        enabled: true,
      });
      formElement.reset();
      setOpen(false);
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
        <Button onClick={() => setOpen((value) => !value)}>
          <Plus size={16} />
          添加平台
        </Button>
      }
    >
      {open ? (
        <form className="admin-form" onSubmit={submit}>
          <label>
            平台 ID
            <input
              required
              name="id"
              pattern="[a-z][a-z0-9-]*"
              placeholder="openai-compatible"
            />
          </label>
          <label>
            显示名称
            <input
              required
              name="displayName"
              placeholder="OpenAI Compatible"
            />
          </label>
          <label>
            适配器
            <select name="adapterType">
              <option value="openai-compatible">OpenAI Compatible</option>
              <option value="anthropic">Anthropic</option>
              <option value="fake">Fake Provider</option>
            </select>
          </label>
          <label>
            区域
            <input required name="region" defaultValue="global" />
          </label>
          <label className="admin-form-wide">
            Base URL
            <input
              required
              name="baseUrl"
              type="url"
              placeholder="https://api.example.com/v1"
            />
          </label>
          <FormFooter busy={busy} error={error} label="创建平台" />
        </form>
      ) : null}
      <PanelState loading={resource.loading} error={resource.error} />
      <div className="admin-list">
        {resource.data?.items.map((item) => (
          <article className="admin-row" key={item.id}>
            <span className="admin-row-icon">
              <ServerCog size={18} />
            </span>
            <div>
              <strong>{item.displayName}</strong>
              <span>
                {item.adapterType} · {item.region}
              </span>
            </div>
            <code>{item.id}</code>
            <Status value={item.status} />
          </article>
        ))}
      </div>
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
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create");
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await post("/admin/model-credentials", {
        providerId: form.get("providerId"),
        alias: form.get("alias"),
        secret: form.get("secret"),
      });
      formElement.reset();
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
      await credentials.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "探测失败");
    } finally {
      setBusy("");
    }
  }
  return (
    <AdminPanel icon={KeyRound} title="密钥与凭据">
      <form className="admin-form credential-form" onSubmit={submit}>
        <label>
          模型平台
          <select name="providerId" required>
            {providers.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.displayName}
              </option>
            ))}
          </select>
        </label>
        <label>
          凭据别名
          <input name="alias" required placeholder="生产环境 Key" />
        </label>
        <label className="admin-form-wide">
          API Key
          <input
            name="secret"
            type="password"
            required
            autoComplete="new-password"
            placeholder="输入后只可覆盖，不可读取"
          />
        </label>
        <FormFooter busy={busy === "create"} error={error} label="加密保存" />
      </form>
      <PanelState
        loading={credentials.loading || providers.loading}
        error={credentials.error || providers.error}
      />
      <div className="admin-list">
        {credentials.data?.items.map((item) => (
          <article className="admin-row" key={item.id}>
            <span className="admin-row-icon">
              <KeyRound size={18} />
            </span>
            <div>
              <strong>{item.alias}</strong>
              <span>
                {item.providerId} · 尾号 {item.lastFour}
              </span>
            </div>
            <Status value={item.status} />
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
              连通性测试
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
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("create");
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      await post("/admin/model-deployments", {
        displayName: form.get("displayName"),
        providerId: form.get("providerId"),
        physicalModelId: form.get("physicalModelId"),
        credentialId: form.get("credentialId"),
        capabilities: String(form.get("capabilities"))
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        timeoutSeconds: 120,
        maxContextTokens: 32000,
      });
      formElement.reset();
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
      await deployments.reload();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "部署探测失败");
    } finally {
      setBusy("");
    }
  }
  return (
    <AdminPanel icon={Waypoints} title="可路由部署">
      <form className="admin-form" onSubmit={submit}>
        <label>
          部署名称
          <input name="displayName" required placeholder="Creative Model CN" />
        </label>
        <label>
          模型平台
          <select name="providerId" required>
            {providers.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.displayName}
              </option>
            ))}
          </select>
        </label>
        <label>
          物理模型 ID
          <input name="physicalModelId" required placeholder="model-v1" />
        </label>
        <label>
          调用凭据
          <select name="credentialId" required>
            {credentials.data?.items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.alias} · {item.lastFour}
              </option>
            ))}
          </select>
        </label>
        <label className="admin-form-wide">
          能力标签
          <input
            name="capabilities"
            required
            defaultValue="text,image-input,structured-output,zh-CN"
          />
        </label>
        <FormFooter busy={busy === "create"} error={error} label="创建部署" />
      </form>
      <PanelState
        loading={
          deployments.loading || providers.loading || credentials.loading
        }
        error={deployments.error || providers.error || credentials.error}
      />
      <div className="admin-list">
        {deployments.data?.items.map((item) => (
          <article className="admin-row deployment-row" key={item.id}>
            <span className="admin-row-icon">
              <Waypoints size={18} />
            </span>
            <div>
              <strong>{item.displayName}</strong>
              <span>
                {item.providerId} / {item.physicalModelId}
              </span>
              <small>{item.capabilities.join(" · ")}</small>
            </div>
            <Status value={item.status} />
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
}: {
  busy: boolean;
  error: string;
  label: string;
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
      <Button disabled={busy}>
        {busy ? (
          <LoaderCircle className="spin" size={16} />
        ) : (
          <Plus size={16} />
        )}
        {label}
      </Button>
    </div>
  );
}
