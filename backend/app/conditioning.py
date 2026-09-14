"""Conditioning catalog and validation for structural image controls."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Conditioner:
    id: str
    label: str
    kind: str
    description: str


CONDITIONERS = [
    Conditioner("none", "No structural control", "none", "Prompt-only generation"),
    Conditioner("pose", "OpenPose", "controlnet", "Preserve human pose and body layout"),
    Conditioner("depth", "Depth map", "controlnet", "Preserve spatial depth and composition"),
    Conditioner("canny", "Canny edges", "controlnet", "Follow strong visual contours"),
    Conditioner("tile", "Tile detail", "controlnet", "Preserve texture and local detail"),
    Conditioner("ip-adapter", "IP Adapter", "ip-adapter", "Guide identity and visual references"),
]


def catalog() -> list[dict[str, str]]:
    return [conditioner.__dict__ for conditioner in CONDITIONERS]
