"""
Probability ensemble utilities for HALAL SCAN AI.

The live app can still load the original XGBoost artifact because it only
requires a predict_proba method. New training runs save this wrapper with both
XGBoost and LightGBM estimators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class ProbabilityEnsemble:
    estimators: dict[str, Any]
    weights: dict[str, float] = field(default_factory=dict)
    feature_names: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def predict_proba(self, X):
        probas = []
        weights = []

        for name, estimator in self.estimators.items():
            if estimator is None or not hasattr(estimator, "predict_proba"):
                continue
            probas.append(estimator.predict_proba(X))
            weights.append(float(self.weights.get(name, 1.0)))

        if not probas:
            raise ValueError("ProbabilityEnsemble has no usable estimators.")

        weights_arr = np.array(weights, dtype=float)
        if weights_arr.sum() <= 0:
            weights_arr = np.ones_like(weights_arr)

        stacked = np.stack(probas, axis=0)
        return np.average(stacked, axis=0, weights=weights_arr)

    @property
    def classes_(self):
        for estimator in self.estimators.values():
            classes = getattr(estimator, "classes_", None)
            if classes is not None:
                return classes
        return np.array([0, 1])

    @property
    def n_features_in_(self):
        if self.feature_names:
            return len(self.feature_names)
        for estimator in self.estimators.values():
            n_features = getattr(estimator, "n_features_in_", None)
            if n_features is not None:
                return n_features
        return None
