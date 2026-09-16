"""Static mood configuration for the Director AI Engine.

The director can plan without a model because every mood is an explicit preset:
look-up table, contrast, lighting, temperature, rhythm and particles are
configuration, not inline literals scattered through the engine.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

MOOD_LUXURY = "Luxury"
MOOD_EPIC = "Epic"
MOOD_DARK = "Dark"
MOOD_MINIMAL = "Minimal"
MOOD_SPORT = "Sport"
MOOD_NEO = "Neo"

DEFAULT_MOOD = MOOD_MINIMAL

MOOD_NAMES: tuple[str, ...] = (
    MOOD_LUXURY,
    MOOD_EPIC,
    MOOD_DARK,
    MOOD_MINIMAL,
    MOOD_SPORT,
    MOOD_NEO,
)


@dataclass(frozen=True)
class MoodPreset:
    """One internal Director AI mood preset."""

    name: str
    lut: str
    contrast: str
    lighting: str
    temperature: str
    rhythm: str
    particles: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


MOOD_PRESETS: dict[str, MoodPreset] = {
    MOOD_LUXURY.casefold(): MoodPreset(
        name=MOOD_LUXURY,
        lut="clean champagne film LUT with protected highlights",
        contrast="low editorial contrast with polished blacks",
        lighting="large soft key, elegant rim and controlled reflections",
        temperature="warm neutral with champagne highlights",
        rhythm="measured reveal, long tactile holds",
        particles="almost none; only refined atmospheric haze",
    ),
    MOOD_EPIC.casefold(): MoodPreset(
        name=MOOD_EPIC,
        lut="high-latitude blockbuster LUT with heroic highlight roll-off",
        contrast="high sculpted contrast with readable shadow detail",
        lighting="hard directional key, strong backlight and volumetric shafts",
        temperature="cool steel shadows with warm hero accents",
        rhythm="escalating trailer cadence with a final hold",
        particles="dust, embers or debris motivated by the scene",
    ),
    MOOD_DARK.casefold(): MoodPreset(
        name=MOOD_DARK,
        lut="noir teal-black LUT with restrained saturation",
        contrast="deep contrast, crushed edges and protected skin values",
        lighting="low practical sources, hard edge light and negative fill",
        temperature="cool nocturnal palette with sodium practical warmth",
        rhythm="patient tension, pauses before movement",
        particles="rain, smoke or glass only when the world justifies it",
    ),
    MOOD_MINIMAL.casefold(): MoodPreset(
        name=MOOD_MINIMAL,
        lut="neutral filmic LUT with honest color separation",
        contrast="balanced contrast and natural highlight roll-off",
        lighting="single motivated soft source with clean falloff",
        temperature="neutral daylight or quiet studio warmth",
        rhythm="simple visual grammar, one idea per shot",
        particles="none unless the environment already contains them",
    ),
    MOOD_SPORT.casefold(): MoodPreset(
        name=MOOD_SPORT,
        lut="punchy performance LUT with clean blacks",
        contrast="high kinetic contrast with crisp muscle definition",
        lighting="hard sidelight, sweat highlights and graphic rim light",
        temperature="cool disciplined shadows with warm skin energy",
        rhythm="fast preparation beats, impact, then a held victory frame",
        particles="chalk, dust, breath or turf particles from real action",
    ),
    MOOD_NEO.casefold(): MoodPreset(
        name=MOOD_NEO,
        lut="saturated cyan-magenta neo-city LUT",
        contrast="high neon contrast with glowing practical highlights",
        lighting="neon practicals, colored bounce and rain diffusion",
        temperature="cool blue base with magenta and cyan accents",
        rhythm="sleek synthetic pulse, drift into sudden reveals",
        particles="rain, steam and luminous haze motivated by the city",
    ),
}

MOOD_ALIASES: dict[str, str] = {
    "luxo": MOOD_LUXURY,
    "luxury": MOOD_LUXURY,
    "premium": MOOD_LUXURY,
    "epico": MOOD_EPIC,
    "épico": MOOD_EPIC,
    "epic": MOOD_EPIC,
    "heroico": MOOD_EPIC,
    "heróico": MOOD_EPIC,
    "dark": MOOD_DARK,
    "sombrio": MOOD_DARK,
    "noir": MOOD_DARK,
    "minimal": MOOD_MINIMAL,
    "minimalista": MOOD_MINIMAL,
    "clean": MOOD_MINIMAL,
    "sport": MOOD_SPORT,
    "esporte": MOOD_SPORT,
    "atleta": MOOD_SPORT,
    "performance": MOOD_SPORT,
    "neo": MOOD_NEO,
    "neon": MOOD_NEO,
    "futuro": MOOD_NEO,
    "futurista": MOOD_NEO,
    "cyber": MOOD_NEO,
}
