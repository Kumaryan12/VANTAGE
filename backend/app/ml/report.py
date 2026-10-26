"""Deterministic report rendering from executed, owned experiment records."""


def render_report(detail, models, regimes):
    comparison = detail.comparison
    data = detail.dataset
    protocol = detail.protocol
    lines = [
        "# VANTAGE — volatility model comparison",
        "",
        f"Experiment `{detail.id}` · status **{detail.status}** · model `{detail.model_version}`",
        "",
        "## Research question",
        "Can ML conditional variance forecasts improve out-of-sample portfolio risk calibration over rolling, EWMA and GARCH?",
        "",
        "## Motivation",
        "Conditional risk forecasts should earn their complexity against simple benchmarks through matched out-of-sample losses and tail calibration, including cases where ML performs worse.",
        "",
        "## Data and portfolio construction",
        f"Source: {data['source']}. **{'SYNTHETIC — software/protocol experiment, not real-market evidence' if detail.synthetic else 'User-provided permitted historical data'}**.",
        f"Price coverage {data['price_start']}–{data['end']}; {data['return_observations']} daily portfolio returns; dataset SHA-256 `{detail.dataset_hash}`.",
        data["portfolio_construction"],
        f"Fixed saved snapshot notional: INR {data['snapshot_value']:,.2f}; valuation as of {data['snapshot_as_of']}.",
        data["universe_limitation"],
        data["availability_assumption"],
        "",
        "## Target and features",
        protocol["target"]
        + ". A single squared return is a noisy ex-post variance proxy, not observed latent volatility.",
        "Features available after origin close: " + ", ".join(data["features"]) + ".",
        *data["unavailable_features"],
        "",
        "## Protocol",
        f"Development training {protocol['train_start']}–{protocol['development_train_end']}; validation {protocol['validation_start']}–{protocol['validation_end']}; final evaluation {protocol['test_start']}–{protocol['test_end']}.",
        f"Scheme {detail.parameters.scheme}; refit every {detail.parameters.refit_every} origins; seed {detail.parameters.seed}.",
        protocol["selection_policy"],
        protocol["online_update_policy"],
        "This is a retrospective development demonstration. The final period is excluded from fitting/tuning at each origin; repeated engineering inspection of this synthetic dataset is not a prospective untouched market study.",
        "",
        "## Model specifications",
        "Rolling: zero-mean rolling second moment. EWMA: fixed-decay second moment with historical initialization. GARCH: ARCH Gaussian zero-mean GARCH(1,1), percent-return scaling. LightGBM: L2 regression on scaled squared returns, training-only imputation, pre-test early stopping and bounded search; no exponentiated log-target bias.",
        "",
        "## Out-of-sample results",
    ]
    if comparison is None:
        lines += ["Unavailable: the experiment has no completed evaluation."]
    else:
        lines += [
            f"Requested targets: {comparison.requested_observations}; common valid targets: {comparison.matched_observations}. Excluded dates: {', '.join(str(d) for d in comparison.excluded_dates) or 'none'}.",
            "",
            "| Model | N | QLIKE | MSE (variance) | MAE (variance) | 95% exceptions | 99% exceptions | Seconds |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]

        def number(v):
            return "unavailable" if v is None else f"{v:.9g}"

        for row in comparison.models:
            m = row.metrics
            lines.append(
                f"| {row.kind} | {m.observations} | {number(m.qlike)} | {number(m.mse)} | {number(m.mae)} | {m.coverage95.exceptions}/{m.coverage95.observations} | {m.coverage99.exceptions}/{m.coverage99.observations} | {row.execution_seconds:.4f} |"
            )
        lines += [
            "",
            "## Conditional VaR backtesting",
            "Gaussian zero-mean one-day loss quantiles use the existing Phase 2 engine with predicted **portfolio** variance and fixed snapshot notional. Exceptions require realized loss strictly greater than VaR.",
            "",
            "| Model / confidence | Kupiec LR | Kupiec p | Independence p | Conditional coverage p | Expected violations |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in comparison.models:
            for confidence in (row.metrics.coverage95, row.metrics.coverage99):
                lines.append(
                    f"| {row.kind} / {confidence.confidence:.0%} | {number(confidence.kupiec_statistic)} | {number(confidence.kupiec_p_value)} | {number(confidence.independence_p_value)} | {number(confidence.conditional_p_value)} | {confidence.expected_exceptions:.3g} |"
                )
        lines += [
            "",
            "No high-regime conclusions are possible when its observation count is zero. Sparse expected violations/transition counts limit asymptotic p-values. Missing states make independence/conditional coverage unavailable; non-rejection does not prove a correct model.",
            "",
            "## Regimes",
            regimes["note"],
            f"Pre-validation thresholds: {regimes['thresholds']}; estimated through {regimes['estimated_through']}.",
            "",
            "| Regime | Model | N | QLIKE | 95% exceptions | 99% exceptions |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for row in regimes["metrics"]:
            m = row["metrics"]
            lines.append(
                f"| {row['regime']} | {row['model_kind']} | {m['observations']} | {number(m['qlike'])} | {m['coverage95']['exceptions']} | {m['coverage99']['exceptions']} |"
            )
        lines += ["", "## Challenger comparison and uncertainty", comparison.policy]
        for row in comparison.uncertainty:
            lines.append(
                f"LightGBM minus {row['benchmark']} QLIKE: "
                + (
                    f"{row['mean_qlike_difference']:.9g}, descriptive 95% moving-block bootstrap interval {row['interval95']}."
                    if row.get("available")
                    else row.get("reason", "unavailable")
                )
            )
        valid = [row for row in comparison.models if row.metrics.qlike is not None]
        if valid:
            best = min(valid, key=lambda row: row.metrics.qlike)
            lines += [
                "",
                f"Lowest observed average QLIKE in this matched experiment: **{best.kind}**. This is not an automatic champion decision or proof of predictive superiority.",
            ]
        for model in models:
            if model.kind == "lightgbm":
                lines += [
                    "",
                    "## LightGBM selection and explanations",
                    "Validation search and selected configuration:",
                    "```json",
                    __import__("json").dumps(model.config, indent=2),
                    "```",
                    "Final-refit gain importance and saved-prediction TreeSHAP explanations are available through the private model API/dashboard. They explain fitted predictions, not causal market drivers. Drift references the first test refit's training distribution and never retunes the model.",
                ]
    lines += [
        "",
        "## Limitations and conclusions",
        *detail.warnings,
        "Synthetic data cannot answer whether ML improves real-market risk. These results demonstrate an executed, controlled research process; real-market conclusions require permitted point-in-time data, larger independent evaluation periods and repeated regime-stability assessment.",
        "Gaussian innovations, noisy squared-return targets, current-universe survivorship bias, availability/calendar assertions, finite samples and repeated research selection remain material risks. No live trading or investment recommendation is implemented.",
        "",
        "## Reproducibility",
        "Complete request parameters:",
        "```json",
        __import__("json").dumps(detail.parameters.model_dump(mode="json"), indent=2),
        "```",
        f"Input data `{detail.dataset_hash}`; feature version `{detail.feature_version}`; runtime:",
        "```json",
        __import__("json").dumps(detail.runtime, indent=2),
        "```",
        "Run `backend/.venv/bin/python backend/scripts/research_report.py` after installing locked dependencies and applying migration 0003. The script runs the default synthetic protocol and writes this report from actual saved results. Model text/JSON artifacts and checksum manifests live outside database rows in the private configured artifact directory.",
        "Owner-authorized experiment reproduction uses immutable saved inputs, fixed seeds and locked configurations; output tolerances are rtol=1e-8 and atol=1e-14 for decimal variance, with failures/nulls preserved. Exact booster reload predictions are tested separately. Execution timings and platform-specific optimizer details are not deterministic scientific metrics.",
    ]
    return "\n".join(lines) + "\n"
