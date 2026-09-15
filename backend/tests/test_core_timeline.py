"""ETAPA 13 tests — the video timeline: assembling a cast sequence into one cut.

Before this etapa the studio could direct a multi-scene storyboard and generate
each scene, but nothing put them back together: `FFmpegService` had a
single-source `export_h264`, no concatenation existed anywhere in the repository,
and `probe` handed back ffprobe's JSON unparsed with zero callers. A five-scene
storyboard produced five orphan files.

The FFmpeg binary is not installed in this sandbox, so the parts that shell out
are verified through the pure argument builders (`probe_fields`,
`concat_command`) and through the guard that runs before any subprocess. What
cannot be executed here is named as such rather than asserted through a stub
that only proves the stub.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.core.contracts import DirectorIntent
from app.core.storyboard_engine import ARC_BY_FORMAT, DEFAULT_ARC, StoryboardEngine
from app.core.timeline import (
    ASPECT_BY_FORMAT,
    CUT,
    DEFAULT_ASPECT_RATIO,
    DEFAULT_FPS,
    DEFAULT_RESOLUTION,
    DISSOLVE,
    MIN_CLIP_SECONDS,
    RESOLUTIONS,
    TRANSITIONS,
    AudioTrack,
    Clip,
    Timeline,
    VideoTimeline,
)
from app.core import CinematicLibrary, DirectorAgent, ShotLibrary


@pytest.fixture()
def timeline_engine() -> VideoTimeline:
    return VideoTimeline()


@pytest.fixture()
def storyboard():
    engine = StoryboardEngine(
        director=DirectorAgent(), shots=ShotLibrary(), grammar=CinematicLibrary()
    )
    return engine.build("Quero um comercial de 30 segundos para uma camiseta artesanal.", scene_count=5)


def _clip(index: int, start: float, duration: float, **kwargs) -> Clip:
    return Clip(
        index=index,
        shot_code=kwargs.pop("shot_code", f"SH{index:03d}"),
        family=kwargs.pop("family", "action"),
        start_seconds=start,
        duration_seconds=duration,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Clip arithmetic
# ---------------------------------------------------------------------------


def test_a_clip_knows_where_it_ends() -> None:
    clip = _clip(1, 2.5, 3.0)
    assert clip.end_seconds == 5.5


def test_end_points_do_not_drift_on_floats() -> None:
    clip = _clip(1, 0.1, 0.2)
    assert clip.end_seconds == 0.3, "0.1 + 0.2 must not surface as 0.30000000000000004"


def test_a_clip_without_a_source_is_not_rendered() -> None:
    assert _clip(1, 0.0, 5.0).is_rendered is False
    assert _clip(1, 0.0, 5.0, source="ws/a.mp4").is_rendered is True


# ---------------------------------------------------------------------------
# Delivery geometry
# ---------------------------------------------------------------------------


def test_vertical_formats_ship_vertical(timeline_engine: VideoTimeline) -> None:
    assert timeline_engine.aspect_for("reels") == "9:16"
    assert timeline_engine.aspect_for("story") == "9:16"


def test_the_other_formats_ship_wide(timeline_engine: VideoTimeline) -> None:
    for name in ("fashion", "commercial", "film", "documentary"):
        assert timeline_engine.aspect_for(name) == "16:9", name


def test_an_unknown_format_falls_back_to_the_default(timeline_engine: VideoTimeline) -> None:
    assert timeline_engine.aspect_for("opera") == DEFAULT_ASPECT_RATIO


def test_every_directed_format_has_a_declared_aspect() -> None:
    assert set(ASPECT_BY_FORMAT) == set(ARC_BY_FORMAT), (
        "a format the Director can emit must have a delivery frame"
    )


def test_the_delivery_box_is_swapped_for_vertical() -> None:
    wide = Timeline(format="film", clips=(), resolution="1080p")
    tall = Timeline(format="reels", clips=(), aspect_ratio="9:16", resolution="1080p")
    assert (wide.width, wide.height) == (1920, 1080)
    assert (tall.width, tall.height) == (1080, 1920)


def test_the_resolution_table_matches_the_export_adapter() -> None:
    """A timeline and an FFmpeg export must agree on what 1080p means."""

    from app.media import QUALITY

    for name, (width, height) in RESOLUTIONS.items():
        assert QUALITY[name][:2] == (width, height), name


def test_an_unknown_resolution_falls_back_to_the_default_box() -> None:
    odd = Timeline(format="film", clips=(), resolution="8k")
    assert (odd.width, odd.height) == RESOLUTIONS[DEFAULT_RESOLUTION]


# ---------------------------------------------------------------------------
# Duration is derived, not summed
# ---------------------------------------------------------------------------


def test_an_empty_timeline_has_no_duration() -> None:
    assert Timeline(format="film", clips=()).duration_seconds == 0.0


def test_duration_comes_from_the_last_clip(timeline_engine: VideoTimeline, storyboard) -> None:
    timeline = timeline_engine.from_storyboard(storyboard)
    assert timeline.duration_seconds == timeline.clips[-1].end_seconds
    assert timeline.duration_seconds == pytest.approx(25.0)


def test_duration_matches_the_storyboard_runtime(timeline_engine: VideoTimeline, storyboard) -> None:
    assert timeline_engine.from_storyboard(storyboard).duration_seconds == pytest.approx(
        storyboard.runtime_seconds
    )


def test_a_gap_is_visible_in_the_number_rather_than_absorbed() -> None:
    """Summing durations would hide a hole in the middle of the cut."""

    cut = Timeline(format="film", clips=(_clip(1, 0.0, 5.0), _clip(2, 8.0, 5.0)))
    assert cut.duration_seconds == 13.0
    assert sum(clip.duration_seconds for clip in cut.clips) == 10.0


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


def test_the_first_clip_always_cuts(timeline_engine: VideoTimeline) -> None:
    assert timeline_engine.transition_for("action", None) == CUT


def test_a_change_of_family_takes_the_cut(timeline_engine: VideoTimeline) -> None:
    assert timeline_engine.transition_for("tension", "action") == CUT


def test_continuing_one_family_dissolves(timeline_engine: VideoTimeline) -> None:
    assert timeline_engine.transition_for("product", "product") == DISSOLVE


def test_an_unnamed_family_never_dissolves(timeline_engine: VideoTimeline) -> None:
    """Two shots with no family are not 'the same idea'."""

    assert timeline_engine.transition_for("", "") == CUT


def test_a_dissolve_appears_exactly_where_a_family_repeats(
    timeline_engine: VideoTimeline,
) -> None:
    """Guards against the rule being dead code, and against it firing anywhere.

    The first draft dissolved on `StoryboardEngine.TRANSITION_FAMILIES`, which no
    arc ever casts — the intersection is empty, so a dissolve could never have
    been emitted. Five of the seven arcs do repeat a family and must dissolve
    there; `film` and the default arc change idea every beat and must stay all
    cuts, which is the other half of the same rule.
    """

    dissolving = {"commercial", "fashion", "reels", "story", "documentary"}
    for name, arc in list(ARC_BY_FORMAT.items()) + [("default", DEFAULT_ARC)]:
        transitions = [
            timeline_engine.transition_for(family, arc[index - 1] if index else None)
            for index, family in enumerate(arc)
        ]
        expected = DISSOLVE if name in dissolving else CUT
        for index, (family, transition) in enumerate(zip(arc, transitions)):
            same_as_previous = index > 0 and family == arc[index - 1]
            assert transition == (DISSOLVE if same_as_previous else CUT), (name, index)
        assert (DISSOLVE in transitions) is (name in dissolving), name
        assert expected in (CUT, DISSOLVE)


def test_five_of_the_seven_arcs_reach_a_dissolve() -> None:
    """The concrete count, so a future arc change cannot silently kill the rule."""

    engine = VideoTimeline()
    reaching = [
        name
        for name, arc in list(ARC_BY_FORMAT.items()) + [("default", DEFAULT_ARC)]
        if any(
            engine.transition_for(family, arc[index - 1] if index else None) == DISSOLVE
            for index, family in enumerate(arc)
        )
    ]
    assert len(reaching) == 5
    assert "documentary" in reaching


def test_a_bridging_family_is_not_what_triggers_a_dissolve() -> None:
    """Pins the finding: those families exist in the library but no arc casts them."""

    families = {family for arc in list(ARC_BY_FORMAT.values()) + [DEFAULT_ARC] for family in arc}
    assert not families & {"transition", "atmosphere"}


def test_assembled_transitions_follow_the_families(timeline_engine: VideoTimeline) -> None:
    engine = StoryboardEngine(
        director=DirectorAgent(), shots=ShotLibrary(), grammar=CinematicLibrary()
    )
    board = engine.build("comercial de produto", scene_count=5)
    timeline = timeline_engine.from_storyboard(board)
    for previous, current in zip(timeline.clips, timeline.clips[1:]):
        expected = DISSOLVE if current.family == previous.family else CUT
        assert current.transition == expected
    assert timeline.clips[0].transition == CUT


def test_the_transition_vocabulary_is_closed() -> None:
    assert TRANSITIONS == (CUT, DISSOLVE)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def test_clips_are_laid_end_to_end(timeline_engine: VideoTimeline, storyboard) -> None:
    timeline = timeline_engine.from_storyboard(storyboard)
    for previous, current in zip(timeline.clips, timeline.clips[1:]):
        assert current.start_seconds == previous.end_seconds


def test_clip_indexes_are_one_based_and_sequential(
    timeline_engine: VideoTimeline, storyboard
) -> None:
    assert [clip.index for clip in timeline_engine.from_storyboard(storyboard).clips] == [1, 2, 3, 4, 5]


def test_sources_are_matched_by_scene_number(timeline_engine: VideoTimeline, storyboard) -> None:
    timeline = timeline_engine.from_storyboard(storyboard, sources={1: "ws/a.mp4", 3: "ws/c.mp4"})
    assert timeline.clips[0].source == "ws/a.mp4"
    assert timeline.clips[1].source == ""
    assert timeline.clips[2].source == "ws/c.mp4"
    assert timeline.rendered_clips == (timeline.clips[0], timeline.clips[2])
    assert [clip.index for clip in timeline.unrendered_clips] == [2, 4, 5]


def test_a_timeline_with_every_source_is_complete(timeline_engine: VideoTimeline, storyboard) -> None:
    sources = {shot.number: f"ws/{shot.number}.mp4" for shot in storyboard.shots}
    assert timeline_engine.from_storyboard(storyboard, sources=sources).is_complete is True


def test_a_timeline_missing_one_source_is_not_complete(
    timeline_engine: VideoTimeline, storyboard
) -> None:
    sources = {shot.number: f"ws/{shot.number}.mp4" for shot in storyboard.shots[:-1]}
    assert timeline_engine.from_storyboard(storyboard, sources=sources).is_complete is False


def test_an_empty_source_string_does_not_count_as_rendered(
    timeline_engine: VideoTimeline, storyboard
) -> None:
    timeline = timeline_engine.from_storyboard(storyboard, sources={1: ""})
    assert timeline.rendered_clips == ()


def test_the_music_bed_is_the_directors_own_language(timeline_engine: VideoTimeline) -> None:
    """Nothing here invents a soundtrack; it carries what the Director said."""

    intent = DirectorAgent().direct("Quero vender uma camiseta")
    timeline = timeline_engine.from_storyboard(
        StoryboardEngine(
            director=DirectorAgent(), shots=ShotLibrary(), grammar=CinematicLibrary()
        ).build("Quero vender uma camiseta", scene_count=4),
        intent=intent,
    )
    assert timeline.audio.bed == intent.music
    assert timeline.audio.is_declared is True


def test_without_an_intent_there_is_no_music_and_it_says_so(
    timeline_engine: VideoTimeline, storyboard
) -> None:
    timeline = timeline_engine.from_storyboard(storyboard)
    assert timeline.audio.bed == ""
    assert timeline.audio.is_declared is False


def test_assemble_accepts_anything_shaped_like_a_shot(timeline_engine: VideoTimeline) -> None:
    class Bare:
        number = 1
        shot_code = "SH001"
        family = "action"
        duration_seconds = 2.0

    timeline = timeline_engine.assemble([Bare(), Bare()], format_name="film")
    assert timeline.clip_count == 2
    assert timeline.duration_seconds == 4.0


def test_a_negative_duration_is_clamped_to_zero(timeline_engine: VideoTimeline) -> None:
    class Broken:
        number = 1
        shot_code = "SH001"
        family = "action"
        duration_seconds = -3.0

    timeline = timeline_engine.assemble([Broken()], format_name="film")
    assert timeline.clips[0].duration_seconds == 0.0


def test_resolution_and_fps_pass_through(timeline_engine: VideoTimeline, storyboard) -> None:
    timeline = timeline_engine.from_storyboard(storyboard, resolution="4k", fps=30)
    assert timeline.resolution == "4k"
    assert timeline.fps == 30
    assert (timeline.width, timeline.height) == (3840, 2160)


# ---------------------------------------------------------------------------
# Validation — a report, never a crash
# ---------------------------------------------------------------------------


def test_an_empty_timeline_is_a_violation(timeline_engine: VideoTimeline) -> None:
    report = timeline_engine.validate(Timeline(format="film", clips=()))
    assert report["valid"] is False
    assert {f["rule"] for f in report["violations"]} == {"empty-timeline"}


def test_a_clean_fully_rendered_cut_passes(timeline_engine: VideoTimeline, storyboard) -> None:
    sources = {shot.number: f"ws/{shot.number}.mp4" for shot in storyboard.shots}
    intent = DirectorAgent().direct(storyboard.brief)
    timeline = timeline_engine.from_storyboard(storyboard, intent=intent, sources=sources)
    report = timeline_engine.validate(timeline)
    assert report["valid"] is True
    assert report["violations"] == []
    assert report["warnings"] == []


def test_an_overlong_cut_is_reported_against_the_same_ceiling_as_the_storyboard() -> None:
    engine = VideoTimeline(max_runtime_seconds=180.0)
    clips = tuple(_clip(index, index * 60.0, 60.0) for index in range(1, 5))
    report = engine.validate(Timeline(format="film", clips=clips))
    assert any(f["rule"] == "runtime" for f in report["violations"])
    assert "180.0s ceiling" in next(f for f in report["violations"] if f["rule"] == "runtime")["detail"]


def test_the_ceiling_matches_the_storyboard_engines() -> None:
    from app.core.storyboard_engine import MAX_RUNTIME_SECONDS

    assert VideoTimeline().max_runtime_seconds == MAX_RUNTIME_SECONDS


def test_a_flash_frame_is_a_violation(timeline_engine: VideoTimeline) -> None:
    report = timeline_engine.validate(
        Timeline(format="film", clips=(_clip(1, 0.0, MIN_CLIP_SECONDS / 2),))
    )
    assert any(f["rule"] == "clip-duration" for f in report["violations"])


def test_overlapping_clips_are_a_violation(timeline_engine: VideoTimeline) -> None:
    report = timeline_engine.validate(
        Timeline(format="film", clips=(_clip(1, 0.0, 5.0), _clip(2, 3.0, 5.0)))
    )
    assert any(f["rule"] == "overlap" for f in report["violations"])


def test_a_hole_is_a_warning_not_a_crash(timeline_engine: VideoTimeline) -> None:
    report = timeline_engine.validate(
        Timeline(format="film", clips=(_clip(1, 0.0, 5.0), _clip(2, 9.0, 5.0)))
    )
    gaps = [f for f in report["warnings"] if f["rule"] == "gap"]
    assert gaps and gaps[0]["status"] == "warning"
    assert "4.0s of black" in gaps[0]["detail"]


def test_an_unrendered_clip_is_a_warning_that_never_passes_silently(
    timeline_engine: VideoTimeline, storyboard
) -> None:
    report = timeline_engine.validate(timeline_engine.from_storyboard(storyboard))
    assert len([f for f in report["warnings"] if f["rule"] == "unrendered-clip"]) == 5
    assert report["unrendered"] == 5
    assert report["rendered"] == 0


def test_missing_music_is_reported(timeline_engine: VideoTimeline, storyboard) -> None:
    report = timeline_engine.validate(timeline_engine.from_storyboard(storyboard))
    assert any(f["rule"] == "no-audio-bed" for f in report["warnings"])


def test_a_fade_longer_than_the_cut_is_a_violation(timeline_engine: VideoTimeline) -> None:
    cut = Timeline(
        format="film",
        clips=(_clip(1, 0.0, 1.0),),
        audio=AudioTrack(bed="strings", fade_out_seconds=5.0),
    )
    assert any(f["rule"] == "audio-fade" for f in timeline_engine.validate(cut)["violations"])


def test_an_unknown_resolution_is_a_violation(timeline_engine: VideoTimeline) -> None:
    report = timeline_engine.validate(
        Timeline(format="film", clips=(_clip(1, 0.0, 5.0),), resolution="8k")
    )
    assert any(f["rule"] == "resolution" for f in report["violations"])


def test_the_report_counts_what_it_checked(timeline_engine: VideoTimeline, storyboard) -> None:
    report = timeline_engine.validate(timeline_engine.from_storyboard(storyboard))
    assert report["duration_seconds"] == 25.0
    assert set(report) == {"valid", "violations", "warnings", "duration_seconds", "rendered", "unrendered"}


# ---------------------------------------------------------------------------
# Serialization and responsibility
# ---------------------------------------------------------------------------


def test_to_dict_carries_everything_a_client_needs(timeline_engine: VideoTimeline, storyboard) -> None:
    payload = timeline_engine.from_storyboard(storyboard).to_dict()
    assert payload["clip_count"] == 5
    assert payload["complete"] is False
    assert payload["unrendered_clips"] == [1, 2, 3, 4, 5]
    assert payload["clips"][0]["transition"] == CUT


def test_the_timeline_never_emits_prompt_text(timeline_engine: VideoTimeline, storyboard) -> None:
    """PromptCompiler owns text. A cut is timing, not wording."""

    payload = json.dumps(timeline_engine.from_storyboard(storyboard).to_dict()).lower()
    for token in ("prompt", "negative"):
        assert token not in payload


def test_the_timeline_module_does_not_reimplement_the_engine() -> None:
    module = pathlib.Path("backend/app/core/timeline.py").read_text()
    assert "FORMAT_KEYWORDS = " not in module
    assert "def detect_format" not in module
    assert "ARC_BY_FORMAT = " not in module


def test_the_timeline_never_shells_out_or_writes_media() -> None:
    """A plan is not a file. Rendering belongs to `app.media`, not to the Core.

    Checked on the import graph rather than on the word "ffmpeg", which appears
    in this module's docstring explaining exactly that boundary.
    """

    import ast

    tree = ast.parse(pathlib.Path("backend/app/core/timeline.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "dataclasses", "contracts"}, sorted(imported)


# ---------------------------------------------------------------------------
# FFmpeg primitives — the argument builders are pure and fully testable
# ---------------------------------------------------------------------------


def test_probe_fields_reads_the_facts_a_timeline_needs() -> None:
    from app.media import probe_fields

    payload = json.dumps(
        {
            "format": {"duration": "12.5", "format_name": "mov,mp4"},
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080,
                 "avg_frame_rate": "24000/1001", "codec_name": "h264"},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        }
    )
    fields = probe_fields(payload)
    assert fields["duration_seconds"] == 12.5
    assert (fields["width"], fields["height"]) == (1920, 1080)
    assert fields["fps"] == pytest.approx(23.976, abs=0.001)
    assert fields["video_codec"] == "h264"
    assert fields["audio_codec"] == "aac"
    assert fields["container"] == "mov,mp4"


def test_probe_fields_survives_garbage_instead_of_raising() -> None:
    from app.media import probe_fields

    assert probe_fields("not json") == {}
    assert probe_fields("") == {}
    assert probe_fields("[1,2,3]") == {}
    assert probe_fields(None) == {}


def test_a_duration_that_is_not_a_number_is_dropped_not_guessed() -> None:
    from app.media import probe_fields

    assert "duration_seconds" not in probe_fields(json.dumps({"format": {"duration": "n/a"}}))


def test_a_zero_denominator_frame_rate_is_dropped() -> None:
    from app.media import probe_fields

    fields = probe_fields(
        json.dumps({"streams": [{"codec_type": "video", "avg_frame_rate": "0/0"}]})
    )
    assert fields["fps"] is None


def test_concat_builds_a_demuxer_command_in_the_given_order() -> None:
    from app.media import concat_command

    command = concat_command(["a.mp4", "b.mp4"], "out.mp4", list_file="/tmp/list.txt", quality="1080p", fps=24)
    assert command[:2] == ["ffmpeg", "-y"]
    assert command[2:6] == ["-f", "concat", "-safe", "0"]
    assert command[command.index("-i") + 1] == "/tmp/list.txt"
    assert command[-1] == "out.mp4"
    assert "-an" in command, "no music bed means no audio stream, said explicitly"
    assert "1920:1080" in command[command.index("-vf") + 1]


def test_concat_maps_the_music_bed_as_a_second_input() -> None:
    from app.media import concat_command

    command = concat_command(["a.mp4"], "out.mp4", list_file="/tmp/l.txt", audio="/tmp/bed.m4a")
    assert command.count("-i") == 2
    first = command.index("-i")
    assert command[command.index("-i", first + 1) + 1] == "/tmp/bed.m4a"
    assert "0:v:0" in command and "1:a:0" in command
    assert "-shortest" in command, "a long track must not hold the file open past the last frame"
    assert "-an" not in command


def test_concat_re_encodes_rather_than_stream_copying() -> None:
    """Clips from different providers do not share a timebase or pixel format."""

    from app.media import concat_command

    command = concat_command(["a.mp4"], "out.mp4", list_file="/tmp/l.txt")
    assert "libx264" in command
    assert "copy" not in command


def test_concat_refuses_an_unknown_quality() -> None:
    from app.media import MediaError, concat_command

    with pytest.raises(MediaError, match="Unsupported quality"):
        concat_command(["a.mp4"], "out.mp4", list_file="/tmp/l.txt", quality="480p")


def test_concat_refuses_an_empty_cut() -> None:
    from app.media import MediaError, concat_command

    with pytest.raises(MediaError, match="no rendered clips"):
        concat_command([], "out.mp4", list_file="/tmp/l.txt")


def test_the_scale_filter_letterboxes_instead_of_stretching() -> None:
    from app.media import scale_filter

    assert scale_filter(1920, 1080) == (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2"
    )


@pytest.mark.skipif(
    __import__("shutil").which("ffmpeg") is not None,
    reason="this asserts the no-FFmpeg guard; skipped where FFmpeg exists",
)
def test_the_adapter_says_so_when_ffmpeg_is_missing() -> None:
    """The honest path: no binary, no output, and no invented result."""

    from app.media import MediaError, media

    assert media.available is False
    with pytest.raises(MediaError, match="FFmpeg is not installed"):
        media.probe("anything.mp4")
    with pytest.raises(MediaError, match="FFmpeg is not installed"):
        media.concat(["a.mp4"], "out.mp4")
    with pytest.raises(MediaError, match="FFmpeg is not installed"):
        media.export_h264("a.mp4", "out.mp4")


def test_the_capability_report_does_not_claim_a_binary() -> None:
    from app.media import media

    report = media.capabilities()
    assert set(report) == {"available", "binary", "formats"}
    if not report["available"]:
        assert report["binary"] is None


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_the_timeline_endpoint_assembles_a_brief(client) -> None:
    body = client.post(
        "/api/v1/core/timeline",
        json={"brief": "Quero um comercial de 30 segundos para uma camiseta artesanal.", "scene_count": 5},
    ).json()
    assert body["format"] == "commercial"
    assert body["clip_count"] == 5
    assert body["duration_seconds"] == pytest.approx(25.0)
    assert body["aspect_ratio"] == "16:9"
    assert (body["width"], body["height"]) == (1920, 1080)
    assert body["audio"]["bed"], "the Director's music must reach the cut"


def test_the_endpoint_does_not_claim_rendered_media(client) -> None:
    body = client.post("/api/v1/core/timeline", json={"brief": "comercial de produto"}).json()
    assert body["complete"] is False
    assert body["rendered_clips"] == 0
    assert len(body["unrendered_clips"]) == body["clip_count"]
    assert all(clip["rendered"] is False for clip in body["clips"])


def test_the_endpoint_accepts_rendered_sources(client) -> None:
    body = client.post(
        "/api/v1/core/timeline",
        json={"brief": "comercial de produto", "scene_count": 4, "sources": {"1": "ws/a.mp4", "2": "ws/b.mp4"}},
    ).json()
    assert body["rendered_clips"] == 2
    assert body["unrendered_clips"] == [3, 4]
    assert body["clips"][0]["source"] == "ws/a.mp4"
    assert body["complete"] is False


def test_a_vertical_brief_gets_a_vertical_frame(client) -> None:
    body = client.post(
        "/api/v1/core/timeline", json={"brief": "quero um reels vertical", "scene_count": 4}
    ).json()
    assert body["aspect_ratio"] == "9:16"
    assert (body["width"], body["height"]) == (1080, 1920)


def test_the_catalogue_reads_straight_off_the_core_tables(client) -> None:
    body = client.get("/api/v1/core/timeline/formats").json()
    assert body["default_aspect_ratio"] == DEFAULT_ASPECT_RATIO
    assert body["default_resolution"] == DEFAULT_RESOLUTION
    assert body["transitions"] == list(TRANSITIONS)
    assert {entry["format"]: entry["aspect_ratio"] for entry in body["formats"]} == ASPECT_BY_FORMAT
    assert body["resolutions"]["1080p"] == [1920, 1080]


def test_the_timeline_routes_contain_no_timing_logic_of_their_own() -> None:
    """The route wires components; VideoTimeline owns the decisions."""

    import ast

    tree = ast.parse(pathlib.Path("backend/app/main.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "build_timeline":
            source = ast.unparse(node)
            assert "duration_per_scene *" not in source
            assert "start_seconds" not in source
            assert "DISSOLVE" not in source
            return
    raise AssertionError("build_timeline is not defined")


@pytest.mark.parametrize(
    "payload",
    [
        {"brief": ""},
        {"brief": "x", "scene_count": 1},
        {"brief": "x", "scene_count": 13},
        {"brief": "x", "duration_per_scene": 0},
        {"brief": "x", "duration_per_scene": 999},
        {"brief": "x", "fps": 0},
        {"brief": "x", "fps": 121},
        {"brief": "x", "resolution": "480p"},
    ],
)
def test_the_timeline_endpoint_validates_its_input(client, payload) -> None:
    assert client.post("/api/v1/core/timeline", json=payload).status_code == 422


def test_probe_merges_the_parsed_fields_into_its_result(monkeypatch) -> None:
    """The wiring between `probe` and `probe_fields`, without an FFmpeg binary.

    `subprocess.run` is stubbed, so this proves the merge and the error handling
    around a real payload shape — not that ffprobe itself behaves. Reverting
    `probe` to return only `{"raw": ...}` fails here, which is the point: nothing
    else in the suite reaches that line when no binary is installed.
    """

    import subprocess

    from app.media import MediaError, media

    payload = json.dumps(
        {
            "format": {"duration": "8.0", "format_name": "mp4"},
            "streams": [{"codec_type": "video", "width": 640, "height": 360}],
        }
    )

    class Result:
        returncode = 0
        stdout = payload
        stderr = ""

    monkeypatch.setattr(type(media), "available", property(lambda self: True))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())

    fields = media.probe("clip.mp4")
    assert fields["raw"] == payload, "the untouched payload is still handed back"
    assert fields["duration_seconds"] == 8.0
    assert (fields["width"], fields["height"]) == (640, 360)


def test_probe_reports_a_failure_instead_of_returning_empty_facts(monkeypatch) -> None:
    import subprocess

    from app.media import MediaError, media

    class Result:
        returncode = 1
        stdout = ""
        stderr = "moov atom not found"

    monkeypatch.setattr(type(media), "available", property(lambda self: True))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(MediaError, match="moov atom not found"):
        media.probe("broken.mp4")


def test_concat_writes_the_list_file_ffmpeg_will_read(monkeypatch, tmp_path) -> None:
    """Order is the caller's, and a path with a quote must not change what runs."""

    import subprocess

    from app.media import media

    captured: dict[str, list[str]] = {}
    written: list[str] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        list_file = command[command.index("-i") + 1]
        written.append(pathlib.Path(list_file).read_text())
        return Result()

    monkeypatch.setattr(type(media), "available", property(lambda self: True))
    monkeypatch.setattr(subprocess, "run", fake_run)

    media.concat(["one.mp4", "it's here.mp4"], str(tmp_path / "out.mp4"))

    assert captured["command"][-1] == str(tmp_path / "out.mp4")
    assert written[0].splitlines() == ["file 'one.mp4'", r"file 'it\'s here.mp4'"], (
        "the concat list must stay in the caller's order and stay parseable"
    )


