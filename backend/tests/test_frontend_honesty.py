"""ETAPA 15 guards — the studio must not lie to the user.

The frontend has no JavaScript test runner in this repository, and adding one is
ETAPA 16 work. These are structural guards in the same style the backend already
uses for its own source (`test_the_timeline_routes_contain_no_timing_logic_of_their_own`
and friends): they read the files and assert on what is there.

They exist because the defects they pin were real and invisible. The shell showed
a hard-coded "RTX 4090 · 18.4 / 24 GB VRAM" on a host with no GPU, a fake render
labelled "FLUX / 2K" regardless of whether anything had been generated, and it
consumed none of the 31 Core routes — so fourteen etapas of decision layer were
unreachable from the product.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
API = ROOT / "lib" / "api.ts"
PAGE = ROOT / "app" / "page.tsx"
NEXT_CONFIG = ROOT / "next.config.mjs"


def _read(path: pathlib.Path) -> str:
    assert path.is_file(), f"{path} is missing"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def api_source() -> str:
    return _read(API)


@pytest.fixture(scope="module")
def page_source() -> str:
    return _read(PAGE)


# ---------------------------------------------------------------------------
# The browser must not be told to reach a hard-coded origin
# ---------------------------------------------------------------------------


def test_the_client_does_not_default_to_localhost(api_source: str) -> None:
    """`http://localhost:8000` only works when the browser is on the API's host.

    The base is now empty and `next.config.mjs` proxies `/api/v1`, so the UI
    works behind any host.
    """

    assert "localhost:8000" not in api_source
    assert "export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''" in api_source


def test_the_proxy_is_configured() -> None:
    config = _read(NEXT_CONFIG)
    assert "rewrites" in config
    assert "/api/v1/:path*" in config
    # The target is an env var, not a literal, so deployments can point elsewhere.
    assert "BROBOND_API_PROXY_TARGET" in config


def test_websocket_urls_are_derived_not_hardcoded(api_source: str, page_source: str) -> None:
    assert "export function wsUrl(" in api_source
    assert "window.location.origin" in api_source
    assert "wsUrl(" in page_source
    assert "API_URL.replace(/^http/, 'ws')" not in page_source, "the old inline ws:// construction is back"


# ---------------------------------------------------------------------------
# The Core must actually be reachable from the product
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/core/direct",
        "/api/v1/core/storyboard",
        "/api/v1/core/timeline",
        "/api/v1/core/quality/assess",
        "/api/v1/core/quality/rules",
        "/api/v1/core/providers",
    ],
)
def test_the_core_routes_are_wired_into_the_client(api_source: str, path: str) -> None:
    assert path in api_source, f"{path} is still unreachable from the studio"


def test_the_director_is_the_front_door(page_source: str) -> None:
    """SYSTEM_PROMPT.md: the user talks to a director, not to a prompt field.

    The Director module must exist and be the default view.
    """

    assert "function DirectorStudio(" in page_source
    assert "useState('director')" in page_source
    assert "directIntent(" in page_source


def test_the_director_never_answers_with_a_prompt_string(page_source: str) -> None:
    """The brief panel shows concept, logline, script, beats — not a prompt box."""

    director = page_source.split("function DirectorStudio(", 1)[1].split("\nfunction AuthModal", 1)[0]
    assert "brief.concept" in director
    assert "brief.logline" in director
    assert "brief.beats.map" in director
    assert "brief.clarification" in director, "the director's question must be shown, not swallowed"
    assert "prompt_compiled" not in director


# ---------------------------------------------------------------------------
# Nothing may be invented
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fabrication",
    [
        "RTX 4090",            # a GPU this host does not have
        "18.4 / 24 GB VRAM",   # memory that was never read
        "Good evening, Petrick",  # a greeting fixed to one name and one hour
        "LoRA v1.2",           # a training version that was never trained
        "FLUX / 2K",           # a label on a drawing, not on a render
        "result-person",       # the CSS figure passed off as a generated image
        "12 renders",
        "4 renders",
        "2 personas",
    ],
)
def test_the_shell_does_not_invent_facts(page_source: str, fabrication: str) -> None:
    assert fabrication not in page_source


def test_the_gpu_card_reads_the_api(page_source: str) -> None:
    assert "gpuInfo(" in page_source
    # The path may appear as a label telling the user what is being queried; it
    # must not appear as a fetch, because the call belongs in lib/api.ts.
    assert "fetch(" not in page_source, "page.tsx must go through the client"
    assert "gpu.message" in page_source or "gpu.backend" in page_source


def test_readiness_is_shown(page_source: str) -> None:
    assert "readiness(" in page_source
    assert "inference_ready" in page_source or "readyChecks" in page_source


def test_asset_counts_are_counted_not_asserted(page_source: str) -> None:
    """The tabs used to print 128 / 84 / 24 / 2 / 18 whatever the library held."""

    for fake in ("128", "84", "24", "18"):
        assert f"<span>{fake}</span>" not in page_source
    assert "counts.all" in page_source


# ---------------------------------------------------------------------------
# The real result must be shown, and failures must be visible
# ---------------------------------------------------------------------------


def test_the_canvas_shows_the_real_output(page_source: str) -> None:
    assert "job.output_url" in page_source
    assert 'src={job.output_url}' in page_source


def test_a_failed_render_is_not_dressed_as_a_result(page_source: str) -> None:
    """An image is rendered only when there is one; otherwise it says so."""

    assert "The render failed — no image was produced" in page_source
    assert "job?.output_url ? <img" in page_source or "job?.output_url && <span" in page_source


def test_errors_reach_the_user(page_source: str, api_source: str) -> None:
    """Every swallowed error used to read as "offline", including 401 and 422."""

    assert "function Notice(" in page_source
    assert page_source.count("<Notice") >= 4, "each studio panel must be able to explain a failure"
    # The client distinguishes "no answer" from "the server answered with an error".
    assert "status?: number" in api_source
    assert "error?: string" in api_source
    assert "readError" in api_source
    assert "return failed<T>('offline')" in api_source


def test_a_rejected_login_is_not_reported_as_offline(page_source: str) -> None:
    assert "if (result.status)" in page_source


def test_the_controls_drive_the_request(page_source: str) -> None:
    """The model/aspect/resolution selects used to render while literals were sent."""

    generate = page_source.split("function ImageStudio(", 1)[1].split("function VideoStudio(", 1)[0]
    assert "model, aspect_ratio: aspectRatio, resolution," in generate, (
        "the image request must carry what the user picked"
    )
    assert "aspect_ratio: '16:9'" not in generate


def test_the_video_controls_drive_the_request(page_source: str) -> None:
    generate = page_source.split("function VideoStudio(", 1)[1].split("function PersonaStudio(", 1)[0]
    assert "duration_seconds: duration" in generate
    assert "aspect_ratio: aspect" in generate


# ---------------------------------------------------------------------------
# The storyboard reports what the Core found
# ---------------------------------------------------------------------------


def test_the_storyboard_uses_the_core_and_shows_findings(page_source: str) -> None:
    assert "buildStoryboard(" in page_source
    assert "result.data.violations" in page_source
    assert "finding-list" in page_source


def test_the_prompt_counter_tracks_the_field(page_source: str) -> None:
    """It used to print a fixed "72 / 2,000" no matter what was typed."""

    assert "72 / 2,000" not in page_source
    assert "{prompt.length} / 2,000" in page_source
