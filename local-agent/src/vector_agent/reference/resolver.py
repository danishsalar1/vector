"""Conservative catalog identity resolution; never proof of physical authenticity.

Every recognized claim constrains the match. Unknown claims block exactness;
catalog cardinality and ordering never substitute for a discriminating code.
"""

from __future__ import annotations

import re
from typing import Any

from vector_agent.models.device import DeviceIdentity, Platform
from vector_agent.models.reference import (
    CandidateMatch,
    DeviceModelReference,
    DeviceResolutionResult,
    DeviceVariantReference,
    ManufacturerReference,
    ResolutionStatus,
)

from .catalog import ReferenceCatalog

_IDENTITY_FIELDS = (
    "manufacturer",
    "brand",
    "model",
    "marketing_name",
    "hardware_model",
    "product_type",
    "device_codename",
)
_RAW_FIELDS = {field: field for field in _IDENTITY_FIELDS} | {
    "ro.product.manufacturer": "manufacturer",
    "ro.product.brand": "brand",
    "ro.product.model": "model",
    "ro.product.device": "device_codename",
    "ProductType": "product_type",
    "HardwareModel": "hardware_model",
}


def _normalize(text: str) -> str:
    return re.sub(r"[\s\-_]+", " ", text.strip().lower())


def _normalize_code(code: str) -> str:
    # Existing catalog code convention; no fuzzy/substring matching.
    return re.sub(r"[\s\-_]+", "", code.strip().lower())


def _product_token(value: str) -> str | None:
    # Preserve the component boundary: iPhone1,52 is not iPhone15,2.
    match = re.fullmatch(r"iphone([0-9]+)[,-]([0-9]+)", value.strip().lower())
    return f"iphone:{match[1]}:{match[2]}" if match else None


def _codename(value: str) -> str:
    return _product_token(value) or _normalize_code(value)


def _manufacturer_name(value: str) -> str:
    # The iOS producer emits Apple Inc.; the catalog alias is apple inc.
    return _normalize(value).removesuffix(".")


_APPLE_NAMES = frozenset({"apple", "apple inc"})


def _catalog_platform(manufacturer: ManufacturerReference | None) -> Platform | None:
    """Platform a catalogued manufacturer's phones run, or None if unknowable.

    iOS ships only on Apple hardware; every other catalogued phone maker here is
    Android. Used only to reject contradictory identity claims, never to infer one.
    """
    if manufacturer is None:
        return None
    names = {
        _manufacturer_name(n) for n in (manufacturer.manufacturer_id, manufacturer.canonical_name)
    }
    return Platform.IOS if names & _APPLE_NAMES else Platform.ANDROID


