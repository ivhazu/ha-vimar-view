"""Filter cloud associations that cannot act as Vimar View gateways.

The list of unsupported models is deliberately narrow: unknown models remain
visible until their compatibility has been established.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

UNSUPPORTED_ASSOCIATION_MODELS = frozenset({"VPTW5"})


def supported_gateways(associations: Iterable[dict[str, Any]]) -> dict[str, dict]:
    """Return DUID-keyed associations excluding known unsupported device models."""
    gateways: dict[str, dict] = {}
    for association in associations:
        if not isinstance(association, dict):
            continue
        model = str(association.get("model") or "").strip().upper()
        if model in UNSUPPORTED_ASSOCIATION_MODELS:
            continue
        duid = str(association.get("duid") or "").strip().upper()
        if duid:
            gateways[duid] = association
    return gateways
