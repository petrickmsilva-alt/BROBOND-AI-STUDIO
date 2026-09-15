"""DirectorAgent: the user states an intention, the director returns direction."""
import pytest

from app.core.contracts import LanguageModel
from app.core.director_agent import (
    CAMERA_LADDER,
    CONTINUITY_LIGHTING,
    MAX_BEATS,
    MIN_BEATS,
    DirectorAgent,
)


@pytest.fixture()
def director() -> DirectorAgent:
    return DirectorAgent()


def test_a_plain_sales_intention_becomes_a_commercial(director: DirectorAgent) -> None:
    brief = director.direct("Quero vender uma camiseta")
    assert brief.format == "commercial"
    assert brief.concept
    assert brief.script
    assert brief.music
    assert brief.pacing
    assert brief.duration_seconds > 0


def test_the_director_never_returns_a_technical_prompt(director: DirectorAgent) -> None:
    brief = director.direct("Quero vender uma camiseta")
    payload = brief.to_dict()
    assert "prompt" not in payload
    assert "prompt_compiled" not in payload
    for beat in payload["beats"]:
        assert "prompt" not in beat


def test_the_brief_contains_concept_script_scenes_cameras_music_and_duration(director: DirectorAgent) -> None:
    brief = director.direct("Quero vender uma camiseta")
    assert brief.concept and brief.logline and brief.script
    assert brief.scene_count >= MIN_BEATS
    assert all(beat.camera for beat in brief.beats)
    assert brief.music and brief.duration_seconds == pytest.approx(sum(b.duration_seconds for b in brief.beats))


def test_scene_count_stays_inside_the_directed_range(director: DirectorAgent) -> None:
    assert director.direct("trailer").scene_count == MIN_BEATS
    assert director.direct("trailer", scene_count=99).scene_count == MAX_BEATS
    assert director.direct("trailer", scene_count=1).scene_count == MIN_BEATS
    assert director.direct("trailer", scene_count=6).scene_count == 6


def test_each_detected_format_has_its_own_language(director: DirectorAgent) -> None:
    assert director.direct("quero um reels vertical").format == "reels"
    assert director.direct("um fashion film editorial").format == "fashion"
    assert director.direct("um story curto").format == "story"
    assert director.direct("um trailer de cinema").format == "film"


def test_mood_maps_onto_the_style_guide_palettes(director: DirectorAgent) -> None:
    assert director.direct("campanha de luxo").style_hint == "luxury-fashion"
    assert director.direct("vídeo futurista neon").style_hint == "neo-tokyo"
    assert director.direct("comercial de treino e disciplina").style_hint == "imax-hero"


def test_an_explicit_style_wins_over_the_detected_mood(director: DirectorAgent) -> None:
    assert director.direct("campanha de luxo", style="john-wick").style_hint == "john-wick"


def test_an_ambiguous_intention_produces_one_short_question(director: DirectorAgent) -> None:
    brief = director.direct("algo legal")
    assert brief.needs_direction is True
    assert brief.clarification
    # A question, not a paragraph.
    assert len(brief.clarification) < 200


def test_a_clear_intention_does_not_ask_anything(director: DirectorAgent) -> None:
    assert director.direct("Quero vender uma camiseta").clarification == ""
    assert director.direct("Quero vender uma camiseta").needs_direction is False


def test_expand_preserves_the_storyboard_camera_ladder(director: DirectorAgent) -> None:
    """This is the behaviour that used to live inside the HTTP route."""

    beats = director.expand("A man walking through a future city", scene_count=4)
    assert len(beats) == 4
    assert beats[0].camera.startswith(CAMERA_LADDER[0])
    assert "wide establishing shot" in beats[0].camera
    assert all(beat.lighting == CONTINUITY_LIGHTING for beat in beats)
    assert all(beat.duration_seconds == 5.0 for beat in beats)


def test_expand_cycles_the_ladder_for_longer_sequences(director: DirectorAgent) -> None:
    beats = director.expand("a long sequence", scene_count=6)
    assert beats[4].camera.startswith(CAMERA_LADDER[0])
    assert len({beat.camera for beat in beats}) == len(CAMERA_LADDER)


def test_expand_carries_objective_emotion_and_reference(director: DirectorAgent) -> None:
    beats = director.expand("a brief", scene_count=4, persona="Petrick Martins")
    assert all(beat.objective and beat.emotion for beat in beats)
    assert all(beat.reference == "Petrick Martins" for beat in beats)
    assert [beat.number for beat in beats] == [1, 2, 3, 4]


def test_expand_honours_a_custom_camera_language(director: DirectorAgent) -> None:
    beats = director.expand("a brief", scene_count=2, camera_language="handheld documentary")
    assert all("handheld documentary" in beat.camera for beat in beats)


