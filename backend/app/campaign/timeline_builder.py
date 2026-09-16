"""V3.3 — Timeline Builder: seven deliverables, five days, zero new prompts.

Two decisions live here:

* **Multi deliverables** (§V3.3): one briefing automatically produces the
  seven campaign deliverables — Reel 9:16, Story, Shorts, Banner,
  Thumbnail, Feed 1:1 and YouTube Cover — each with its own format,
  medium, resolution and generation prompt. The user is never asked for a
  new prompt: the prompt is composed from the brief fields and the
  deliverable's scene hint, then expanded through the existing
  ``PromptEnhancer`` (the Core's ``PromptCompiler`` facade) by the caller.
* **Campaign timeline**: the deliverables are organised into Dia 1..Dia 5,
  each day with a focus, its own CTA and a *different* set of assets
  (Teaser → Bastidores → Alcance → Conversão → Última chamada).

Framework-free: standard library only. The builder draws CTAs from the
``cta_engine`` deck passed to it, so it never invents a repeated CTA.
"""
from __future__ import annotations

from dataclasses import dataclass

from .brief_interpreter import InterpretedBrief
from .cta_engine import CTADeck, CTAExhaustedError, clean_product


# ---------------------------------------------------------------------------
# The seven deliverables
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliverableSpec:
    """One campaign deliverable format: what it is and how it renders."""

    kind: str
    label: str
    medium: str  # "video" ships MP4, "image" ships PNG (export center)
    aspect_ratio: str
    width: int
    height: int
    #: Video deliverables carry the brief's duration; images are stills.
    duration_seconds: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "medium": self.medium,
            "aspect_ratio": self.aspect_ratio,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
        }


DELIVERABLES: tuple[DeliverableSpec, ...] = (
    DeliverableSpec("reel", "Reel 9:16", "video", "9:16", 1080, 1920, 15),
    DeliverableSpec("story", "Story", "image", "9:16", 1080, 1920, None),
    DeliverableSpec("shorts", "Shorts", "video", "9:16", 1080, 1920, 15),
    DeliverableSpec("banner", "Banner", "image", "1.91:1", 1200, 628, None),
    DeliverableSpec("thumbnail", "Thumbnail", "image", "16:9", 1280, 720, None),
    DeliverableSpec("feed", "Feed 1:1", "image", "1:1", 1080, 1080, None),
    DeliverableSpec("cover", "YouTube Cover", "image", "16:9", 2560, 1440, None),
)

DELIVERABLES_BY_KIND: dict[str, DeliverableSpec] = {spec.kind: spec for spec in DELIVERABLES}

#: One cinematic scene hint per deliverable — the seed the generation prompt
#: grows from, so each asset directs a different moment of the campaign.
SCENE_HINTS: dict[str, str] = {
    "reel": "hero reveal of {product}, slow dolly-in on the signature piece, fabric catching the key light",
    "story": "behind-the-scenes frame of {product} being prepared backstage, hands adjusting the detail",
    "shorts": "fast-cut vertical sequence of {product} in motion, street energy, handheld camera",
    "banner": "wide editorial composition of {product}, negative space reserved for the headline",
    "thumbnail": "tight hero still of the {product} signature piece, dramatic side light, clickable contrast",
    "feed": "symmetrical studio composition of {product} on seamless backdrop, catalog clarity",
    "cover": "cinematic wide banner of the {product} world, leading room for the title",
}


# ---------------------------------------------------------------------------
# The five-day timeline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DayFocus:
    """What day N of the campaign is for, and which assets it runs."""

    day: int
    focus: str
    kinds: tuple[str, ...]


TOTAL_DAYS = 5

#: The campaign arc. Every deliverable is scheduled exactly once and every
#: day runs a different set of assets — that pairing is verified by tests.
DAY_PLAN: tuple[DayFocus, ...] = (
    DayFocus(1, "Lançamento", ("reel", "thumbnail")),
    DayFocus(2, "Bastidores", ("story",)),
    DayFocus(3, "Alcance", ("shorts", "cover")),
    DayFocus(4, "Conversão", ("feed",)),
    DayFocus(5, "Última chamada", ("banner",)),
)


