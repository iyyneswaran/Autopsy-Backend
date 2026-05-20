"""
Atopsy — Data Normalization Engine (Layer 2).

Orchestrates the complete normalization pipeline:
  Raw Metadata → Clean → Medical Standardization → Synonym Resolution →
  Forensic Entity Extraction → Toxicology Normalization → Ontology Mapping →
  Canonical Structuring → Anomaly Pre-checks → Quality Scoring → Persist

Modular stage-based architecture with per-stage reporting and audit trail.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logger import logger
from app.exceptions.pipeline import NormalizationError
from app.models.pipeline import (
    EvidenceFile,
    MetadataRecord,
    NormalizationRecord,
    NormalizationStatus,
)
from app.pipeline.normalization.anomaly import run_anomaly_checks
from app.pipeline.normalization.quality import compute_quality_report
from app.pipeline.normalization.stages.cleaning import clean_dict_values
from app.pipeline.normalization.stages.confidence_tracker import (
    ConfidenceTracker,
    TransformationType,
)
from app.pipeline.normalization.stages.structuring import build_canonical_output


class NormalizationEngine:
    """
    Enterprise-grade forensic data normalization engine.

    Processes evidence files through a 9-stage pipeline:
    1. Cleaning — text/encoding normalization
    2. Medical Standardization — abbreviation expansion, text normalization
    3. Synonym Resolution — colloquial → scientific term mapping
    4. Forensic Entity Extraction — typed entity detection
    5. Toxicology Normalization — substance/level standardization
    6. Ontology Mapping — ICD-10, anatomical hierarchy, drug classification
    7. Canonical Structuring — build standardized forensic output
    8. Anomaly Pre-checks — detect data quality issues
    9. Quality Scoring — compute confidence/completeness metrics
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def normalize(
        self,
        evidence_file_id: str,
    ) -> dict[str, Any]:
        """
        Run the full normalization pipeline for a single evidence file.

        Args:
            evidence_file_id: UUID of the EvidenceFile to normalize.

        Returns:
            Dict with normalization results, quality report, anomalies.
        """
        start_time = time.monotonic()
        stage_reports: list[dict[str, Any]] = []
        audit_trail: list[dict[str, Any]] = []
        confidence_tracker = ConfidenceTracker()

        # ── Load evidence file ───────────────
        evidence = (
            self.db.query(EvidenceFile)
            .filter(EvidenceFile.id == uuid.UUID(evidence_file_id))
            .first()
        )

        if not evidence:
            raise NormalizationError(
                f"Evidence file {evidence_file_id} not found",
                context={"evidence_file_id": evidence_file_id},
            )

        # ── Load metadata ────────────────────
        meta_records = (
            self.db.query(MetadataRecord)
            .filter(
                MetadataRecord.evidence_file_id == uuid.UUID(evidence_file_id)
            )
            .all()
        )

        # Merge all metadata into one dict
        raw_metadata: dict[str, Any] = {}
        for record in meta_records:
            if record.extracted_data:
                raw_metadata.update(record.extracted_data)

        logger.info(
            f"Starting normalization for evidence {evidence_file_id} "
            f"({evidence.original_filename})"
        )

        # ── Create normalization record ──────
        norm_record = NormalizationRecord(
            evidence_file_id=uuid.UUID(evidence_file_id),
            status=NormalizationStatus.IN_PROGRESS,
        )
        self.db.add(norm_record)
        self.db.flush()

        # Pipeline context — accumulates data through stages
        context: dict[str, Any] = {
            "forensic_entities": None,
            "toxicology_results": [],
            "ontology_mappings": [],
            "synonym_substitutions": [],
        }

        try:
            # ── Stage 1: Cleaning ────────────
            cleaned_metadata = self._run_stage(
                "cleaning",
                stage_reports,
                lambda: self._stage_cleaning(raw_metadata, audit_trail),
                fallback=raw_metadata,
            )

            # ── Stage 2: Medical Standardization ──
            standardized_metadata = self._run_stage(
                "medical_standardization",
                stage_reports,
                lambda: self._stage_medical(
                    cleaned_metadata, audit_trail, confidence_tracker
                ),
                fallback=cleaned_metadata,
            )

            # ── Stage 3: Synonym Resolution ──
            resolved_metadata = self._run_stage(
                "synonym_resolution",
                stage_reports,
                lambda: self._stage_synonyms(
                    standardized_metadata, context, audit_trail, confidence_tracker
                ),
                fallback=standardized_metadata,
            )

            # ── Stage 4: Forensic Entity Extraction ──
            self._run_stage(
                "forensic_entity_extraction",
                stage_reports,
                lambda: self._stage_entity_extraction(
                    resolved_metadata, context, confidence_tracker
                ),
                fallback=None,
            )

            # ── Stage 5: Toxicology Normalization ──
            self._run_stage(
                "toxicology_normalization",
                stage_reports,
                lambda: self._stage_toxicology(
                    context, audit_trail, confidence_tracker
                ),
                fallback=None,
            )

            # ── Stage 6: Ontology Mapping ────
            self._run_stage(
                "ontology_mapping",
                stage_reports,
                lambda: self._stage_ontology(
                    context, confidence_tracker
                ),
                fallback=None,
            )

            # ── Stage 7: Canonical Structuring ──
            canonical = self._run_stage(
                "structuring",
                stage_reports,
                lambda: self._stage_structuring(
                    evidence_file_id, evidence, resolved_metadata, context
                ),
                fallback={
                    "source_evidence_id": evidence_file_id,
                    "raw_metadata": resolved_metadata,
                },
            )

            # ── Stage 8: Anomaly Pre-checks ──
            anomalies = self._run_stage(
                "anomaly_checks",
                stage_reports,
                lambda: run_anomaly_checks(resolved_metadata, canonical),
                fallback=[],
            )

            # ── Stage 9: Quality Scoring ─────
            quality_report = self._run_stage(
                "quality_scoring",
                stage_reports,
                lambda: compute_quality_report(
                    evidence_file_id=evidence_file_id,
                    canonical=canonical,
                    anomalies=anomalies,
                    stage_reports=stage_reports,
                ),
                fallback={
                    "overall_quality_score": 0.0,
                    "completeness_score": 0.0,
                    "confidence_score": 0.0,
                },
            )

            # ── Inject audit trail into canonical output ──
            canonical["normalization_audit"] = {
                "transformation_count": len(audit_trail),
                "transformations": audit_trail[:200],
                "confidence_tracking": confidence_tracker.to_dict(),
                "stages_executed": len(stage_reports),
            }

            # ── Persist Results ──────────────
            completed_stages = [
                s["stage_name"]
                for s in stage_reports
                if s["status"] == "completed"
            ]
            failed_stages = [
                s["stage_name"]
                for s in stage_reports
                if s["status"] == "failed"
            ]

            has_failures = len(failed_stages) > 0
            norm_record.status = (
                NormalizationStatus.PARTIAL
                if has_failures
                else NormalizationStatus.COMPLETED
            )
            norm_record.canonical_output = canonical
            norm_record.quality_score = quality_report.get(
                "overall_quality_score", 0.0
            )
            norm_record.completeness_score = quality_report.get(
                "completeness_score", 0.0
            )
            norm_record.confidence_score = quality_report.get(
                "confidence_score", 0.0
            )
            norm_record.quality_report = quality_report
            norm_record.anomalies_detected = anomalies
            norm_record.anomaly_count = len(anomalies)
            norm_record.stages_completed = completed_stages
            norm_record.stages_failed = failed_stages
            norm_record.completed_at = datetime.now(timezone.utc)

            self.db.commit()

            elapsed = round(time.monotonic() - start_time, 3)
            logger.info(
                f"Normalization completed for {evidence_file_id} "
                f"in {elapsed}s — quality={norm_record.quality_score:.2f}, "
                f"anomalies={len(anomalies)}, "
                f"stages={len(completed_stages)}/{len(stage_reports)}"
            )

            return {
                "normalization_id": str(norm_record.id),
                "evidence_file_id": evidence_file_id,
                "status": norm_record.status.value,
                "canonical_output": canonical,
                "quality_report": quality_report,
                "anomalies": anomalies,
                "stages_completed": completed_stages,
                "stages_failed": failed_stages,
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            norm_record.status = NormalizationStatus.FAILED
            norm_record.error_message = str(e)
            self.db.commit()

            logger.error(
                f"Normalization failed for {evidence_file_id}: {e}"
            )
            raise NormalizationError(
                f"Normalization failed: {e}",
                context={"evidence_file_id": evidence_file_id},
            ) from e

    # ─────────────────────────────────────────
    # Stage Implementations
    # ─────────────────────────────────────────

    def _stage_cleaning(
        self,
        raw_metadata: dict[str, Any],
        audit_trail: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Stage 1: Text and encoding normalization."""
        cleaned = clean_dict_values(raw_metadata)
        diff_count = self._count_diff(raw_metadata, cleaned)
        if diff_count > 0:
            audit_trail.append({
                "stage": "cleaning",
                "action": "clean_dict_values",
                "fields_modified": diff_count,
            })
        return cleaned

    def _stage_medical(
        self,
        metadata: dict[str, Any],
        audit_trail: list[dict[str, Any]],
        tracker: ConfidenceTracker,
    ) -> dict[str, Any]:
        """Stage 2: Medical text standardization."""
        from app.pipeline.normalization.stages.medical import (
            standardize_medical_text,
            expand_abbreviation,
        )

        result = {}
        modifications = 0

        for key, value in metadata.items():
            if isinstance(value, str) and len(value) > 2:
                standardized = standardize_medical_text(value)
                if standardized != value:
                    modifications += 1
                    audit_trail.append({
                        "stage": "medical_standardization",
                        "field": key,
                        "original": value[:100],
                        "normalized": standardized[:100],
                        "rule": "abbreviation_expansion",
                    })
                    tracker.record_transformation(
                        field=key,
                        stage="medical_standardization",
                        transformation_type=TransformationType.EXACT_MATCH,
                        rule="abbreviation_expansion",
                    )
                result[key] = standardized
            elif isinstance(value, dict):
                result[key] = self._apply_medical_to_dict(
                    value, audit_trail, tracker
                )
            else:
                result[key] = value

        return result

    def _apply_medical_to_dict(
        self,
        d: dict[str, Any],
        audit_trail: list[dict[str, Any]],
        tracker: ConfidenceTracker,
    ) -> dict[str, Any]:
        """Recursively apply medical standardization to nested dicts."""
        from app.pipeline.normalization.stages.medical import standardize_medical_text

        result = {}
        for key, value in d.items():
            if isinstance(value, str) and len(value) > 2:
                standardized = standardize_medical_text(value)
                if standardized != value:
                    audit_trail.append({
                        "stage": "medical_standardization",
                        "field": key,
                        "original": value[:100],
                        "normalized": standardized[:100],
                    })
                result[key] = standardized if isinstance(value, str) else value
            elif isinstance(value, dict):
                result[key] = self._apply_medical_to_dict(value, audit_trail, tracker)
            else:
                result[key] = value
        return result

    def _stage_synonyms(
        self,
        metadata: dict[str, Any],
        context: dict[str, Any],
        audit_trail: list[dict[str, Any]],
        tracker: ConfidenceTracker,
    ) -> dict[str, Any]:
        """Stage 3: Synonym resolution."""
        from app.pipeline.normalization.stages.synonym_resolver import (
            resolve_synonyms,
        )

        result = {}
        all_substitutions = []

        for key, value in metadata.items():
            if isinstance(value, str) and len(value) > 3:
                resolution = resolve_synonyms(value)
                result[key] = resolution.resolved_text

                for sub in resolution.substitutions:
                    all_substitutions.append(sub.to_dict())
                    audit_trail.append({
                        "stage": "synonym_resolution",
                        "field": key,
                        "original": sub.original,
                        "normalized": sub.resolved,
                        "category": sub.category,
                    })
                    tracker.record_transformation(
                        field=key,
                        stage="synonym_resolution",
                        transformation_type=TransformationType.EXACT_MATCH,
                        rule=f"synonym:{sub.original}→{sub.resolved}",
                    )
            else:
                result[key] = value

        context["synonym_substitutions"] = all_substitutions
        return result

    def _stage_entity_extraction(
        self,
        metadata: dict[str, Any],
        context: dict[str, Any],
        tracker: ConfidenceTracker,
    ) -> None:
        """Stage 4: Forensic entity extraction."""
        from app.pipeline.normalization.stages.forensic_entity_extractor import (
            extract_forensic_entities,
        )

        # Build text from content preview or all string values
        text_parts = []
        for key in ["content_preview", "extracted_text", "full_text"]:
            if key in metadata and isinstance(metadata[key], str):
                text_parts.append(metadata[key])

        if not text_parts:
            text_parts = [
                str(v) for v in metadata.values()
                if isinstance(v, str) and len(v) > 20
            ]

        full_text = "\n".join(text_parts)
        entities = extract_forensic_entities(full_text)
        context["forensic_entities"] = entities

        # Track confidence for key entities
        for entity in entities.all_entities:
            tracker.set_initial(
                f"entity:{entity.entity_type}",
                entity.confidence,
            )

    def _stage_toxicology(
        self,
        context: dict[str, Any],
        audit_trail: list[dict[str, Any]],
        tracker: ConfidenceTracker,
    ) -> None:
        """Stage 5: Toxicology normalization."""
        from app.pipeline.normalization.stages.toxicology_normalizer import (
            normalize_toxicology,
        )

        entities = context.get("forensic_entities")
        if not entities:
            return

        # Extract raw toxicology findings from entities
        raw_findings = []
        for entity in entities.toxicology:
            raw_findings.append({
                "substance": entity.raw_value,
                "result": entity.normalized_value,
            })

        if not raw_findings:
            return

        normalized = normalize_toxicology(raw_findings)
        context["toxicology_results"] = [n.to_dict() for n in normalized]

        for finding in normalized:
            audit_trail.append({
                "stage": "toxicology_normalization",
                "original": finding.original_substance,
                "normalized": finding.substance,
                "level": finding.level_classification,
            })
            tracker.record_transformation(
                field=f"tox:{finding.substance}",
                stage="toxicology_normalization",
                transformation_type=TransformationType.EXACT_MATCH,
                override_confidence=finding.confidence,
            )

    def _stage_ontology(
        self,
        context: dict[str, Any],
        tracker: ConfidenceTracker,
    ) -> None:
        """Stage 6: Ontology mapping."""
        from app.pipeline.normalization.stages.ontology_mapper import (
            map_to_ontology,
        )

        entities = context.get("forensic_entities")
        if not entities:
            return

        # Convert entities to dicts for mapping
        entity_dicts = [e.to_dict() for e in entities.all_entities]
        mappings = map_to_ontology(entity_dicts)

        context["ontology_mappings"] = [m.to_dict() for m in mappings]

        for mapping in mappings:
            tracker.record_transformation(
                field=f"ontology:{mapping.source_term}",
                stage="ontology_mapping",
                transformation_type=TransformationType.ONTOLOGY_MAPPED,
                rule=f"{mapping.ontology_system}:{mapping.ontology_code}",
                override_confidence=mapping.confidence,
            )

    def _stage_structuring(
        self,
        evidence_file_id: str,
        evidence: Any,
        metadata: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Stage 7: Canonical structuring with forensic data."""
        canonical = build_canonical_output(
            evidence_file_id=evidence_file_id,
            original_filename=evidence.original_filename,
            mime_type=evidence.mime_type,
            category=(
                evidence.category.value
                if hasattr(evidence.category, "value")
                else str(evidence.category)
            ),
            file_size=evidence.file_size,
            sha256_hash=evidence.sha256_hash,
            metadata=metadata,
        )

        # Enrich with forensic data from pipeline context
        entities = context.get("forensic_entities")
        if entities:
            entity_data = entities.to_dict()
            canonical["forensic_entities"] = entity_data

            # Build autopsy_metadata from entities
            autopsy_meta = self._build_autopsy_metadata(entities)
            if autopsy_meta:
                canonical["autopsy_metadata"] = autopsy_meta

            # Build victim_data from deceased entities
            victim_data = self._build_victim_data(entities)
            if victim_data:
                canonical["victim_data"] = victim_data

        # Add toxicology results
        tox_results = context.get("toxicology_results", [])
        if tox_results:
            canonical["toxicology_results"] = tox_results

        # Add ontology mappings
        ontology = context.get("ontology_mappings", [])
        if ontology:
            canonical["ontology_mappings"] = ontology

        # Add synonym substitutions
        synonyms = context.get("synonym_substitutions", [])
        if synonyms:
            canonical["synonym_substitutions"] = synonyms

        return canonical

    # ─────────────────────────────────────────
    # Forensic Data Builders
    # ─────────────────────────────────────────

    def _build_autopsy_metadata(self, entities: Any) -> dict[str, Any] | None:
        """Build autopsy metadata section from extracted entities."""
        meta: dict[str, Any] = {}

        if entities.cause_of_death:
            cod = entities.cause_of_death[0]
            meta["cause_of_death"] = cod.normalized_value

            from app.pipeline.normalization.stages.medical import (
                classify_cause_of_death,
            )
            meta["cause_of_death_category"] = classify_cause_of_death(
                cod.normalized_value
            )

        if entities.manner_of_death:
            from app.pipeline.normalization.stages.medical import (
                normalize_manner_of_death,
            )
            mod = entities.manner_of_death[0]
            meta["manner_of_death"] = normalize_manner_of_death(
                mod.normalized_value
            )

        if entities.time_of_death:
            meta["time_of_death"] = entities.time_of_death[0].normalized_value

        if entities.examining_doctor:
            meta["examiner"] = entities.examining_doctor[0].normalized_value

        if entities.case_identifier:
            meta["case_number"] = entities.case_identifier[0].normalized_value

        # Build injuries list with classifications
        if entities.injuries:
            from app.pipeline.normalization.stages.medical import (
                classify_injury_severity,
                normalize_injury_type,
                normalize_body_region,
                classify_wound_age,
            )

            injuries_list = []
            for inj in entities.injuries:
                injury_dict = {
                    "description": inj.normalized_value,
                    "injury_type": normalize_injury_type(
                        inj.normalized_value.split()[0]
                        if inj.normalized_value
                        else ""
                    ),
                    "severity": classify_injury_severity(inj.normalized_value),
                    "wound_age": classify_wound_age(inj.normalized_value),
                    "confidence": inj.confidence,
                }
                injuries_list.append(injury_dict)
            meta["injuries"] = injuries_list

        return meta if meta else None

    def _build_victim_data(self, entities: Any) -> dict[str, Any] | None:
        """Build victim data section from deceased entities."""
        data: dict[str, Any] = {}
        for ent in entities.deceased_info:
            if ent.entity_type == "DECEASED_NAME":
                data["name"] = ent.normalized_value
            elif ent.entity_type == "DECEASED_AGE":
                try:
                    data["age"] = int(ent.normalized_value)
                except (ValueError, TypeError):
                    data["age_text"] = ent.normalized_value
            elif ent.entity_type == "DECEASED_GENDER":
                data["gender"] = ent.normalized_value
        return data if data else None

    # ─────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────

    def _run_stage(
        self,
        stage_name: str,
        stage_reports: list[dict[str, Any]],
        fn: Any,
        fallback: Any = None,
    ) -> Any:
        """Execute a pipeline stage with timing and error handling."""
        stage_start = time.monotonic()
        try:
            result = fn()
            elapsed = round((time.monotonic() - stage_start) * 1000, 2)
            stage_reports.append({
                "stage_name": stage_name,
                "status": "completed",
                "duration_ms": elapsed,
            })
            return result if result is not None else fallback
        except Exception as e:
            elapsed = round((time.monotonic() - stage_start) * 1000, 2)
            logger.error(f"Stage '{stage_name}' failed: {e}")
            stage_reports.append({
                "stage_name": stage_name,
                "status": "failed",
                "error": str(e),
                "duration_ms": elapsed,
            })
            return fallback

    def normalize_batch(
        self,
        evidence_file_ids: list[str],
    ) -> list[dict[str, Any]]:
        """Normalize multiple evidence files."""
        results: list[dict[str, Any]] = []
        for eid in evidence_file_ids:
            try:
                result = self.normalize(eid)
                results.append(result)
            except Exception as e:
                results.append({
                    "evidence_file_id": eid,
                    "status": "FAILED",
                    "error": str(e),
                })
        return results

    @staticmethod
    def _count_diff(
        original: dict[str, Any],
        cleaned: dict[str, Any],
    ) -> int:
        """Count how many values changed during cleaning."""
        count = 0
        for key in original:
            if key in cleaned and original[key] != cleaned[key]:
                count += 1
        return count
