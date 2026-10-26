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

export type FinancialDocument = {
  id: string;
  filename: string;
  content_hash: string;
  source: string;
  company: string | null;
  reporting_period: string | null;
  publication_date: string | null;
  uploaded_at: string;
  status: string;
  page_count: number;
  chunk_count: number;
  version: string;
  metadata: Record<string, unknown>;
  error: { code: string; message: string } | null;
};
export type Passage = {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page: number;
  section: string;
  text: string;
  content_hash: string;
  source: string;
  reporting_period: string | null;
  keyword_score: number;
  semantic_score: number | null;
  score: number;
  rank: number;
  table_structure: string;
};
export type SearchResult = {
  passages: Passage[];
  method: string;
  warnings: string[];
  index_version: string;
  embedding_usage: Record<string, unknown> | null;
};
export type EvaluationRun = {
  id: string;
  status: string;
  created_at: string;
  payload: {
    completed_cases: number;
    total_cases: number;
    acceptance_passed?: boolean;
    mode: string;
    error?: string;
    metrics?: Record<
      string,
      { passed: number; total: number; rate: number | null }
    >;
    efficiency?: {
      elapsed_seconds: number;
      median_case_seconds: number;
      max_case_seconds: number;
      tool_calls: number;
      input_tokens: number | null;
      output_tokens: number | null;
      estimated_cost_usd: number | null;
    };
    limitations?: string[];
    failures?: { id: string; category: string; failure: string }[];
    cases?: {
      id: string;
      category: string;
      question: string;
      expected_tools: string[];
      checks: Record<string, boolean>;
      passed: boolean;
      failure: string | null;
      elapsed_seconds: number;
      actual: Record<string, unknown>;
    }[];
    runtime?: Record<string, unknown>;
    dataset_sha256?: string;
  };
};