def test_portuguese_intentions_are_answered_in_portuguese(director: DirectorAgent) -> None:
    assert director.detect_language("Quero vender uma camiseta") == "pt"
    assert director.direct("Quero vender uma camiseta").beats[0].objective.startswith("Estabelecer")


def test_english_intentions_are_answered_in_english(director: DirectorAgent) -> None:
    assert director.detect_language("A man walking through a future city") == "en"
    assert director.direct("product commercial for shoes").beats[0].objective.startswith("Establish")


def test_english_is_not_mistaken_for_portuguese(director: DirectorAgent) -> None:
    for text in ("no budget product ad", "make a film about us", "one minute trailer"):
        assert director.detect_language(text) == "en", text


def test_an_injected_language_model_enriches_the_concept() -> None:
    class EchoModel:
        def complete(self, instruction: str, context: str) -> str:
            return "refined concept"

    assert DirectorAgent(llm=EchoModel()).direct("trailer").concept == "refined concept"


def test_a_failing_language_model_never_breaks_direction() -> None:
    class BrokenModel:
        def complete(self, instruction: str, context: str) -> str:
            raise RuntimeError("provider down")

    brief = DirectorAgent(llm=BrokenModel()).direct("trailer")
    assert brief.concept, "direction must survive an LLM failure"


def test_an_empty_language_model_answer_falls_back() -> None:
    class SilentModel:
        def complete(self, instruction: str, context: str) -> str:
            return "   "

    assert DirectorAgent(llm=SilentModel()).direct("trailer").concept


def test_the_language_model_hook_is_a_protocol() -> None:
    class Model:
        def complete(self, instruction: str, context: str) -> str:
            return "x"

    assert isinstance(Model(), LanguageModel)


def test_a_long_intention_is_shortened_in_the_logline(director: DirectorAgent) -> None:
    brief = director.direct("comercial " + "muito longo " * 40)
    assert len(brief.logline) < 200


# ---------------------------------------------------------------------------
# ETAPA 7 — the documentary arc, format ranking, honest pacing, eight beats
# ---------------------------------------------------------------------------


def test_documentary_is_its_own_format_in_both_languages(director: DirectorAgent) -> None:
    """It used to be folded into `film` (pt) or missed entirely (en)."""

    assert director.detect_format("documentário sobre artesãos locais") == "documentary"
    assert director.detect_format("a documentary about local artisans") == "documentary"
    assert director.detect_format("entrevista com o fundador") == "documentary"
    assert director.detect_format("interview with the founder") == "documentary"


def test_documentary_does_not_steal_a_film(director: DirectorAgent) -> None:
    assert director.detect_format("um trailer de cinema") == "film"
    assert director.detect_format("um curta de ficção") == "film"
    assert director.detect_format("a short movie") == "film"


def test_documentary_wins_when_both_vocabularies_appear(director: DirectorAgent) -> None:
    """Declared before `film` and more specific: two documentary words, one film."""

    assert director.detect_format("um documentário de cinema") == "documentary"


def test_a_documentary_brief_is_directed_without_a_question(director: DirectorAgent) -> None:
    brief = director.direct("a documentary about a small farm")
    assert brief.format == "documentary"
    assert brief.clarification == ""
    assert brief.concept and brief.music and brief.pacing


def test_format_choice_follows_specificity_not_declaration_order(
    director: DirectorAgent,
) -> None:
    """`fashion` and `film` both match; two fashion words beat one film word.

    Before ETAPA 7 the same answer came out of dictionary order, which is an
    accident of how the table was written rather than a reading of the brief.
    """

    assert director.detect_formats("um fashion film editorial") == [("fashion", 2), ("film", 1)]
    assert director.detect_format("um fashion film editorial") == "fashion"


def test_specificity_overrides_declaration_order(director: DirectorAgent) -> None:
    """The case that separates the two rules.

    "reels" is declared first, so a first-match scan returns `reels` on the
    strength of one word while ignoring three commercial ones. Ranking by count
    reads the brief instead of the table. Reverting `detect_format` to a
    first-match scan fails here, which is what makes the rule enforceable.
    """

    assert director.detect_formats("reels para vender meu produto na loja") == [
        ("commercial", 3),
        ("reels", 1),
    ]
    assert director.detect_format("reels para vender meu produto na loja") == "commercial"
    assert director.detect_format("reels sobre a coleção de moda") == "fashion"
    assert director.detect_format("story para vender produto na loja") == "commercial"


def test_detect_formats_ranks_every_match(director: DirectorAgent) -> None:
    ranked = director.detect_formats("reels vertical para vender meu produto")
    assert ranked[0][0] == "reels"
    assert all(count > 0 for _, count in ranked)
    counts = [count for _, count in ranked]
    assert counts == sorted(counts, reverse=True)