# ---------------------------------------------------------------------------
# The built plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssetPlan:
    """One deliverable, fully specified: format, day, prompt and CTA."""

    kind: str
    label: str
    medium: str
    aspect_ratio: str
    width: int
    height: int
    duration_seconds: int | None
    day: int
    position: int
    prompt: str
    cta: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "medium": self.medium,
            "aspect_ratio": self.aspect_ratio,
            "width": self.width,
            "height": self.height,
            "duration_seconds": self.duration_seconds,
            "day": self.day,
            "position": self.position,
            "prompt": self.prompt,
            "cta": self.cta,
        }


@dataclass(frozen=True)
class EpisodePlan:
    """One day of the timeline: focus, CTA and the assets it carries."""

    day: int
    focus: str
    cta: str
    notes: str
    asset_kinds: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "day": self.day,
            "focus": self.focus,
            "cta": self.cta,
            "notes": self.notes,
            "asset_kinds": list(self.asset_kinds),
        }


def compose_prompt(spec: DeliverableSpec, brief: InterpretedBrief, cta: str, focus: str) -> str:
    """The deliverable's base prompt, composed from the brief — never asked again.

    The scene hint, product, audience, platform, duration and the asset's
    own CTA are the six ingredients; the caller passes the result through
    the existing ``PromptEnhancer`` for the cinematic blocks.
    """

    product = clean_product(brief.product)
    scene = SCENE_HINTS[spec.kind].format(product=product)
    duration = (
        f"{brief.duration_seconds}-second cut. "
        if spec.medium == "video"
        else ""
    )
    return (
        f"{spec.label} for the {brief.objective} campaign of {product} (dia {focus}): "
        f"{scene}. Audience: {brief.audience}. Platform: {brief.platform}. "
        f"{duration}Overlay text: “{cta}”"
    )


def build_plan(
    brief: InterpretedBrief,
    deck: CTADeck,
    *,
    enhance=None,
) -> tuple[tuple[AssetPlan, ...], tuple[EpisodePlan, ...]]:
    """Turn one brief into the full deliverable set plus the five-day timeline.

    ``enhance`` is the existing prompt expansion callable (the campaign
    service passes ``PromptEnhancer.enhance``); when None the composed base
    prompt is used as-is. The deck supplies one CTA per deliverable and one
    per day — 12 draws against a 28-template bank, so the deck never runs
    dry for the fixed plan.
    """

    scheduled = {kind for day in DAY_PLAN for kind in day.kinds}
    if scheduled != set(DELIVERABLES_BY_KIND):
        raise CTAExhaustedError("day plan and deliverable catalogue drifted apart")

    expand = enhance if enhance is not None else (lambda prompt, **_: prompt)
    assets: list[AssetPlan] = []
    episodes: list[EpisodePlan] = []
    position_by_kind = {spec.kind: index for index, spec in enumerate(DELIVERABLES)}

    for day in DAY_PLAN:
        day_kinds: list[str] = []
        for kind in day.kinds:
            spec = DELIVERABLES_BY_KIND[kind]
            cta = deck.draw()
            prompt = expand(
                compose_prompt(spec, brief, cta, day.focus),
                style="cinematic realism",
            )
            assets.append(
                AssetPlan(
                    kind=spec.kind,
                    label=spec.label,
                    medium=spec.medium,
                    aspect_ratio=spec.aspect_ratio,
                    width=spec.width,
                    height=spec.height,
                    duration_seconds=brief.duration_seconds if spec.medium == "video" else None,
                    day=day.day,
                    position=position_by_kind[kind],
                    prompt=prompt,
                    cta=cta,
                )
            )
            day_kinds.append(kind)
        episodes.append(
            EpisodePlan(
                day=day.day,
                focus=day.focus,
                cta=deck.draw(),
                notes="",
                asset_kinds=tuple(day_kinds),
            )
        )

    if len(assets) != len(DELIVERABLES):
        raise CTAExhaustedError("the plan must carry every deliverable exactly once")
    if [episode.day for episode in episodes] != list(range(1, TOTAL_DAYS + 1)):
        raise CTAExhaustedError("the timeline must cover Dia 1..Dia 5 in order")
    return tuple(assets), tuple(episodes)
