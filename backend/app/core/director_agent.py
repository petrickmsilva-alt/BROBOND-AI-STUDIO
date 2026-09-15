"""DirectorAgent — the conversational film director.

Responsibility: turn a plain-language intention ("Quero vender uma camiseta")
into direction — concept, script, scenes, cameras, music, pacing and duration.
The user never writes a technical prompt.

What this component deliberately does NOT do:
  * it does not compile prompt text (that is PromptCompiler's job);
  * it does not resolve styles or shot codes (StyleResolver / ShotResolver);
  * it does not read persona memory (MemoryResolver).
It emits *intent*. GenerationSpecBuilder is the composition root that combines
the four. Keeping them apart is what makes each one independently testable.

Independence: imports `contracts` only.

Determinism: no LLM is loaded and none is pretended. Rules are explicit and
reviewable; a `LanguageModel` can be injected later to enrich `concept` and
`logline` without changing this contract.
"""
from __future__ import annotations

import re

from .contracts import DirectorIntent, LanguageModel, SceneBeat

#: Narrative camera progression used when the director lays out beats:
#: establish geography, carry action, intensify, isolate the decision.
#: Grounded in knowledge_base/CINEMATIC_BIBLE.md ("Framing").
CAMERA_LADDER: tuple[str, ...] = (
    "wide establishing shot",
    "tracking medium shot",
    "low angle push-in",
    "intimate close-up",
)

#: Continuity lighting applied across an expanded sequence, preserving the
#: behaviour the storyboard endpoint had before the Core existed.
CONTINUITY_LIGHTING = "consistent blue-hour lighting across the sequence"

DEFAULT_CAMERA_LANGUAGE = "coherent camera movement"

#: ETAPA 8 bounds for a director-led storyboard.
MIN_BEATS = 4
MAX_BEATS = 8

_WORD = re.compile(r"[a-zà-öø-ÿ0-9]+", re.UNICODE)


def _words(text: str) -> set[str]:
    return set(_WORD.findall((text or "").casefold()))


