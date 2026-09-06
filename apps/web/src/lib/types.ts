export type ProjectStatus =
  | "intake"
  | "advising"
  | "brief_draft"
  | "brief_approved"
  | "storyboard_draft"
  | "storyboard_approved"
  | "generating"
  | "needs_attention"
  | "completed";

export interface Project {
  id: string;
  title: string;
  contentPackId: string;
  mode: string;
  targetPlatform: string;
  locale: string;
  status: ProjectStatus;
  currentBriefVersionId: string | null;
  currentStoryboardVersionId: string | null;
  rowVersion: number;
  createdAt: string;
  updatedAt: string;
}

export interface Workspace {
  project: Project;
  messages: Array<{ id: string; role: string; text: string; createdAt: string }>;
  facts: Array<{ id: string; key: string; value: unknown; status: string; confidence: number }>;
  evidenceItems: unknown[];
  assetVersions: unknown[];
  latestAdvisorRunId: string | null;
  activeGenerationRunId: string | null;
  generationReadiness: { ready: boolean; mode: string; reason: string | null };
}

export interface Proposal {
  proposalKey: string;
  name: string;
  positioning: string;
  audience: string[];
  primaryGoal: string;
  contentType: string;
  hook: { text: string; visual: string; durationMs: number };
  corePromise: string;
  visualPayoffs: string[];
  pacing: string;
  emotionalPeak: string;
  close: string;
  requiredAssets: string[];
  resourceEstimate: "low" | "medium" | "high";
  whyItFits: string[];
  limitations: string[];
}

export interface AdvisorRun {
  id: string;
  status: string;
  result: {
    diagnosis: { understoodGoal: string; opportunity: string; primaryRisk: string; missingInformation: string[] };
    proposals: Proposal[];
    recommendedProposalKey: string | null;
  };
}

export interface Brief {
  id: string;
  version: number;
  status: string;
  contentType: string;
  audience: string[];
  primaryGoal: string;
  hook: { text: string; visual: string; durationMs: number };
  corePromise: string;
  visualPayoffs: string[];
  pacing: string;
  emotionalPeak: string;
  cta: string;
  targetDurationMs: number;
  resourceEstimate: string;
}

export interface Shot {
  id: string;
  order: number;
  purpose: string;
  startMs: number;
  durationMs: number;
  visual: string;
  camera: string;
  voiceover: string;
  caption: string;
  sound: string;
  sourceStrategy: string;
  status: string;
}

export interface Storyboard {
  id: string;
  version: number;
  status: string;
  title: string;
  totalDurationMs: number;
  shots: Shot[];
  output: { aspectRatio: string; width: number; height: number; fps: number };
}

export interface GenerationRun {
  id: string;
  status: string;
  storyboardVersionId: string;
  shotRuns: Array<{ id: string; shotId: string; attempt: number; strategy: string; status: string }>;
  finalArtifactId: string | null;
  costCny: string;
}

export interface Artifact {
  id: string;
  status: string;
  mimeType: string;
  sizeBytes: number;
  width: number;
  height: number;
  durationMs: number;
  previewUrl: string;
}

export interface Provider {
  id: string;
  displayName: string;
  adapterType: string;
  baseUrl: string;
  region: string;
  enabled: boolean;
  status: string;
  updatedAt: string;
}

export interface Credential {
  id: string;
  providerId: string;
  alias: string;
  lastFour: string;
  status: string;
  lastSuccessAt: string | null;
}

export interface Deployment {
  id: string;
  displayName: string;
  providerId: string;
  physicalModelId: string;
  credentialId: string;
  capabilities: string[];
  status: string;
}

export interface RoutingBinding {
  capabilityAlias: string;
  requirements: string[];
  primaryDeploymentId: string;
  fallbackDeploymentIds: string[];
  timeoutSeconds: number;
  maxAttempts: number;
  budgetClass: string;
  fallbackOn: string[];
}

export interface RoutingDraft {
  id: string;
  bindings: RoutingBinding[];
  status: string;
  updatedAt: string;
}

export interface RoutingVersion {
  id: string;
  version: number;
  bindings: RoutingBinding[];
  status: string;
  changeNote: string;
  publishedAt: string;
}

export interface ModelInvocation {
  id: string;
  capabilityAlias: string;
  deploymentId: string;
  credentialId: string;
  status: string;
  inputTokens: number;
  outputTokens: number;
  durationMs: number;
  costCny: string;
  startedAt: string;
  redactedInput?: string;
  redactedOutput?: string;
  traceId?: string;
  providerRequestId?: string;
  providerModelId?: string;
}

export interface PlaygroundRun {
  id: string;
  status: string;
  checks: Array<{ check: string; status: string; durationMs: number }>;
  routeChain: ModelInvocation[];
  redactedInput: string;
  redactedOutput: string;
}
