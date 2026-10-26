export type AgentJob = {
  id: string;
  question: string;
  status: string;
  stage: string;
  intent: string;
  engine: string;
  created_at: string;
  elapsed_seconds: number | null;
  error: { code: string; message: string } | null;
};
export type AgentFact = {
  key: string;
  label: string;
  value: number | string | null;
  unit: string;
  as_of: string;
  evidence_id: string;
  source_id: string;
};
export type AgentCitation = {
  document_id: string;
  chunk_id: string;
  page: number;
  section: string;
  quote: string;
  content_hash: string;
  source: string;
  evidence_id: string;
  unavailable: boolean;
};
export type AgentDetail = AgentJob & {
  workflow_version: string;
  context: Record<string, unknown>;
  provider: Record<string, unknown>;
  usage: {
    input_tokens: number | null;
    output_tokens: number | null;
    estimated_cost_usd: number | null;
    provider_requests: number;
    tool_calls: number;
  };
  verification: Record<string, unknown>;
  answer: {
    title: string;
    execution_mode: string;
    findings: string[];
    claims: AgentFact[];
    citations: AgentCitation[];
    warnings: string[];
    numerical_verification: string;
    citation_verification: string;
    financial_validity: string;
  } | null;
};
export type AgentActivity = {
  sequence: number;
  kind: string;
  status: string;
  summary: string;
  elapsed_ms: number;
  data: Record<string, unknown>;
};
export type AgentEvidence = {
  id: string;
  tool: string;
  source_type: string;
  source_id: string;
  as_of: string;
  synthetic: boolean;
  checksum: string;
  provenance: Record<string, unknown>;
  warnings: string[];
  data: Record<string, unknown>;
};
export type AIStatus = {
  configured: boolean;
  provider: string;
  model: string;
  demo_available: boolean;
  embeddings_available: boolean;
  message: string;
};
export const modelQuestion =
  "Compare the forecasting models in the latest saved VANTAGE research experiment. Which performed best on QLIKE, and what limitations prevent us from declaring it superior?";
export function factValue(value: number | string | null, unit: string): string {
  if (value === null) return "Unavailable";
  if (typeof value === "string") return value;
  if (unit === "INR")
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(value);
  if (unit === "probability" || unit === "decimal weight")
    return value.toLocaleString("en-IN", { maximumFractionDigits: 6 });
  return Number.isInteger(value)
    ? value.toString()
    : Math.abs(value) < 0.0001
      ? value.toExponential(5)
      : value.toFixed(6);
}