class DeviceResolver:
    """Resolve only identities supported by compatible catalog relationships."""

    def __init__(self, catalog: ReferenceCatalog) -> None:
        self.catalog = catalog

    def resolve(
        self,
        identity: DeviceIdentity | None = None,
        *,
        raw_properties: dict[str, Any] | None = None,
    ) -> DeviceResolutionResult:
        return DeviceResolver(self.catalog.snapshot())._resolve_snapshot(
            identity, raw_properties=raw_properties
        )

    def _resolve_snapshot(
        self,
        identity: DeviceIdentity | None = None,
        *,
        raw_properties: dict[str, Any] | None = None,
    ) -> DeviceResolutionResult:
        considered: dict[str, str | int | None] = {}
        claims: list[tuple[str, str, str]] = []
        unresolved: list[str] = []

        def add(label: str, kind: str, value: Any) -> None:
            if value is None or (isinstance(value, str) and not value.strip()):
                return
            if not isinstance(value, str):
                considered[label] = None
                unresolved.append(label)
                return
            considered[label] = value
            claims.append((label, kind, value))

        if identity is not None:
            if identity.platform != Platform.UNKNOWN:
                considered["platform"] = identity.platform.value
            for kind in _IDENTITY_FIELDS:
                add(kind, kind, getattr(identity, kind))
        # Do not overwrite DeviceIdentity or echo arbitrary/private raw properties.
        for key, kind in _RAW_FIELDS.items():
            if raw_properties and key in raw_properties:
                add(f"raw.{key}", kind, raw_properties[key])

        def result(status: ResolutionStatus, reason: str, **kwargs: Any) -> DeviceResolutionResult:
            return DeviceResolutionResult(
                status=status, reason=reason, considered_fields=considered, **kwargs
            )

        def conflict(labels: list[str]) -> DeviceResolutionResult:
            return result(
                ResolutionStatus.CONFLICTING_IDENTIFIERS,
                "Contradictory identifiers: catalog constraints from "
                + ", ".join(sorted(labels))
                + " have no common identity.",
                limitations=("No identifier was preferred over conflicting evidence.",),
            )

        models = self.catalog.all_models()
        variants = self.catalog.all_variants()
        model_constraints: list[tuple[str, set[str]]] = []
        maker_constraints: list[tuple[str, set[str]]] = []
        variant_constraints: list[tuple[str, set[str]]] = []
        unrepresented_codes: list[str] = []
        for label, kind, value in claims:
            if kind in {"manufacturer", "brand"}:
                matched_makers = {
                    m.manufacturer_id
                    for m in self.catalog.all_manufacturers()
                    if _manufacturer_name(value)
                    in {
                        _manufacturer_name(name)
                        for name in (m.manufacturer_id, m.canonical_name, *m.aliases)
                    }
                }
                if matched_makers:
                    maker_constraints.append((label, matched_makers))
                else:
                    unresolved.append(label)
                continue

            matches: set[str] = set()
            code_models: set[str] = set()
            code_variants: set[str] = set()
            if kind in {"model", "hardware_model"}:
                code = _normalize_code(value)
                code_models = {
                    m.model_id
                    for m in models
                    if code in {_normalize_code(c) for c in m.known_model_codes}
                }
                code_variants = {
                    v.variant_id
                    for v in variants
                    if code
                    in {
                        _normalize_code(c)
                        for c in (*v.model_codes, *(v.sku_numbers if kind == "model" else ()))
                    }
                }
                matches.update(code_models)
                matches.update(v.model_id for v in variants if v.variant_id in code_variants)
            if kind in {"model", "marketing_name"}:
                matches.update(
                    m.model_id for m in models if _normalize(value) == _normalize(m.marketed_name)
                )
            if kind in {"product_type", "device_codename"} or (
                kind == "model" and _product_token(value)
            ):
                matches.update(
                    m.model_id
                    for m in models
                    if _codename(value) in {_codename(c) for c in m.device_codenames}
                )
            if matches:
                model_constraints.append((label, matches))
            else:
                unresolved.append(label)
            if code_variants:
                variant_constraints.append((label, code_variants))
            elif code_models:
                # A recognized code with no variant mapping must not fall through
                # to a different code or a sole catalogued variant.
                unrepresented_codes.append(label)

        # Manufacturer and brand are independent constraints, not fallbacks.
        makers: set[str] | None = None
        for _, allowed in maker_constraints:
            makers = allowed.copy() if makers is None else makers & allowed
        if makers is not None and not makers:
            return conflict([label for label, _ in maker_constraints])

        candidates: set[str] | None = None
        for _, allowed in model_constraints:
            candidates = allowed.copy() if candidates is None else candidates & allowed
        labels = [label for label, _ in model_constraints]
        if candidates is not None and makers is not None:
            candidates &= {m.model_id for m in models if m.manufacturer_id in makers}
            labels += [label for label, _ in maker_constraints]
        if candidates is not None and not candidates:
            return conflict(labels)

        # A declared platform must agree with the catalogued maker's platform.
        if (
            candidates is not None
            and identity is not None
            and identity.platform != Platform.UNKNOWN
        ):
            agreeing = {
                m.model_id
                for m in models
                if m.model_id in candidates
                and _catalog_platform(self.catalog.get_manufacturer(m.manufacturer_id))
                in (None, identity.platform)
            }
            if not agreeing:
                return conflict([*labels, "platform"])
            candidates &= agreeing

        # Also reject conflicting regional codes within the same model.
        allowed_variants: set[str] | None = None
        for _, allowed in variant_constraints:
            allowed_variants = (
                allowed.copy() if allowed_variants is None else allowed_variants & allowed
            )
        if allowed_variants is not None and not allowed_variants:
            return conflict([label for label, _ in variant_constraints])

        unresolved = sorted(set(unresolved + unrepresented_codes))
        if not candidates:
            return result(
                ResolutionStatus.UNSUPPORTED_DEVICE
                if claims or unresolved
                else ResolutionStatus.UNKNOWN_DEVICE,
                "No catalog model established. Unresolved fields: " + ", ".join(unresolved)
                if unresolved
                else "No identifying model evidence available.",
            )
        unknown_makers = [
            label
            for label, kind, _ in claims
            if kind in {"manufacturer", "brand"} and label in unresolved
        ]
        if unknown_makers:
            return result(
                ResolutionStatus.UNSUPPORTED_DEVICE,
                "Unmapped manufacturer/brand claims prevent identity resolution: "
                + ", ".join(unknown_makers),
            )
        matched_fields = tuple(sorted(label for label, _ in model_constraints + maker_constraints))
        matched_models = [m for m in models if m.model_id in candidates]
        if len(matched_models) > 1:
            return result(
                ResolutionStatus.MULTIPLE_CANDIDATES,
                "Compatible clues still identify multiple catalog models; ordering is not evidence.",
                candidate_matches=tuple(
                    CandidateMatch(
                        model_id=m.model_id,
                        marketed_name=m.marketed_name,
                        confidence_rank=i + 1,
                        matched_fields=matched_fields,
                        unmatched_fields=tuple(unresolved),
                    )
                    for i, m in enumerate(matched_models)
                ),
            )
        selected = matched_models[0]
        manufacturer = self.catalog.get_manufacturer(selected.manufacturer_id)
        model_sources = (*selected.source_ids, *((manufacturer.source_id,) if manufacturer else ()))
        if self._source_gap(model_sources):
            return result(
                ResolutionStatus.UNSUPPORTED_DEVICE,
                "Selected model has synthetic or missing identity source attribution; real-device identity is not established.",
            )
        options = self.catalog.find_variants_for_model(selected.model_id)
        matched_options = tuple(
            v for v in options if allowed_variants is not None and v.variant_id in allowed_variants
        )
        if len(matched_options) == 1 and not unresolved:
            exact = matched_options[0]
            if not self._source_gap(exact.source_ids):
                return result(
                    ResolutionStatus.EXACT_MATCH,
                    "Compatible identifiers explicitly match catalog variant "
                    + exact.variant_id
                    + ".",
                    resolved_model=selected,
                    resolved_variant=exact,
                    candidate_matches=self._candidates(
                        selected, matched_options, matched_fields, ()
                    ),
                    limitations=(
                        "Catalog identity match only; source claims and physical authenticity are not verified.",
                    ),
                )
            unresolved.append("variant source attribution is synthetic or missing")
        return result(
            ResolutionStatus.MODEL_MATCH_AMBIGUOUS_VARIANT,
            "Model matched; no exact regional variant established. "
            + (
                "Unresolved fields: " + ", ".join(unresolved)
                if unresolved
                else "A compatible discriminating variant code is required regardless of catalog size."
            ),
            resolved_model=selected,
            candidate_matches=self._candidates(
                selected, matched_options or options, matched_fields, tuple(unresolved)
            ),
            limitations=("Catalog candidate list is not proof of complete regional coverage.",),
        )

    def _source_gap(self, source_ids: tuple[str, ...]) -> bool:
        # Identity guard only: no source-conflict or general catalog repair here.
        return not source_ids or any(
            (source := self.catalog.get_source(sid)) is None or source.is_synthetic
            for sid in source_ids
        )

    @staticmethod
    def _candidates(
        model: DeviceModelReference,
        variants: tuple[DeviceVariantReference, ...],
        matched: tuple[str, ...],
        unresolved: tuple[str, ...],
    ) -> tuple[CandidateMatch, ...]:
        return tuple(
            CandidateMatch(
                model_id=model.model_id,
                variant_id=v.variant_id,
                marketed_name=model.marketed_name,
                confidence_rank=i + 1,
                matched_fields=matched,
                unmatched_fields=unresolved,
                match_notes="Catalog candidate only; position does not establish identity.",
            )
            for i, v in enumerate(variants)
        )
