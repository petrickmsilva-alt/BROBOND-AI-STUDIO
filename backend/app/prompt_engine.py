"""Deterministic prompt composition layer.

This service is provider-agnostic and can later delegate semantic rewriting to
an LLM while preserving the same request/response contract.
"""
from dataclasses import dataclass


@dataclass
class PromptEnhancer:
    default_style: str = "cinematic realism"

    def enhance(self, prompt: str, style: str | None = None, persona: str | None = None, camera: str | None = None, lighting: str | None = None) -> str:
        subject = prompt.strip().rstrip(".")
        identity = f" featuring {persona}" if persona else ""
        shot = camera or "medium shot, 85mm lens, shallow depth of field"
        light = lighting or "soft volumetric light, teal and amber color grade"
        visual_style = style or self.default_style
        return f"Ultra-realistic {visual_style} scene of {subject}{identity}, {shot}, {light}, detailed textures, natural skin, atmospheric depth, cinematic composition, high dynamic range, film grain, IMAX quality."


prompt_engine = PromptEnhancer()
