"""Explicit sample/linear-shrinkage covariance policy and PSD diagnostics."""

import numpy as np

from app.core.errors import AppError


def validated_covariance(covariance) -> tuple[np.ndarray, dict]:
    matrix = np.asarray(covariance, dtype=float)
    if (
        matrix.ndim != 2
        or matrix.shape[0] != matrix.shape[1]
        or not matrix.shape[0]
        or not np.isfinite(matrix).all()
    ):
        raise AppError("INVALID_COVARIANCE", "Covariance must be a nonempty finite square matrix.")
    scale = max(float(np.max(np.abs(matrix))), np.finfo(float).tiny)
    tolerance = 1e-10 * scale
    asymmetry = float(np.max(np.abs(matrix - matrix.T)))
    if asymmetry > tolerance:
        raise AppError(
            "ASYMMETRIC_COVARIANCE",
            "Covariance is not symmetric within the documented relative tolerance.",
        )
    symmetric = (matrix + matrix.T) / 2
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    if eigenvalues.min() < -tolerance:
        raise AppError(
            "INDEFINITE_COVARIANCE",
            "Covariance has a materially negative eigenvalue; no arbitrary replacement is permitted.",
        )
    corrected = eigenvalues < 0
    clipped = np.maximum(eigenvalues, 0)
    final = (eigenvectors * clipped) @ eigenvectors.T if corrected.any() else symmetric
    rank_tolerance = (
        max(float(clipped.max()), np.finfo(float).tiny) * len(matrix) * np.finfo(float).eps
    )
    rank = int(np.count_nonzero(clipped > rank_tolerance))
    condition = float(clipped.max() / clipped.min()) if clipped.min() > rank_tolerance else None
    return final, {
        "minimum_eigenvalue_before": float(eigenvalues.min()),
        "maximum_eigenvalue": float(clipped.max()),
        "rank": rank,
        "condition_number": condition,
        "singular": rank < len(matrix),
        "ill_conditioned": condition is None or condition > 1e8,
        "symmetry_error": asymmetry,
        "symmetrized": asymmetry > 0,
        "negative_eigenvalues_clipped": int(corrected.sum()),
        "psd_tolerance": tolerance,
        "correction_frobenius_norm": float(np.linalg.norm(final - matrix)),
    }


def estimate_covariance(returns, shrinkage: float = 0) -> tuple[np.ndarray, dict]:
    values = np.asarray(returns, dtype=float)
    if (
        values.ndim != 2
        or values.shape[0] < 2
        or not values.shape[1]
        or not np.isfinite(values).all()
    ):
        raise AppError(
            "INVALID_RETURNS",
            "Covariance requires a finite observations-by-assets matrix with at least two rows.",
        )
    if not np.isfinite(shrinkage) or not 0 <= shrinkage <= 1:
        raise AppError("INVALID_SHRINKAGE", "Shrinkage must be between zero and one.")
    centered = values - values.mean(axis=0)
    sample = centered.T @ centered / (len(values) - 1)
    target_variance = float(np.trace(sample) / sample.shape[0])
    matrix = (1 - shrinkage) * sample + shrinkage * target_variance * np.eye(sample.shape[0])
    final, diagnostics = validated_covariance(matrix)
    return final, {
        **diagnostics,
        "method": "sample" if shrinkage == 0 else "linear_shrinkage_identity",
        "ddof": 1,
        "shrinkage": float(shrinkage),
        "target_variance": target_variance,
        "shrinkage_change_frobenius_norm": float(np.linalg.norm(matrix - sample)),
    }


def spectral_root(covariance) -> np.ndarray:
    matrix, _ = validated_covariance(covariance)
    eigenvalues, vectors = np.linalg.eigh(matrix)
    # Validation above rejects material negatives; roundoff clipping is recorded upstream.
    return vectors * np.sqrt(np.maximum(eigenvalues, 0))


def correlation_matrix(covariance) -> list[list[float | None]]:
    matrix, _ = validated_covariance(covariance)
    deviations = np.sqrt(np.maximum(np.diag(matrix), 0))
    denominator = np.outer(deviations, deviations)
    return [
        [
            None
            if denominator[i, j] == 0
            else float(np.clip(matrix[i, j] / denominator[i, j], -1, 1))
            for j in range(len(matrix))
        ]
        for i in range(len(matrix))
    ]
