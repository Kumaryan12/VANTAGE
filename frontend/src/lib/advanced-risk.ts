import type { Portfolio, Provenance } from "./api";

export type RiskSelection = {
  mode: "demo" | "kite";
  dataset_id?: string;
  confidence: number;
  window: number;
};
export type AnalysisParameters = RiskSelection & {
  shrinkage: number;
  simulations: number;
  seed: number;
};
export type TailEstimate = {
  method: string;
  var: number;
  expected_shortfall: number;
  var_return: number;
  es_return: number;
  tail_sample_mass: number | null;
  assumptions: string[];
};
export type RunMetadata = {
  methodology: string;
  model_version: string;
  created_at: string;
  valuation_as_of: string;
  snapshot_retrieved_at: string;
  snapshot_id: string;
  input_artifact_id: string;
  input_hash: string;
  artifact_hash: string;
  historical_data_hash: string | null;
  horizon: string;
  confidence: number;
  requested_window: number;
  sample_size: number;
  estimation_start: string | null;
  estimation_end: string | null;
  covariance_method: string | null;
  shrinkage: number;
  random_seed: number | null;
  simulation_count: number;
  runtime: Record<string, string>;
  validation: Record<string, string | number | boolean | null>;
  warnings: string[];
};
export type Analysis = {
  kind: "analysis";
  run_id: string;
  portfolio: Portfolio;
  parameters: AnalysisParameters;
  metadata: RunMetadata;
  provenance: Provenance;
  expected_daily_return: number;
  daily_volatility: number;
  annualized_volatility: number;
  sample_annualized_volatility: number;
  models: {
    historical: TailEstimate;
    gaussian: TailEstimate;
    monte_carlo: TailEstimate;
  };
  covariance: number[][];
  correlation: (number | null)[][];
  covariance_diagnostics: {
    method: string;
    shrinkage: number;
    rank: number;
    condition_number: number | null;
    singular: boolean;
    ill_conditioned: boolean;
    negative_eigenvalues_clipped: number;
    correction_frobenius_norm: number;
    shrinkage_change_frobenius_norm: number;
  };
  attribution: {
    daily_volatility: number;
    annualized_volatility: number;
    assets: {
      instrument: string;
      name: string;
      sector: string;
      weight: number;
      marginal_daily_volatility: number | null;
      component_daily_volatility: number;
      component_annualized_volatility: number;
      percentage_contribution: number | null;
    }[];
    sectors: {
      sector: string;
      weight: number;
      component_daily_volatility: number;
      component_annualized_volatility: number;
      percentage_contribution: number | null;
    }[];
    weight_hhi: number;
    positive_component_hhi: number | null;
    reconciliation_residual: number;
    note: string;
  };
  simulation: {
    simulations: number;
    seed: number;
    sampling_method: string;
    bit_generator: string;
    mean_pnl: number;
    pnl_standard_deviation: number;
    var_standard_error: number;
    es_standard_error: number;
    var_mc_interval_95: number[];
    es_mc_interval_95: number[];
    value_quantiles: Record<string, number>;
    return_quantiles: Record<string, number>;
    pnl_quantiles: Record<string, number>;
    histogram: {
      left_pnl: number;
      right_pnl: number;
      center_pnl: number;
      count: number;
      tail_count: number;
    }[];
    nonpositive_value_count: number;
    asset_returns_below_minus_one: number;
    uncertainty_note: string;
    assumptions: string[];
  };
};
export type StressParameters = RiskSelection & {
  kind: "hypothetical" | "historical";
  name: string;
  scenario_id?: string;
  scenario_dataset_id?: string;
  start?: string;
  end?: string;
  market_shock?: number;
  sector_shocks?: Record<string, number>;
  security_shocks?: Record<string, number>;
};
export type Stress = {
  kind: "stress";
  scenario_kind: "hypothetical" | "historical" | "synthetic_replay";
  run_id: string;
  name: string;
  portfolio: Portfolio;
  parameters: StressParameters;
  metadata: RunMetadata;
  provenance: Provenance | null;
  value_before: number;
  value_after: number;
  portfolio_return: number;
  pnl: number;
  loss: number;
  assets: {
    instrument: string;
    name: string;
    sector: string;
    weight: number;
    shock_return: number;
    pnl: number;
    loss: number;
    value_before: number;
    value_after: number;
    mapping: string;
  }[];
  sectors: {
    sector: string;
    pnl: number;
    loss: number;
    value_before: number;
    value_after: number;
  }[];
  largest_loss_contributors: string[];
  pnl_reconciliation_residual: number;
  path: {
    date: string;
    value: number;
    pnl: number;
    cumulative_return: number;
  }[];
  observations: number;
  assumptions: string[];
  reference_risk: {
    historical_var: number;
    historical_es: number;
    stress_loss_to_var: number | null;
    note: string;
  } | null;
};
export type Scenario = {
  id: string;
  name: string;
  start: string;
  end: string;
  synthetic: boolean;
  available: boolean;
  reason: string;
};
export type RunSummary = {
  id: string;
  kind: "analysis" | "stress" | "legacy";
  mode: string;
  name: string;
  created_at: string;
  confidence: number;
  window: number;
  sample_size: number;
  portfolio_value: number | null;
  historical_var: number | null;
  historical_es: number | null;
  stress_pnl: number | null;
  replayable: boolean;
};
export type SavedRun = {
  id: string;
  input_hash: string;
  replayable: boolean;
  result: Analysis | Stress;
};
export type RunComparison = {
  baseline_id: string;
  rows: (RunSummary & {
    var_delta: number | null;
    gaussian_var_delta: number | null;
    gaussian_es_delta: number | null;
    monte_carlo_var_delta: number | null;
    monte_carlo_es_delta: number | null;
    es_delta: number | null;
    pnl_delta: number | null;
  })[];
  warnings: string[];
};
export type Replay = {
  original_run_id: string;
  replayed_run_id: string;
  input_hash_matches: boolean;
  numerical_results_match: boolean;
  result: Analysis | Stress;
  note: string;
};
