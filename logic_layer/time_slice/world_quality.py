"""Scoped world-quality helpers for the data-end handoff contract.

WMI must be computed relative to the *declared* consumer archive bands in the
world bundle. Scoring permanently empty schema slots that are outside that
contract artificially caps WMI and prevents the production valve from ever
opening—even when every delivered band is ready.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from logic_layer.asset_readiness.service import AssetReadinessService


def resolve_active_bands(
    *,
    scope: str | None = None,
    declared_bands: Sequence[str] | None = None,
) -> list[str]:
    """Return the band set used for breadth/stability.

    ``eval_archive`` / ``declared`` → EVAL_ARCHIVE_BANDS (or explicit declared).
    ``full`` → all BAND_WEIGHTS keys.
    """
    from config.settings import EVAL_ARCHIVE_BANDS, WORLD_MODEL_BAND_SCOPE

    mode = (scope or WORLD_MODEL_BAND_SCOPE or "eval_archive").strip().lower()
    if mode in {"eval_archive", "declared", "archive", "consumer"}:
        bands = list(declared_bands) if declared_bands else list(EVAL_ARCHIVE_BANDS)
    else:
        bands = list(AssetReadinessService.BAND_WEIGHTS.keys())
    # Preserve stable order from BAND_WEIGHTS when possible.
    order = list(AssetReadinessService.BAND_WEIGHTS.keys())
    bands = [b for b in order if b in bands] + [b for b in bands if b not in order]
    return bands


def status_ratio(status: str) -> float:
    return float(AssetReadinessService._status_ratio(status))


def continuous_honesty(excl: float, cont: float) -> float:
    """Same continuous honesty used in the PIT paper panel."""
    import math

    return float(math.exp(-2.0 * cont) * max(0.0, 1.0 - 0.5 * (1.0 - excl)))


def scoped_band_components(
    statuses: Mapping[str, str],
    *,
    active_bands: Sequence[str],
    weights: tuple[float, float, float] = (0.25, 0.35, 0.40),
) -> dict[str, Any]:
    """Compute B/U/H/WMI inputs on ``active_bands`` only (renormalized weights).

    Breadth is the weight-renormalized readiness of the *declared* bands
    (``B_asset``). Hierarchical mixing with domain means is retained as
    ``B_hier`` for audit, but the consumer-archive valve scores ``B_asset``
    so a missing required band (esp. exchange) cannot be washed out by
    always-ready macro/alternative slots.
    """
    bands = [b for b in active_bands if b]
    if not bands:
        bands = list(AssetReadinessService.BAND_WEIGHTS.keys())

    raw_w = {b: float(AssetReadinessService.BAND_WEIGHTS.get(b, 0.0)) for b in bands}
    wsum = float(sum(raw_w.values())) or float(len(bands))
    norm_w = {b: (raw_w[b] / wsum if wsum > 0 else 1.0 / len(bands)) for b in bands}

    ratios = {b: status_ratio(str(statuses.get(b, "missing"))) for b in bands}
    B_asset = float(sum(norm_w[b] * ratios[b] for b in bands))
    B_domain = float(sum(ratios.values()) / len(bands))
    B_band = B_domain
    B_hier = (
        weights[0] * B_domain + weights[1] * B_band + weights[2] * B_asset
    )

    ready_n = sum(
        1
        for b in bands
        if str(statuses.get(b, "missing")) in AssetReadinessService.READY_STATUSES
    )
    limited_n = sum(
        1
        for b in bands
        if str(statuses.get(b, "missing")) in AssetReadinessService.LIMITED_STATUSES
    )
    total = max(len(bands), 1)
    U = (ready_n + 0.7 * limited_n) / total
    excl = ready_n / total
    cont = limited_n / total * 0.5
    H = continuous_honesty(excl, cont)
    # Contract completeness: every declared band must be ready for "ok".
    archive_complete = ready_n == total
    if archive_complete and cont < 0.15:
        flag = "ok"
    elif B_asset >= 0.35:
        flag = "thin"
    else:
        flag = "blocked"
    return {
        "active_bands": list(bands),
        "B_asset": float(B_asset),
        "B_hier": float(B_hier),
        "U": float(U),
        "H": float(H),
        "n_ready": int(ready_n),
        "n_limited": int(limited_n),
        "n_missing": int(total - ready_n - limited_n),
        "total_bands": int(total),
        "archive_complete": bool(archive_complete),
        "data_quality_flag": flag,
        "band_weights_norm": norm_w,
    }


def scoped_wmi_from_statuses(
    statuses: Mapping[str, str],
    *,
    scope: str | None = None,
    declared_bands: Sequence[str] | None = None,
    abstain_threshold: float | None = None,
) -> dict[str, Any]:
    """End-to-end scoped WMI + valve for a status map.

    Valve contract for ``eval_archive`` / declared scopes:
    - score WMI = B_asset × U × H on declared bands only;
    - abstain unless the archive is complete (all declared bands ready)
      *and* WMI ≥ threshold.
    Full-schema scope keeps the legacy soft product without the
    completeness conjunction (empty non-archive bands still drag B/U).
    """
    from config.settings import WMI_ABSTAIN_THRESHOLD, WORLD_MODEL_BAND_SCOPE

    bands = resolve_active_bands(scope=scope, declared_bands=declared_bands)
    comp = scoped_band_components(statuses, active_bands=bands)
    thr = float(
        WMI_ABSTAIN_THRESHOLD if abstain_threshold is None else abstain_threshold
    )
    mode = (scope or WORLD_MODEL_BAND_SCOPE or "eval_archive").strip().lower()
    # Use declared-band breadth; honesty from continuous PIT formula.
    wmi = round(float(comp["B_asset"]) * float(comp["U"]) * float(comp["H"]), 4)
    if mode in {"eval_archive", "declared", "archive", "consumer"}:
        should_abstain = (not comp["archive_complete"]) or (wmi < thr)
    else:
        should_abstain = wmi < thr
    return {
        **comp,
        "wmi": float(wmi),
        "breadth": float(comp["B_asset"]),
        "stability": float(comp["U"]),
        "honesty": float(comp["H"]),
        "should_ai_abstain": bool(should_abstain),
        "abstain_threshold": thr,
        "band_scope": mode,
        "thin_world": bool(should_abstain),
        "interpretation": (
            "sufficient"
            if (not should_abstain and wmi >= 0.6)
            else "marginal"
            if (not should_abstain)
            else "insufficient"
        ),
    }


def statuses_from_panel_row(row: Mapping[str, Any], bands: Iterable[str]) -> dict[str, str]:
    return {b: str(row.get(f"st_{b}", "missing")) for b in bands}
