"""Dry-run and apply migration from legacy model selections to global bindings."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from novelvideo.model_catalog import get_bindings, get_models, save_bindings
from novelvideo.model_gateway_settings import _read_all, _write_many

_MIGRATION_STATUS_KEY = "feature_model_migration_v1"
_LOCAL_VIDEO_TRANSPORTS = {"comfyui", "jimeng", "ltx23"}
_PROJECT_MODEL_FIELDS: dict[str, tuple[str, ...]] = {
    "sketch_image_selection": ("sketch_image",),
    "render_image_selection": ("render_image",),
    "image_generation_selection": ("render_image",),
    "character_image_selection": ("character_reference_image",),
    "image_source_selection": ("render_image",),
    "video_backend": ("image_to_video", "text_to_video"),
    "tts_model": ("character_tts",),
    "cognee_embedding_model": ("knowledge_embedding",),
}
_ENV_MODEL_FIELDS: dict[str, tuple[str, ...]] = {
    "MODEL_NAME": (
        "hermes_llm",
        "scene_builder_llm",
        "content_rewriter_llm",
        "video_prompt_optimizer_llm",
    ),
    "FREEZONE_VISION_MODEL": ("vision_analysis_llm",),
    "NEWAPI_IMAGE_MODEL": ("sketch_image", "render_image", "scene_master_image"),
    "SCENE_360_IMAGE_MODEL": ("scene_360_image",),
    "PROP_REF_IMAGE_MODEL": ("prop_reference_image",),
    "CHARACTER_IMAGE_MODEL": ("character_reference_image",),
    "VIDEO_BACKEND": ("image_to_video", "text_to_video"),
    "INDEXTTS2_NEWAPI_MODEL": ("character_tts",),
    "BACKGROUND_MUSIC_MODEL": ("background_music",),
    "COGNEE_EMBEDDING_MODEL": ("knowledge_embedding",),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_config_paths(project_root: str | Path | None = None) -> list[Path]:
    if project_root is None:
        from novelvideo import config

        project_root = config.STATE_DIR
    root = Path(project_root)
    if not root.exists():
        return []
    return sorted(
        path
        for path in root.rglob("project_config.json")
        if "model_migration_backups" not in path.parts
    )


def _selection_model(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    from novelvideo.config import IMAGE_GENERATION_SELECTIONS

    selection = IMAGE_GENERATION_SELECTIONS.get(clean)
    if selection:
        return str(selection.get("model") or "").strip()
    lowered = clean.lower()
    if lowered.startswith("newapi_"):
        return clean[len("newapi_") :]
    return clean


def _classify_value(value: Any, catalog_ids: set[str]) -> tuple[str, str]:
    clean = str(value or "").strip()
    if not clean:
        return "empty", ""
    if clean.lower() in _LOCAL_VIDEO_TRANSPORTS:
        return "local_transport", ""
    model_id = _selection_model(clean)
    if model_id in catalog_ids:
        return "mapped", model_id
    return "unresolved", model_id


def build_model_migration_report(*, project_root: str | Path | None = None) -> dict[str, Any]:
    catalog_ids = {str(item.get("id")) for item in get_models() if item.get("id")}
    current_bindings = get_bindings()
    candidates: list[dict[str, Any]] = []

    for env_name, feature_ids in _ENV_MODEL_FIELDS.items():
        raw_value = os.environ.get(env_name, "")
        if not raw_value:
            continue
        status, model_id = _classify_value(raw_value, catalog_ids)
        for feature_id in feature_ids:
            candidates.append({
                "source": f"env:{env_name}",
                "featureId": feature_id,
                "rawValue": raw_value,
                "modelId": model_id,
                "status": status,
            })

    settings = _read_all()
    legacy_setting_map = {
        "custom_newapi_embedding_model": ("knowledge_embedding",),
        "custom_newapi_image_model": ("character_reference_image", "render_image"),
        "custom_newapi_video_model": ("image_to_video", "text_to_video"),
        "custom_newapi_audio_model": ("character_tts", "background_music"),
    }
    for key, feature_ids in legacy_setting_map.items():
        raw_value = settings.get(key, "")
        if not raw_value:
            continue
        status, model_id = _classify_value(raw_value, catalog_ids)
        for feature_id in feature_ids:
            candidates.append({
                "source": f"settings:{key}",
                "featureId": feature_id,
                "rawValue": raw_value,
                "modelId": model_id,
                "status": status,
            })

    project_documents: dict[str, dict[str, Any]] = {}
    for path in _project_config_paths(project_root):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            candidates.append({
                "source": f"project:{path}",
                "featureId": "",
                "rawValue": "",
                "modelId": "",
                "status": "invalid_project_config",
            })
            continue
        if not isinstance(document, dict):
            continue
        project_documents[str(path)] = document
        for field, feature_ids in _PROJECT_MODEL_FIELDS.items():
            if field not in document:
                continue
            raw_value = document.get(field)
            status, model_id = _classify_value(raw_value, catalog_ids)
            for feature_id in feature_ids:
                candidates.append({
                    "source": f"project:{path}",
                    "projectPath": str(path),
                    "field": field,
                    "featureId": feature_id,
                    "rawValue": raw_value,
                    "modelId": model_id,
                    "status": status,
                })

    proposals: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    for feature_id in {item["featureId"] for item in candidates if item.get("featureId")}:
        mapped = sorted({
            str(item["modelId"])
            for item in candidates
            if item.get("featureId") == feature_id and item.get("status") == "mapped"
        })
        current = current_bindings.get(feature_id)
        if current:
            proposals[feature_id] = current
            if mapped and any(model_id != current for model_id in mapped):
                conflicts[feature_id] = sorted(set(mapped + [current]))
        elif len(mapped) == 1:
            proposals[feature_id] = mapped[0]
        elif len(mapped) > 1:
            conflicts[feature_id] = mapped

    removals: list[dict[str, str]] = []
    for item in candidates:
        if item.get("status") != "mapped" or not item.get("projectPath"):
            continue
        feature_id = str(item["featureId"])
        if feature_id not in conflicts and proposals.get(feature_id) == item.get("modelId"):
            removal = {"projectPath": str(item["projectPath"]), "field": str(item["field"])}
            if removal not in removals:
                removals.append(removal)

    unresolved = [item for item in candidates if item.get("status") in {"unresolved", "invalid_project_config"}]
    local_transports = [item for item in candidates if item.get("status") == "local_transport"]
    return {
        "version": 1,
        "generatedAt": _now_iso(),
        "currentBindings": current_bindings,
        "proposedBindings": proposals,
        "conflicts": conflicts,
        "projectFieldRemovals": removals,
        "unresolved": unresolved,
        "localTransports": local_transports,
        "candidates": candidates,
        "canApply": not conflicts,
    }


def apply_model_migration(*, project_root: str | Path | None = None) -> dict[str, Any]:
    report = build_model_migration_report(project_root=project_root)
    if report["conflicts"]:
        raise ValueError("legacy model selections contain conflicting global bindings")

    binding_updates = {
        feature_id: model_id
        for feature_id, model_id in report["proposedBindings"].items()
        if report["currentBindings"].get(feature_id) != model_id
    }
    removals = list(report["projectFieldRemovals"])
    if not binding_updates and not removals:
        return {**report, "applied": False, "backupDir": ""}

    if project_root is None:
        from novelvideo import config

        project_root = config.STATE_DIR
    backup_dir = Path(project_root) / "local" / "model_migration_backups" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir.mkdir(parents=True, exist_ok=False)
    (backup_dir / "runtime_settings.json").write_text(
        json.dumps(_read_all(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    paths_to_fields: dict[Path, set[str]] = {}
    for item in removals:
        paths_to_fields.setdefault(Path(item["projectPath"]), set()).add(item["field"])
    replaced_files: list[tuple[Path, Path]] = []
    temp_paths: list[Path] = []
    previous_bindings = dict(report["currentBindings"])
    bindings_applied = False
    try:
        for index, (path, fields) in enumerate(
            sorted(paths_to_fields.items(), key=lambda pair: str(pair[0]))
        ):
            backup_path = backup_dir / f"project_config_{index}.json"
            shutil.copy2(path, backup_path)
            document = json.loads(path.read_text(encoding="utf-8"))
            for field in fields:
                document.pop(field, None)
            temp_path = path.with_suffix(f"{path.suffix}.migration.tmp")
            temp_paths.append(temp_path)
            temp_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temp_path, path)
            replaced_files.append((path, backup_path))

        if binding_updates:
            save_bindings(binding_updates)
            bindings_applied = True
        applied_at = _now_iso()
        status = {
            "version": 1,
            "appliedAt": applied_at,
            "backupDir": str(backup_dir),
            "bindingUpdates": binding_updates,
            "projectFieldRemovals": removals,
        }
        _write_many(
            {
                _MIGRATION_STATUS_KEY: json.dumps(
                    status, ensure_ascii=False, separators=(",", ":")
                )
            }
        )
    except BaseException:
        for temp_path in temp_paths:
            temp_path.unlink(missing_ok=True)
        for original_path, backup_path in reversed(replaced_files):
            shutil.copy2(backup_path, original_path)
        if bindings_applied:
            from novelvideo import model_catalog

            current_bindings = get_bindings()
            rollback_bindings = {
                feature_id: previous_bindings.get(feature_id)
                for feature_id in set(current_bindings) | set(binding_updates)
            }
            model_catalog.save_bindings(rollback_bindings)
        raise

    return {**report, "applied": True, "appliedAt": applied_at, "backupDir": str(backup_dir)}