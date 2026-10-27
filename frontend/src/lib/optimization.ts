export type OptimizationJob = {
  id: string;
  kind: string;
  status: string;
  stage: string;
  progress: number;
  synthetic: boolean;
  solver_status: string | null;
  error: { code: string; message: string } | null;
  created_at: string;
  reproduction_of: string | null;
};
export type OptimizationResidual = {
  name: string;
  group: string;
  value: number;
  lower: number | null;
  upper: number | null;
  violation: number;
  binding: boolean;
  utilization: number | null;
  units: string;
};
export type OptimizationSolution = {
  status: string;
  feasible: boolean;
  weights: number[] | null;
  annual_variance: number | null;
  annual_volatility: number | null;
  objective_value: number | null;
  turnover: number | null;
  gross_weight_change: number | null;
  one_way_notional: number | null;
  gross_notional_traded: number | null;
  cost_fraction: number | null;
  cost_inr: number | null;
  expected_annual_return: number | null;
  residuals: OptimizationResidual[];
  diagnostics: string[];
  solver: Record<string, string | number | null>;
  validation: Record<string, unknown>;
};
export type SleeveRisk = {
  notional: number;
  annual_volatility: number;
  annual_variance: number;
  historical_var: number;
  historical_es: number;
  gaussian_var: number;
  gaussian_es: number;
  monte_carlo_var: number;
  monte_carlo_es: number;
  position_hhi: number;
  sector_hhi: number;
  sector_weights: Record<string, number>;
  confidence: number;
  observations: number;
  attribution: {
    assets: {
      instrument: string;
      name: string;
      sector: string;
      component_annualized_volatility: number;
      percentage_contribution: number | null;
    }[];
    sectors: {
      sector: string;
      weight: number;
      percentage_contribution: number | null;
      component_annualized_volatility: number;
    }[];
    reconciliation_residual: number;
    note: string;
  };
};
export type OptimizationPoint = {
  label: string;
  changes: Record<string, unknown>;
  parameters: Record<string, unknown>;
  dataset: OptimizationDataset;
  covariance: number[][];
  allocation_stability?: {
    one_way_distance_from_base: number | null;
    interpretation: string;
  };
  solution: OptimizationSolution;
  current_metrics: SleeveRisk;
  comparison: {
    current: SleeveRisk;
    proposed: SleeveRisk;
    delta: Record<string, number>;
    relative_delta: Record<string, number | null>;
    volatility_reduction_fraction: number | null;
    policy: string;
    warnings: string[];
  } | null;
  allocations: {
    instrument: string;
    name: string;
    sector: string;
    current_weight: number;
    proposed_weight: number;
    change: number;
    approximate_notional_change: number;
    frozen: boolean;
  }[];
};
export type OptimizationDataset = {
  synthetic: boolean;
  sleeve: string;
  account_cash: string;
  excluded: string;
  as_of: string;
  sleeve_notional: number;
  instruments: string[];
  sectors: string[];
  current_weights: number[];
  estimation_start: string;
  estimation_end: string;
  observations: number;
  available_returns: number;
  covariance_hash: string;
  price_value_hash: string;
  covariance_diagnostics: {
    method: string;
    shrinkage: number;
    singular: boolean;
    condition_number: number | null;
    [key: string]: unknown;
  };
  source: {
    source: string;
    synthetic: boolean;
    adjustment: string;
    content_hash: string;
  };
};
export type OptimizationDetail = OptimizationJob & {
  version: string;
  snapshot_id: string;
  artifact_id: string;
  input_hash: string;
  parameters: Record<string, unknown>;
  dataset: OptimizationDataset;
  runtime: Record<string, string | null>;
  result: {
    kind: string;
    frontier_mode: string | null;
    plot: {
      point_index: number;
      label: string;
      x: number | null;
      annual_volatility: number | null;
      status: string;
      feasible: boolean;
    }[];
    points: OptimizationPoint[];
    warnings: string[];
    reproduction_match: boolean | null;
    reproduction_tolerances: Record<string, unknown>;
  } | null;
};
