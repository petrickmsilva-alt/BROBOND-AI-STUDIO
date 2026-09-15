"""StyleResolver — the cinematic library.

Responsibility: turn a style the user picked into the whole technical
vocabulary (lens, LUT, lighting, contrast, grain, camera motion, particles,
fps). The user chooses a style; nobody types a prompt.

Independence: imports `contracts` only. The seed catalog below is the
deterministic default source; ETAPA 5 moves it to a Styles table by injecting a
different `StyleSource`.

Vocabulary is grounded in knowledge_base/CINEMATIC_BIBLE.md and the narrative
palettes declared in STYLE_GUIDE.md (Legado, Luxo, Futuro, Disciplina).
"""
from __future__ import annotations

from .contracts import StylePreset, StyleSource

#: Style used when the caller does not pick one. Kept identical to the
#: `PromptEnhancer.default_style` that existed before the Core, so prompts
#: compiled without an explicit style stay recognisably BROBOND.
DEFAULT_STYLE_ID = "cinematic-realism"

#: Returned when an unknown style id is requested: neutral, honest, and never
#: invents a look the library does not have.
NEUTRAL_STYLE_ID = "brobond-neutral"


SEED_STYLES: tuple[StylePreset, ...] = (
    StylePreset(
        style_id=DEFAULT_STYLE_ID,
        name="Cinematic Realism",
        lens="85mm",
        lut="neutral filmic, protected highlights",
        lighting="soft volumetric key, gentle rim separation",
        contrast="controlled, natural skin",
        grain="subtle 35mm grain",
        camera_motion="motivated, steady",
        particles="light atmospheric haze",
        fps=24,
        palette="teal and amber restraint",
        description="BROBOND baseline: tactile realism, natural skin, motivated movement.",
    ),
    StylePreset(
        style_id="imax-hero",
        name="IMAX HERO",
        lens="40mm large format",
        lut="high latitude filmic, deep clean blacks",
        lighting="hard directional key, strong rim, volumetric haze",
        contrast="high, sculpted shadows",
        grain="fine large-format grain",
        camera_motion="slow monumental push-in",
        particles="dust in shafts of light",
        fps=24,
        palette="steel, champagne highlight, deep shadow",
        description="Scale and authority. Architecture dwarfs, subject commands.",
    ),
    StylePreset(
        style_id="john-wick",
        name="JOHN WICK",
        lens="35mm anamorphic",
        lut="cold teal with sodium practicals",
        lighting="hard practical sources, wet reflective floors",
        contrast="crushed blacks, specular highlights",
        grain="tight digital grain",
        camera_motion="locked geometric staging, controlled lateral tracking",
        particles="rain and glass in backlight",
        fps=24,
        palette="noir teal, neon magenta, wet black",
        description="Discipline and menace. Symmetry, silhouettes, readable geography.",
    ),
    StylePreset(
        style_id="luxury-fashion",
        name="LUXURY FASHION",
        lens="85mm portrait compression",
        lut="clean champagne, soft roll-off",
        lighting="large soft key, subtle rim, polished reflections",
        contrast="low, editorial",
        grain="almost none",
        camera_motion="elegant slow dolly, measured",
        particles="none",
        fps=24,
        palette="black, champagne, silver",
        description="Quiet confidence. Material detail and separation over spectacle.",
    ),
    StylePreset(
        style_id="neo-tokyo",
        name="NEO TOKYO",
        lens="24mm wide",
        lut="saturated cyan-magenta night grade",
        lighting="neon practicals, coloured bounce, rain diffusion",
        contrast="high, glowing highlights",
        grain="medium digital grain",
        camera_motion="handheld drift through crowd",
        particles="rain, steam, floating signage glow",
        fps=24,
        palette="deep blue, controlled cyan, magenta accents",
        description="Futurist density. Wet streets, layered light, urban scale.",
    ),
    StylePreset(
        style_id="marvel-trailer",
        name="MARVEL TRAILER",
        lens="28mm dynamic wide",
        lut="punchy teal-orange blockbuster",
        lighting="hero backlight, atmospheric beams",
        contrast="high, lifted shadows",
        grain="clean, low",
        camera_motion="sweeping crane to hero landing",
        particles="embers and debris in backlight",
        fps=24,
        palette="teal shadows, warm hero light",
        description="Trailer rhythm: reveal, escalation, hero beat.",
    ),
    StylePreset(
        style_id=NEUTRAL_STYLE_ID,
        name="BROBOND Neutral",
        lens="50mm",
        lut="neutral",
        lighting="natural available light",
        contrast="balanced",
        grain="none",
        camera_motion="static",
        particles="none",
        fps=24,
        palette="neutral",
        description="Fallback preset. Used when a requested style is not in the library.",
    ),
)


