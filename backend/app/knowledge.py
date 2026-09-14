"""BROBOND CORE knowledge resolver and seed catalog."""
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import KnowledgeEntry


@dataclass(frozen=True)
class KnowledgeSeed:
    category: str
    code: str
    title: str
    content: str


SEEDS = [
    KnowledgeSeed("cinematic", "LENS_85", "85mm portrait", "Luxury portrait compression, shallow depth of field, subject separation."),
    KnowledgeSeed("cinematic", "LIGHT_BLUE_HOUR", "Blue hour", "Consistent blue-hour ambience, soft volumetric light, teal and amber restraint."),
    KnowledgeSeed("style", "BROBOND_CORE", "BROBOND identity", "Black premium workspace, violet technology accent, warm cinematic highlights."),
    KnowledgeSeed("character", "CHAR_PETRICK", "Petrick Martins", "50 years, 1.85m, athletic build, short beard, tied hair, dark brown eyes, cinematic realism."),
    KnowledgeSeed("character", "CHAR_JEFFERSON", "Jefferson", "Planned character. Identity requires approval before training or generation."),
    KnowledgeSeed("shot", "SH001", "Hero Walk", "50mm, low-angle tracking, confident forward motion."),
    KnowledgeSeed("shot", "SH014", "Close Eyes", "85mm intimate close-up, shallow depth, slow push-in."),
    KnowledgeSeed("shot", "SH032", "Drone Reveal", "24mm aerial establishing, crane reveal, geographic scale."),
    KnowledgeSeed("shot", "SH051", "Orbit 360", "35mm orbit, subject locked, parallax reveal."),
    KnowledgeSeed("shot", "SH120", "Luxury Entrance", "35mm dolly-in, symmetrical architecture, warm practicals."),
    KnowledgeSeed("prompt", "PROMPT_LUXURY", "Luxury", "Architectural scale, quiet confidence, black and champagne palette, polished surfaces."),
    KnowledgeSeed("prompt", "PROMPT_LEGACY", "Legacy", "Warm side light, tactile materials, measured pace, emotional restraint."),
]


def seed_knowledge(db: Session) -> None:
    for seed in SEEDS:
        if not db.scalar(select(KnowledgeEntry).where(KnowledgeEntry.code == seed.code)):
            db.add(KnowledgeEntry(category=seed.category, code=seed.code, title=seed.title, content=seed.content, source="core-seed", version=1))
    db.commit()


def resolve(db: Session, query: str | None = None, category: str | None = None) -> list[KnowledgeEntry]:
    statement = select(KnowledgeEntry).order_by(KnowledgeEntry.category, KnowledgeEntry.code)
    if category:
        statement = statement.where(KnowledgeEntry.category == category)
    if query:
        pattern = f"%{query}%"
        statement = statement.where((KnowledgeEntry.code.ilike(pattern)) | (KnowledgeEntry.title.ilike(pattern)) | (KnowledgeEntry.content.ilike(pattern)))
    return list(db.scalars(statement).all())