class DirectorAgent:
    """Deterministic direction engine with an optional LLM enrichment hook."""

    #: Format detection. Portuguese and English are both accepted because the
    #: studio is used in both.
    #: Declaration order is only a tie-break. `detect_format` ranks by how many
    #: keywords matched, so "um fashion film editorial" resolves to `fashion`
    #: because two of its words are fashion words and only one is a film word —
    #: not because `fashion` happens to be declared first, which is what the old
    #: dict-order scan relied on.
    FORMAT_KEYWORDS: dict[str, tuple[str, ...]] = {
        "reels": ("reels", "reel", "shorts", "tiktok", "vertical", "feed"),
        "fashion": ("moda", "fashion", "lookbook", "editorial", "desfile", "roupa", "coleção", "colecao"),
        "story": ("story", "stories", "status"),
        "commercial": (
            "comercial", "vender", "venda", "produto", "camiseta", "anúncio", "anuncio",
            "campanha", "publicidade", "lançamento", "lancamento", "loja", "ecommerce",
            "e-commerce", "ad", "commercial", "sell", "product", "shop",
        ),
        # Declared before `film` on purpose: "documentário de cinema" carries both
        # vocabularies and the documentary reading is the more specific one.
        "documentary": (
            "documentário", "documentario", "documentários", "documentarios", "documentary",
            "documentaries", "documentarista", "entrevista", "entrevistas", "interview",
            "interviews", "depoimento", "depoimentos", "testemunho", "bastidores",
        ),
        "film": ("filme", "trailer", "curta", "cinema", "movie", "film", "videoclipe", "clipe"),
    }

    #: Palette/language detection, mapped onto STYLE_GUIDE.md narrative palettes.
    MOOD_KEYWORDS: dict[str, tuple[str, ...]] = {
        "luxo": ("luxo", "luxury", "premium", "elegante", "sofisticado", "champagne"),
        "futuro": ("futuro", "futurista", "neon", "cyber", "tecnologia", "future", "sci-fi", "scifi"),
        "legado": ("legado", "herança", "heranca", "tradição", "tradicao", "história", "historia", "legacy", "memória", "memoria"),
        "disciplina": ("disciplina", "treino", "esporte", "atleta", "força", "forca", "training", "sport", "workout"),
    }

    MOOD_STYLE: dict[str, str] = {
        "luxo": "luxury-fashion",
        "futuro": "neo-tokyo",
        "legado": "cinematic-realism",
        "disciplina": "imax-hero",
    }

    #: Narrative vocabulary per language. Direction speaks the user's language;
    #: camera/lighting/motion stay English because they become prompt blocks.
    NARRATIVE: dict[str, dict[str, object]] = {
        "pt": {
            # Eight distinct objectives, matching MAX_BEATS. With only four, a
            # six- or eight-beat storyboard repeated beat one verbatim — the
            # director told the same instruction twice in one sequence.
            "objectives": (
                "Estabelecer o mundo e apresentar o objeto de desejo",
                "Aproximar o espectador do detalhe que gera valor",
                "Criar a virada emocional que sustenta a decisão",
                "Fechar com a imagem que permanece na memória",
                "Reabrir o mundo por um ângulo que ainda não foi visto",
                "Isolar o gesto que resume tudo o que veio antes",
                "Sustentar o silêncio que deixa o valor assentar",
                "Devolver ao espectador a imagem que ele vai repetir",
            ),
            "emotions": (
                "curiosidade", "desejo", "tensão", "convicção",
                "reconhecimento", "intimidade", "reverência", "pertencimento",
            ),
            "music": {
                "reels": "batida eletrônica curta, corte no tempo",
                "fashion": "pulso minimalista, textura sintética elegante",
                "story": "cama atmosférica suave",
                "commercial": "percussão crescente com resolução quente",
                "film": "cordas em construção, impacto no ato final",
                "documentary": "som ambiente em primeiro plano, colchão discreto por baixo",
            },
            # `{shot}` is filled with the duration the beats actually carry. It
            # used to read a hardcoded "1.5s por plano" while every beat was
            # emitted at 5.0s — the director described a rhythm it was not
            # delivering.
            "pacing": {
                "reels": "cortes rápidos, {shot}s por plano",
                "fashion": "ritmo editorial, respiração longa",
                "story": "ritmo íntimo, um plano por ideia",
                "commercial": "aceleração progressiva até o beat do produto",
                "film": "construção em três atos",
                "documentary": "observação paciente, {shot}s por plano, corte no gesto",
            },
            "clarification": (
                "Antes de dirigir: isso é um comercial de produto, um fashion film "
                "ou um trailer? A escolha muda lente, ritmo e luz."
            ),
            "conflict": (
                "Li sua intenção como {formats}, e os dois pedem direção diferente. "
                "Qual eu dirijo? A escolha muda lente, ritmo e luz."
            ),
            "concept": {
                "commercial": "Comercial de produto com valor percebido construído por luz e escala",
                "fashion": "Fashion film editorial, materialidade e silhueta em primeiro plano",
                "reels": "Peça vertical de alto contraste feita para prender nos primeiros dois segundos",
                "story": "Peça íntima de um plano só, feita para proximidade",
                "film": "Peça cinematográfica em três atos com progressão de escala",
                "documentary": "Retrato observacional em que a verdade da cena vale mais que o enquadramento perfeito",
            },
            "logline": "Uma visão de {subject} tratada como objeto de desejo, revelada em {scenes} planos.",
            "script": (
                "Ato 1 — contexto e escala. Ato 2 — aproximação e detalhe, o valor é sentido antes de ser dito. "
                "Ato 3 — decisão, imagem final sustentada."
            ),
        },
        "en": {
            "objectives": (
                "Establish the world and introduce the object of desire",
                "Move the audience into the detail that creates value",
                "Create the emotional turn that carries the decision",
                "Close on the image that stays in memory",
                "Reopen the world from an angle nothing has shown yet",
                "Isolate the gesture that sums up everything before it",
                "Hold the silence that lets the value settle",
                "Hand back the image the audience will repeat",
            ),
            "emotions": (
                "curiosity", "desire", "tension", "conviction",
                "recognition", "intimacy", "reverence", "belonging",
            ),
            "music": {
                "reels": "short electronic pulse, cut on beat",
                "fashion": "minimal pulse, elegant synthetic texture",
                "story": "soft atmospheric bed",
                "commercial": "building percussion with a warm resolution",
                "film": "strings building into a final-act hit",
                "documentary": "room tone first, a quiet bed underneath",
            },
            "pacing": {
                "reels": "fast cuts, {shot}s per shot",
                "fashion": "editorial pace, long breathing room",
                "story": "intimate pace, one shot per idea",
                "commercial": "progressive acceleration into the product beat",
                "film": "three-act build",
                "documentary": "patient observation, {shot}s per shot, cut on the gesture",
            },
            "clarification": (
                "Before I direct this: is it a product commercial, a fashion film or a "
                "trailer? The choice changes lens, pace and light."
            ),
            "conflict": (
                "I read your intention as {formats}, and the two need different "
                "direction. Which one do I direct? The choice changes lens, pace and light."
            ),
            "concept": {
                "commercial": "Product commercial with perceived value built through light and scale",
                "fashion": "Editorial fashion film, materiality and silhouette first",
                "reels": "High-contrast vertical piece built to hook in the first two seconds",
                "story": "Intimate single-idea piece built for closeness",
                "film": "Three-act cinematic piece with a scale progression",
                "documentary": "Observational portrait where the truth of the scene outranks the perfect frame",
            },
            "logline": "A vision of {subject} treated as an object of desire, revealed across {scenes} shots.",
            "script": (
                "Act 1 — context and scale. Act 2 — approach and detail; value is felt before it is stated. "
                "Act 3 — decision, final image held."
            ),
        },
    }

    DEFAULT_LANGUAGE = "en"

    def __init__(self, llm: LanguageModel | None = None) -> None:
        self._llm = llm

    # ------------------------------------------------------------------ public

    def direct(
        self,
        intent: str,
        *,
        scene_count: int | None = None,
        style: str | None = None,
        camera_language: str | None = None,
        duration_per_scene: float = 5.0,
    ) -> DirectorIntent:
        """Direct a plain-language intention into a full brief.

        Never raises for an ambiguous intent: it returns a brief *and* a short
        clarification question, which is the behaviour SYSTEM_PROMPT.md demands
        ("faça uma pergunta curta de direção").
        """

        language = self.detect_language(intent)
        narrative = self.NARRATIVE[language]
        detected = self.detect_format(intent)
        conflict = self.detect_format_conflict(intent)
        # A tie between two formats is as undecided as no match at all: picking
        # one silently is the director guessing and not saying so.
        needs_direction = detected is None or bool(conflict)
        chosen = detected or "commercial"
        mood = self.detect_mood(intent)

        beats_count = self._clamp_scene_count(scene_count)
        camera_language = (camera_language or DEFAULT_CAMERA_LANGUAGE).strip()
        beats = self._build_beats(
            beats_count,
            objectives=narrative["objectives"],
            emotions=narrative["emotions"],
            camera_language=camera_language,
            duration_per_scene=duration_per_scene,
        )

        style_hint = style or self.MOOD_STYLE.get(mood, "cinematic-realism")
        subject = self._subject_of(intent, language)

        concepts: dict[str, str] = narrative["concept"]  # type: ignore[assignment]
        music: dict[str, str] = narrative["music"]  # type: ignore[assignment]
        pacing: dict[str, str] = narrative["pacing"]  # type: ignore[assignment]
        logline_template: str = narrative["logline"]  # type: ignore[assignment]

        return DirectorIntent(
            intent=intent.strip(),
            concept=self._enrich(concepts[chosen], intent),
            format=chosen,
            logline=logline_template.format(subject=subject, scenes=beats_count),
            script=narrative["script"],  # type: ignore[arg-type]
            beats=beats,
            camera_language=camera_language,
            lighting_language=CONTINUITY_LIGHTING,
            music=music[chosen],
            pacing=self._pacing(pacing[chosen], duration_per_scene),
            style_hint=style_hint,
            duration_seconds=round(sum(beat.duration_seconds for beat in beats), 2),
            clarification=self._clarification(narrative, conflict, needs_direction),
        )

    def expand(
        self,
        brief: str,
        *,
        scene_count: int = 4,
        persona: str | None = None,
        style: str | None = None,
        camera_language: str | None = None,
        duration_per_scene: float = 5.0,
    ) -> tuple[SceneBeat, ...]:
        """Lay a brief out as connected, independently renderable beats.

        This is the logic that used to live inside the `/storyboards/expand`
        route. Camera ladder, cycling and continuity lighting are unchanged, so
        the endpoint's output is preserved while the route stops containing
        direction logic.
        """

        language = self.detect_language(brief)
        narrative = self.NARRATIVE[language]
        return self._build_beats(
            max(1, scene_count),
            objectives=narrative["objectives"],
            emotions=narrative["emotions"],
            camera_language=(camera_language or DEFAULT_CAMERA_LANGUAGE).strip(),
            duration_per_scene=duration_per_scene,
            persona=persona,
        )

    # ---------------------------------------------------------------- detection

    #: Portuguese markers that switch the narrative vocabulary to pt-BR.
    #: Only unambiguously Portuguese tokens: "no"/"na"/"um" were excluded on
    #: purpose because they collide with common English words, and a false
    #: positive here would answer an English user in Portuguese.
    PT_MARKERS: frozenset[str] = frozenset(
        {
            "quero", "preciso", "vender", "venda", "camiseta", "produto", "não", "voce", "você",
            "está", "uma", "para", "com", "fazer", "criar", "meu", "minha", "bonito", "vídeo",
            "sobre", "esse", "essa", "muito", "de", "do", "da",
        }
    )

    @classmethod
    def detect_language(cls, text: str) -> str:
        """Very small language gate for the narrative vocabulary.

        Deliberately heuristic: it only chooses between two phrase tables. It
        is not a language detector and does not claim to be one.
        """

        return "pt" if _words(text) & cls.PT_MARKERS else cls.DEFAULT_LANGUAGE

    def detect_formats(self, intent: str) -> list[tuple[str, int]]:
        """Every format the intention matches, ranked by keyword count.

        Ranked rather than first-match: a brief usually carries more than one
        vocabulary ("um fashion film editorial" is both fashion and film), and
        which one wins should follow from the brief, not from the order the
        dictionary happens to be written in. Ties keep declaration order, which
        is a documented rule instead of an accident.
        """

        found = _words(intent)
        ranked = [
            (fmt, len(found & set(keywords)))
            for fmt, keywords in self.FORMAT_KEYWORDS.items()
        ]
        ranked = [(fmt, count) for fmt, count in ranked if count]
        # `sorted` is stable, so equal counts keep declaration order.
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    def detect_format(self, intent: str) -> str | None:
        ranked = self.detect_formats(intent)
        return ranked[0][0] if ranked else None

    def detect_format_conflict(self, intent: str) -> tuple[str, ...]:
        """Formats tied for first place — the genuinely ambiguous case.

        Empty whenever the brief leans one way, which is the common case: the
        director only asks a question when the answer is actually undecided.
        """

        ranked = self.detect_formats(intent)
        if len(ranked) < 2:
            return ()
        top = ranked[0][1]
        tied = tuple(fmt for fmt, count in ranked if count == top)
        return tied if len(tied) > 1 else ()

    def detect_mood(self, intent: str) -> str | None:
        found = _words(intent)
        for mood, keywords in self.MOOD_KEYWORDS.items():
            if found & set(keywords):
                return mood
        return None

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _pacing(template: str, duration_per_scene: float) -> str:
        """State the rhythm with the duration the beats actually carry.

        A pacing line that names a shot length has to name the real one. The
        reels line used to promise 1.5s while every beat was emitted at 5.0s.
        """

        return template.replace("{shot}", f"{duration_per_scene:g}")

    @staticmethod
    def _clarification(narrative: dict, conflict: tuple[str, ...], needs_direction: bool) -> str:
        """Empty when the director is confident; one short question otherwise.

        A tie names the two candidates instead of asking the generic question,
        because "is it a commercial or a trailer" is the wrong question when the
        brief already said both.
        """

        if not needs_direction:
            return ""
        if conflict:
            joined = " e ".join(conflict) if len(conflict) == 2 else ", ".join(conflict)
            return str(narrative["conflict"]).format(formats=joined)
        return str(narrative["clarification"])

    def _build_beats(
        self,
        scene_count: int,
        *,
        objectives: tuple[str, ...] | list[str],
        emotions: tuple[str, ...] | list[str],
        camera_language: str,
        duration_per_scene: float,
        persona: str | None = None,
    ) -> tuple[SceneBeat, ...]:
        beats: list[SceneBeat] = []
        for index in range(1, scene_count + 1):
            position = (index - 1) % len(CAMERA_LADDER)
            beats.append(
                SceneBeat(
                    number=index,
                    objective=objectives[(index - 1) % len(objectives)],
                    emotion=emotions[(index - 1) % len(emotions)],
                    camera=f"{CAMERA_LADDER[position]}, {camera_language}",
                    lighting=CONTINUITY_LIGHTING,
                    motion="motivated by the beat" if position else "reveal",
                    duration_seconds=duration_per_scene,
                    reference=persona or "",
                )
            )
        return tuple(beats)

    @staticmethod
    def _clamp_scene_count(scene_count: int | None) -> int:
        if scene_count is None:
            return MIN_BEATS
        return max(MIN_BEATS, min(MAX_BEATS, scene_count))

    #: Leading intent verbs stripped before building the logline, so the
    #: director talks about the subject instead of echoing the request.
    INTENT_PREFIXES: tuple[str, ...] = (
        "quero", "queria", "preciso", "gostaria de", "gostaria", "pode", "podes", "faça", "faca",
        "criar", "crie", "fazer", "faça-me", "me faz", "i want to", "i want", "i need to", "i need",
        "please", "can you", "could you", "make me", "make", "create", "build", "generate",
    )

    @classmethod
    def _subject_of(cls, intent: str, language: str) -> str:
        """Short subject phrase for the logline, from the user's own words."""

        cleaned = re.sub(r"\s+", " ", (intent or "").strip()).rstrip(".!?")
        if not cleaned:
            return "the subject"
        lowered = cleaned.casefold()
        for prefix in sorted(cls.INTENT_PREFIXES, key=len, reverse=True):
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix) :].lstrip(" ,:-").strip()
                break
        if not cleaned:
            return "the subject"
        return cleaned if len(cleaned) <= 90 else cleaned[:87].rsplit(" ", 1)[0] + "..."

    def _enrich(self, concept: str, intent: str) -> str:
        """Optional LLM enrichment. Falls back to the deterministic concept.

        A failure in the injected model must never break direction, so any
        exception degrades silently to the rule-based answer.
        """

        if self._llm is None:
            return concept
        try:
            enriched = self._llm.complete(
                instruction="Refine this film concept into one precise sentence.",
                context=f"{concept}\nIntention: {intent}",
            ).strip()
        except Exception:
            return concept
        return enriched or concept