class SeedStyleSource:
    """Default in-memory `StyleSource` backed by the seed catalog."""

    def __init__(self, styles: tuple[StylePreset, ...] = SEED_STYLES) -> None:
        self._by_id: dict[str, StylePreset] = {style.style_id: style for style in styles}
        # Lookups also accept the human name, since the UI shows names.
        self._by_name: dict[str, StylePreset] = {style.name.casefold(): style for style in styles}

    def register(self, style: StylePreset) -> StylePreset:
        self._by_id[style.style_id] = style
        self._by_name[style.name.casefold()] = style
        return style

    def fetch(self, style_id: str) -> StylePreset | None:
        return self._by_id.get(style_id) or self._by_name.get(style_id.strip().casefold())

    def search(self, query: str = "") -> list[StylePreset]:
        if not query:
            return list(self._by_id.values())
        needle = query.strip().casefold()
        return [
            style
            for style in self._by_id.values()
            if needle in style.style_id.casefold() or needle in style.name.casefold()
        ]


class StyleResolver:
    """Resolves a style selection into a full technical vocabulary."""

    def __init__(self, source: StyleSource | None = None) -> None:
        self._source: StyleSource = source or SeedStyleSource()

    def resolve(self, style: str | None) -> StylePreset:
        """Always returns a usable preset. Callers never handle None.

        Two different fallbacks, on purpose:
          * **absent** style (the user did not choose) -> the BROBOND default,
            because "no preference" should still look like BROBOND;
          * **unknown** style (the user asked for something the library does
            not have) -> neutral, because guessing another style's look would
            silently misrepresent the request.
        """

        if not style or not style.strip():
            return self.resolve_default()
        found = self._source.fetch(style)
        if found:
            return found
        return self._source.fetch(NEUTRAL_STYLE_ID) or SEED_STYLES[-1]

    def resolve_default(self) -> StylePreset:
        return self._source.fetch(DEFAULT_STYLE_ID) or SEED_STYLES[0]

    def catalog(self, query: str = "") -> list[StylePreset]:
        """Full library, optionally filtered. Feeds the style picker UI."""

        return self._source.search(query)

    def is_known(self, style: str | None) -> bool:
        return bool(style) and self._source.fetch(style) is not None

    # -------------------------------------------------------------- vocabulary

    def describe(self, style: StylePreset) -> str:
        """STYLE prompt block: the look, without camera or motion detail."""

        return ", ".join(
            part
            for part in (style.name.lower(), style.lut, style.contrast, style.grain, style.palette)
            if part
        )

    def style_phrase(self, style: StylePreset) -> str:
        """STYLE block, name only.

        ETAPA 9: `describe` packs the name together with the grade, which put
        the colour identity in the STYLE block and made it impossible to trim an
        adjective without also losing the palette. This returns just the name;
        `color_phrase` carries the rest. `describe` is kept unchanged because it
        is part of the resolver's public surface.
        """

        return style.name.lower()

    def color_phrase(self, style: StylePreset) -> str:
        """COLOR block: grade, contrast, grain and palette.

        All four fields already existed on `StylePreset` and were reaching the
        model, but folded into STYLE where SYSTEM_PROMPT.md does not put them.
        """

        return ", ".join(
            part for part in (style.lut, style.contrast, style.grain, style.palette) if part
        )

    def lighting_phrase(self, style: StylePreset) -> str:
        return style.lighting

    def lens_phrase(self, style: StylePreset) -> str:
        return style.lens

    def motion_phrase(self, style: StylePreset) -> str:
        return ", ".join(part for part in (style.camera_motion, style.particles) if part)

    def environment_phrase(self, style: StylePreset) -> str:
        return style.particles