def test_an_unmatched_brief_still_matches_nothing(director: DirectorAgent) -> None:
    assert director.detect_formats("A man walking through a future city") == []
    assert director.detect_format("A man walking through a future city") is None


def test_a_clear_brief_reports_no_conflict(director: DirectorAgent) -> None:
    assert director.detect_format_conflict("Quero vender uma camiseta") == ()
    assert director.detect_format_conflict("quero um reels vertical") == ()
    assert director.detect_format_conflict("um fashion film editorial") == ()


def test_a_genuine_tie_is_said_out_loud(director: DirectorAgent) -> None:
    """One fashion word and one story word is undecided, not a coin flip."""

    assert director.detect_format_conflict("fashion story") == ("fashion", "story")
    brief = director.direct("fashion story")
    assert brief.needs_direction is True
    assert "fashion" in brief.clarification and "story" in brief.clarification
    assert len(brief.clarification) < 200


def test_a_conflict_question_is_asked_in_the_users_language(
    director: DirectorAgent,
) -> None:
    assert "e " in director.direct("reels de moda").clarification
    assert " and " in director.direct("fashion story for the shop").clarification


def test_pacing_states_the_duration_the_beats_actually_carry(
    director: DirectorAgent,
) -> None:
    """The reels line promised 1.5s per shot while emitting 5.0s beats."""

    brief = director.direct("quero um reels vertical")
    assert all(beat.duration_seconds == 5.0 for beat in brief.beats)
    assert "5s por plano" in brief.pacing
    assert "1.5" not in brief.pacing


def test_pacing_follows_a_requested_duration(director: DirectorAgent) -> None:
    brief = director.direct("quero um reels vertical", duration_per_scene=1.5)
    assert all(beat.duration_seconds == 1.5 for beat in brief.beats)
    assert "1.5s por plano" in brief.pacing


def test_no_pacing_line_contradicts_its_own_beats(director: DirectorAgent) -> None:
    """Any pacing string that names a shot length must name the real one."""

    import re

    for language in ("pt", "en"):
        for fmt, template in director.NARRATIVE[language]["pacing"].items():
            for seconds in (1.5, 3.0, 5.0):
                brief = director.direct(
                    {"commercial": "produto", "fashion": "moda", "reels": "reels",
                     "story": "story", "film": "trailer", "documentary": "documentário"}[fmt],
                    duration_per_scene=seconds,
                )
                stated = re.findall(r"(\d+(?:[.,]\d+)?)s (?:por plano|per shot)", brief.pacing)
                assert all(float(s.replace(",", ".")) == seconds for s in stated), (
                    language, fmt, brief.pacing
                )


def test_every_format_is_directable_in_both_languages(director: DirectorAgent) -> None:
    for language in ("pt", "en"):
        narrative = director.NARRATIVE[language]
        for fmt in director.FORMAT_KEYWORDS:
            assert narrative["concept"][fmt], (language, fmt)
            assert narrative["music"][fmt], (language, fmt)
            assert narrative["pacing"][fmt], (language, fmt)


def test_eight_beats_carry_eight_distinct_objectives(director: DirectorAgent) -> None:
    """With four objectives, beats 5-8 repeated beats 1-4 word for word."""

    beats = director.direct("Quero vender uma camiseta", scene_count=MAX_BEATS).beats
    assert len(beats) == MAX_BEATS == 8
    assert len({beat.objective for beat in beats}) == MAX_BEATS
    assert len({beat.emotion for beat in beats}) == MAX_BEATS
    assert beats[4].objective != beats[0].objective


def test_the_first_objective_is_unchanged(director: DirectorAgent) -> None:
    """Pinned by the API tests: the sequence still opens the same way."""

    assert director.direct("Quero vender uma camiseta").beats[0].objective.startswith("Estabelecer")
    assert director.direct("product commercial").beats[0].objective.startswith("Establish")


def test_the_camera_ladder_still_cycles_at_four(director: DirectorAgent) -> None:
    """Deliberately unchanged: the ladder is a pinned visual grammar."""

    beats = director.direct("Quero vender uma camiseta", scene_count=MAX_BEATS).beats
    assert beats[4].camera == beats[0].camera
    assert len({beat.camera for beat in beats}) == len(CAMERA_LADDER)


def test_an_intent_that_is_only_a_verb_falls_back_to_a_generic_subject(
    director: DirectorAgent,
) -> None:
    """Stripping the intent verb must not leave an empty logline."""

    assert director._subject_of("quero", "pt") == "the subject"
    assert director._subject_of("i want to", "en") == "the subject"
    assert "the subject" in director.direct("quero").logline


def test_a_blank_intent_falls_back_too(director: DirectorAgent) -> None:
    assert director._subject_of("   ", "pt") == "the subject"
    assert director._subject_of("", "en") == "the subject"
