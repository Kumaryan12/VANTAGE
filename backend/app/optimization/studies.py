from pydantic import ValidationError

from app.core.errors import AppError

from .contracts import FrontierRequest, OptimizationRequest, SensitivityRequest


def request_for(kind, payload):
    return {
        "single": OptimizationRequest,
        "frontier": FrontierRequest,
        "sensitivity": SensitivityRequest,
    }[kind].model_validate(payload)


def point_plan(kind, request):
    if kind == "single":
        return [("Base allocation", request, {})]
    base = request.base
    if kind == "frontier":
        if request.mode == "risk_turnover":
            return [
                (
                    f"Turnover budget {budget:.1%}",
                    OptimizationRequest.model_validate(
                        {
                            **base.model_dump(),
                            "constraints": {
                                **base.constraints.model_dump(),
                                "max_turnover": budget,
                            },
                        }
                    ),
                    {"max_turnover": budget},
                )
                for budget in sorted(request.turnover_budgets)
            ]
        return [
            (
                f"Assumed return target {target:.2%}",
                OptimizationRequest.model_validate(
                    {
                        **base.model_dump(),
                        "objective": "target_return",
                        "target_annual_return": target,
                    }
                ),
                {"target_annual_return": target, "objective": "target_return"},
            )
            for target in sorted(request.return_targets)
        ]
    result = [("Base allocation", base, {})]
    for variation in request.variations:
        settings = base.model_dump(mode="json")
        changes = {}
        if variation.kind == "window":
            if not isinstance(variation.value, int) or isinstance(variation.value, bool):
                raise AppError(
                    "SENSITIVITY_VALUE", "Window sensitivity requires an integer observation count."
                )
            settings["window"] = variation.value
            changes["window"] = variation.value
        elif variation.kind == "shrinkage":
            settings["shrinkage"] = variation.value
            changes["shrinkage"] = variation.value
        elif variation.kind in ("max_weight", "turnover"):
            key = "max_weight" if variation.kind == "max_weight" else "max_turnover"
            settings["constraints"][key] = variation.value
            changes[key] = variation.value
        elif variation.kind == "sector_max":
            if not variation.sector:
                raise AppError(
                    "SENSITIVITY_SECTOR",
                    "Sector sensitivity needs an existing explicit sector name.",
                )
            settings["constraints"]["sector_max"][variation.sector] = variation.value
            changes[f"sector_max.{variation.sector}"] = variation.value
        else:
            settings.update(objective="risk_cost", lambda_cost=variation.value)
            changes = {"objective": "risk_cost", "lambda_cost": variation.value}
        try:
            parameters = OptimizationRequest.model_validate(settings)
        except ValidationError as error:
            raise AppError(
                "SENSITIVITY_VALUE",
                "A variation is outside the validated parameter bounds.",
                details=error.errors(include_input=False, include_context=False),
            ) from None
        result.append(
            (f"{variation.kind}: {variation.sector or ''} {variation.value}", parameters, changes)
        )
    return result