def test_concat_cleans_up_its_list_file_even_on_failure(monkeypatch, tmp_path) -> None:
    import subprocess

    from app.media import MediaError, media

    seen: list[str] = []

    class Result:
        returncode = 1
        stdout = ""
        stderr = "Invalid data found when processing input"

    def fake_run(command, **kwargs):
        seen.append(command[command.index("-i") + 1])
        return Result()

    monkeypatch.setattr(type(media), "available", property(lambda self: True))
    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(MediaError, match="Invalid data"):
        media.concat(["a.mp4"], str(tmp_path / "out.mp4"))

    assert seen and not pathlib.Path(seen[0]).exists(), "the temp list was left behind"


def test_a_stream_that_is_not_an_object_is_skipped() -> None:
    from app.media import probe_fields

    fields = probe_fields(
        json.dumps({"streams": ["garbage", {"codec_type": "video", "width": 320, "height": 240}]})
    )
    assert (fields["width"], fields["height"]) == (320, 240)


def test_a_plain_frame_rate_is_read_as_written() -> None:
    from app.media import probe_fields

    fields = probe_fields(json.dumps({"streams": [{"codec_type": "video", "avg_frame_rate": "25"}]}))
    assert fields["fps"] == 25.0


def test_an_unreadable_frame_rate_is_dropped_not_guessed() -> None:
    from app.media import probe_fields

    fields = probe_fields(json.dumps({"streams": [{"codec_type": "video", "avg_frame_rate": "n/a"}]}))
    assert fields["fps"] is None
