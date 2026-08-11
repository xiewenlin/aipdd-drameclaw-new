"""Shared NewAPI transport for Freezone vision-understanding tasks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VisionInput:
    data: bytes
    media_type: str = "image/png"


def image_media_type(path: str) -> str:
    """Return the image MIME type expected by multimodal model providers."""
    suffix = str(path).lower().rsplit(".", 1)[-1] if "." in str(path) else ""
    if suffix in {"jpg", "jpeg"}:
        return "image/jpeg"
    if suffix == "webp":
        return "image/webp"
    if suffix == "gif":
        return "image/gif"
    return "image/png"


def resolve_freezone_vision_model(model_override: str | None = None) -> str:
    """Return the globally bound NewAPI model for Freezone vision tasks."""
    del model_override
    from novelvideo.model_catalog import model_runtime_resolver

    return model_runtime_resolver.resolve("vision_analysis_llm").model_id


async def call_freezone_vision_model(
    *,
    prompt: str,
    images: list[VisionInput],
    model_override: str | None = None,
    timeout_seconds: float = 120.0,
) -> tuple[str, str]:
    """Run a PydanticAI vision Agent through the effective NewAPI gateway."""
    if not images:
        raise ValueError("at least one image is required")

    from pydantic_ai import Agent, BinaryContent

    from novelvideo.config import get_pydantic_model

    del timeout_seconds
    model = resolve_freezone_vision_model(model_override)
    agent = Agent(
        get_pydantic_model(feature_id="vision_analysis_llm"),

        output_type=str,
        name="Freezone Vision Analyzer",
    )
    result = await agent.run(
        [
            prompt,
            *[
                BinaryContent(data=image.data, media_type=image.media_type)
                for image in images
            ],
        ]
    )
    text = str(result.output or "").strip()
    if not text:
        raise RuntimeError("视觉模型返回空内容")
    return model, text
