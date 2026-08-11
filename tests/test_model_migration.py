from __future__ import annotations

import json
from pathlib import Path

import pytest

from novelvideo import config
from novelvideo.model_catalog import get_bindings, merge_models
from novelvideo.model_migration import apply_model_migration, build_model_migration_report


def _isolate_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    state_dir = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", str(state_dir))
    monkeypatch.delenv("ST_CONTROL_PLANE_DSN", raising=False)
    return state_dir


def test_dry_run_maps_catalog_models_without_writing(monkeypatch, tmp_path) -> None:
    state_dir = _isolate_settings(monkeypatch, tmp_path)
    merge_models([{"id": "chat-one"}, {"id": "image-one"}, {"id": "video-one"}])
    monkeypatch.setenv("MODEL_NAME", "chat-one")
    project_path = state_dir / "alice" / "demo" / "project_config.json"
    project_path.parent.mkdir(parents=True)
    project_path.write_text(
        json.dumps({"render_image_selection": "image-one", "video_backend": "comfyui"}),
        encoding="utf-8",
    )

    report = build_model_migration_report(project_root=state_dir)

    assert report["proposedBindings"]["hermes_llm"] == "chat-one"
    assert report["proposedBindings"]["render_image"] == "image-one"
    assert report["localTransports"][0]["rawValue"] == "comfyui"
    assert get_bindings() == {}
    assert "render_image_selection" in json.loads(project_path.read_text(encoding="utf-8"))


def test_apply_backs_up_removes_mapped_fields_and_is_idempotent(monkeypatch, tmp_path) -> None:
    state_dir = _isolate_settings(monkeypatch, tmp_path)
    merge_models([{"id": "image-one"}])
    project_path = state_dir / "alice" / "demo" / "project_config.json"
    project_path.parent.mkdir(parents=True)
    project_path.write_text(
        json.dumps({"render_image_selection": "image-one", "visual_style": "comic"}),
        encoding="utf-8",
    )

    applied = apply_model_migration(project_root=state_dir)

    assert applied["applied"] is True
    assert Path(applied["backupDir"], "runtime_settings.json").exists()
    assert get_bindings()["render_image"] == "image-one"
    migrated = json.loads(project_path.read_text(encoding="utf-8"))
    assert "render_image_selection" not in migrated
    assert migrated["visual_style"] == "comic"

    repeated = apply_model_migration(project_root=state_dir)
    assert repeated["applied"] is False
    assert repeated["backupDir"] == ""


def test_apply_rejects_cross_project_binding_conflicts(monkeypatch, tmp_path) -> None:
    state_dir = _isolate_settings(monkeypatch, tmp_path)
    merge_models([{"id": "image-one"}, {"id": "image-two"}])
    for project, model in (("one", "image-one"), ("two", "image-two")):
        path = state_dir / "alice" / project / "project_config.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"render_image_selection": model}), encoding="utf-8")

    report = build_model_migration_report(project_root=state_dir)
    assert report["conflicts"]["render_image"] == ["image-one", "image-two"]
    with pytest.raises(ValueError, match="conflicting"):
        apply_model_migration(project_root=state_dir)

def test_apply_rolls_back_on_binding_failure(monkeypatch, tmp_path) -> None:
    from novelvideo import config
    from novelvideo.model_catalog import get_bindings, merge_models, save_bindings
    from novelvideo.model_migration import apply_model_migration, build_model_migration_report

    state_dir = tmp_path / "state"
    monkeypatch.setattr(config, "STATE_DIR", str(state_dir))
    monkeypatch.delenv("ST_CONTROL_PLANE_DSN", raising=False)
    merge_models([{"id": "image-one"}])
    project_path = state_dir / "alice" / "demo" / "project_config.json"
    project_path.parent.mkdir(parents=True)
    project_path.write_text(
        json.dumps({"render_image_selection": "image-one", "visual_style": "comic"}),
        encoding="utf-8",
    )

    original_save = save_bindings
    call_count = 0

    def broken_save(bindings, *_a, **_kw):
        nonlocal call_count
        call_count += 1
        if call_count > 0:
            raise RuntimeError("simulated binding write failure")
        return original_save(bindings)

    monkeypatch.setattr(
        "novelvideo.model_migration.save_bindings",
        broken_save,
    )

    with pytest.raises(RuntimeError, match="simulated binding write failure"):
        apply_model_migration(project_root=state_dir)

    # Project file should NOT have been modified because save_bindings failed
    recovered = json.loads(project_path.read_text(encoding="utf-8"))
    assert "render_image_selection" in recovered, (
        "project_config.json should be unchanged when save_bindings fails"
    )

    # Bindings should not contain the migrated value
    assert get_bindings().get("render_image") is None, (
        "bindings should not be saved when migration fails"
    )

