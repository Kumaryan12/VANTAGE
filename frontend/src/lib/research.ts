export type ModelKind = "rolling" | "ewma" | "garch" | "lightgbm";
export const modelNames: Record<ModelKind, string> = {
  rolling: "Rolling historical",
  ewma: "EWMA",
  garch: "GARCH(1,1)",
  lightgbm: "LightGBM",
};
export const modelColors: Record<ModelKind, string> = {
  rolling: "#779cf5",
  ewma: "#e3b773",
  garch: "#b297df",
  lightgbm: "#64d9b4",
};
export type Coverage = {
  confidence: number;
  observations: number;
  exceptions: number;
  exception_rate: number | null;
  nominal_rate: number;
  expected_exceptions: number;
  kupiec_statistic: number | null;
  kupiec_p_value: number | null;
  independence_statistic: number | null;
  independence_p_value: number | null;
  conditional_statistic: number | null;
  conditional_p_value: number | null;
  exact_binomial_p_value: number | null;
  transitions: Record<string, number>;
  warnings: string[];
};
export type Metrics = {
  observations: number;
  qlike: number | null;
  mse: number | null;
  mae: number | null;
  coverage95: Coverage;
  coverage99: Coverage;
};
export type Job = {
  id: string;
  status:
    "queued" | "running" | "completed" | "partial" | "failed" | "interrupted";
  progress: number;
  stage: string;
  created_at: string;
  finished_at: string | null;
  error: { code: string; message: string } | null;
  dataset_hash: string;
  synthetic: boolean;
  reproduction_of: string | null;
};
export type ResearchParameters = {
  mode: "demo" | "kite";
  dataset_id?: string;
  context_dataset_id?: string;
  benchmark_instrument?: string;
  scheme: "expanding" | "rolling";
  history_window: number;
  initial_train: number;
  validation_size: number;
  test_size: number;
  refit_every: number;
  rolling_train_window: number;
  rolling_window: 20 | 60;
  ewma_lambda: number;
  seed: number;
  max_trees: number;
  search_candidates: number;
  feature_set: "basic" | "full";
};
export type ComparisonRow = {
  id: string;
  kind: ModelKind;
  role: "benchmark" | "candidate" | "champion";
  status: string;
  available_predictions: number;
  failures: number;
  metrics: Metrics;
  execution_seconds: number;
  limitations: string[];
};
export type ResearchComparison = {
  experiment_id: string;
  start: string | null;
  end: string | null;
  requested_observations: number;
  matched_observations: number;
  excluded_dates: string[];
  models: ComparisonRow[];
  policy: string;
  uncertainty: {
    benchmark: string;
    available: boolean;
    mean_qlike_difference?: number;
    interval95?: number[];
    note?: string;
    reason?: string;
  }[];
  warnings: string[];
};
export type Experiment = Job & {
  parameters: ResearchParameters;
  model_version: string;
  feature_version: string;
  dataset: {
    snapshot_value: number;
    snapshot_as_of: string;
    series_id: string;
    source: string;
    data_version: string;
    synthetic: boolean;
    price_start: string;
    return_start: string;
    end: string;
    price_observations: number;
    return_observations: number;
    features: string[];
    portfolio_construction: string;
    availability_assumption: string;
    universe_limitation: string;
    unavailable_features: string[];
    sector_context?: string;
  };
  protocol: {
    target: string;
    horizon: string;
    mean_model: string;
    variance_units: string;
    train_start: string;
    development_train_end: string;
    validation_start: string;
    validation_end: string;
    test_start: string;
    test_end: string;
    selection_policy: string;
    online_update_policy: string;
    purging: string;
  };
  runtime: Record<string, string | null>;
  comparison: ResearchComparison | null;
  reproduction_match: boolean | null;
  warnings: string[];
};
export type TrainingRefit = {
  id: string;
  forecast_origin: string;
  training_start: string;
  training_end: string;
  training_return_observations: number;
  max_label_available_at: string;
  last_training_feature_origin?: string;
  failure?: string;
  parameters?: Record<string, number>;
  warnings?: string[];
};
export type ForecastModel = {
  id: string;
  experiment_id: string;
  kind: ModelKind;
  role: "benchmark" | "candidate" | "champion";
  status: string;
  config: Record<string, unknown>;
  metrics: Metrics | null;
  latest_forecast: {
    origin: string;
    target_date: null;
    horizon: string;
    forecast_variance: number | null;
    forecast_volatility: number | null;
    var95: number | null;
    var99: number | null;
    failure: string | null;
  } | null;
  refits: TrainingRefit[];
  global_importance: {
    feature: string;
    gain: number;
    split_count: number;
    gain_share: number;
  }[];
  drift: {
    feature: string;
    standardized_mean_difference: number | null;
    outside_training_5_95_fraction: number;
    note: string;
  }[];
  execution_seconds: number;
  limitations: string[];
  artifact_files: { path: string; sha256: string; bytes: number }[];
  governance: {
    from: string;
    to: string;
    rationale: string;
    created_at: string;
  }[];
};
export type ResearchPoint = {
  date: string;
  origin: string;
  realized_volatility_proxy: number;
  realized_loss: number;
  regime: string;
  rolling: number | null;
  ewma: number | null;
  garch: number | null;
  lightgbm: number | null;
  [key: string]: string | number | boolean | null;
};
export type Regimes = {
  thresholds: { low_upper: number; high_lower: number };
  estimated_through: string;
  rows: {
    origin: string;
    target: string;
    lagged_variance: number;
    regime: string;
  }[];
  metrics: { regime: string; model_kind: ModelKind; metrics: Metrics }[];
  note: string;
};
export type Explanation = {
  model_id: string;
  origin: string;
  target: string;
  training_window_id: string;
  base_variance: number;
  raw_variance: number;
  forecast_variance: number;
  floor_adjustment: number;
  reconstruction_residual: number;
  features: {
    feature: string;
    observed_value: number | null;
    model_input: number;
    variance_contribution: number;
  }[];
  sensitivity: {
    feature: string;
    training_std: number;
    lower_variance: number;
    upper_variance: number;
  }[];
  note: string;
};
export type ExperimentComparison = {
  experiments: Experiment[];
  warnings: string[];
};
export const metric = (value: number | null | undefined, digits = 5) =>
  value == null ? "Unavailable" : value.toFixed(digits);
export const scientific = (value: number | null | undefined) =>
  value == null ? "Unavailable" : value.toExponential(3);
