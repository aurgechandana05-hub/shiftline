from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
import wave
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import imageio_ffmpeg
import winsound
from playwright.sync_api import BrowserContext, Page, sync_playwright


ROOT = Path(__file__).resolve().parent
APP_URL = "http://127.0.0.1:8000"
OUTPUT = ROOT / "Shiftline_Live_Hindsight_Walkthrough.mp4"
SUBTITLES = ROOT / "Shiftline_Live_Hindsight_Walkthrough.srt"
WIDTH = 1280
HEIGHT = 720
FPS = 24
SCREENSHOT_FPS = 4
INTRO_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;font-family:Segoe UI,Arial,sans-serif}
body{display:grid;place-items:center;background:radial-gradient(ellipse at 78% 18%,#163a39 0,transparent 43%),linear-gradient(135deg,#0a1018,#111b27 72%,#0d1720);color:#ecf4f3}
main{width:100%;height:100%;padding:76px 112px;display:flex;flex-direction:column;justify-content:center}
.eyebrow{font-size:15px;letter-spacing:.22em;text-transform:uppercase;color:#8de7c7;font-weight:600}
h1{font-size:68px;line-height:1.04;letter-spacing:-.045em;max-width:950px;margin:28px 0 20px;font-weight:650}
h1 span{color:#82e3c2}
.purpose{font-size:25px;line-height:1.48;color:#c1ccd3;max-width:910px}
.rule{height:1px;background:#2b3c49;width:100%;margin:38px 0 24px}
.foot{display:flex;justify-content:space-between;gap:30px;color:#95a7b4;font-size:15px}
.tag{border:1px solid #496455;border-radius:999px;padding:8px 14px;color:#b4f0d8;letter-spacing:.08em}
</style>
</head>
<body><main>
<div class="eyebrow">Shiftline · Live Hindsight walkthrough</div>
<h1>Carry the context.<br><span>Not the whole conversation.</span></h1>
<div class="purpose">Purpose: help the next on-call operator inherit what happened, what failed, what the customer needs, and what is still unverified.</div>
<div class="rule"></div>
<div class="foot"><span>Actual Shiftline app · live Hindsight Cloud calls</span><span class="tag">SYNTHETIC INCIDENT EXAMPLE</span></div>
</main></body></html>"""
OUTRO_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{margin:0;width:100%;height:100%;font-family:Segoe UI,Arial,sans-serif}
body{display:grid;place-items:center;background:radial-gradient(ellipse at 78% 18%,#163a39 0,transparent 43%),linear-gradient(135deg,#0a1018,#111b27 72%,#0d1720);color:#ecf4f3}
main{max-width:950px;padding:68px}small{color:#8de7c7;text-transform:uppercase;letter-spacing:.2em;font-size:15px}
h1{font-size:55px;line-height:1.12;letter-spacing:-.04em;margin:26px 0 16px}
p{font-size:22px;line-height:1.55;color:#c1ccd3}footer{margin-top:35px;color:#9aadb7;font-size:15px}
</style></head><body><main>
<small>Shiftline · Live Hindsight</small>
<h1>Better handoffs.<br>Human decisions stay human.</h1>
<p>Preserve evidence across shifts. Verify remembered context before acting. The Acme Logistics incident shown here is fictional.</p>
<footer>Actual retain · recall · Reflect · memory comparison</footer>
</main></body></html>"""


@dataclass(frozen=True)
class Scene:
    name: str
    narration: str
    action: str


SCENES = [
    Scene(
        "Purpose",
        "Every shift change risks losing one important fact: what failed, what the customer cannot change, and what is still unverified. Shiftline is built to carry that context forward.",
        "intro",
    ),
    Scene(
        "The real-world handoff problem",
        "Here is a familiar on-call moment: webhook deliveries duplicate after a replay, the customer's signing secret cannot rotate until Friday, and an earlier replay made things worse. This Acme Logistics incident is synthetic, but it reflects real support pressure: people inherit incidents while customers and services are still waiting.",
        "incident",
    ),
    Scene(
        "Retain selected context",
        "These four fictional handoff notes have already been explicitly retained in the live Hindsight bank. The incoming operator can review their sources without replaying the entire conversation. Real teams should store only approved, appropriately redacted incident context.",
        "retained",
    ),
    Scene(
        "Recall and Reflect",
        "Now I ask what not to repeat. Shiftline first recalls memory from Hindsight, then invokes Hindsight Reflect. The answer connects the failed replay with the customer constraint, so the next operator is not asked to rediscover it from a long chat log.",
        "reflect",
    ),
    Scene(
        "Keep evidence and uncertainty distinct",
        "The answer warns against repeating the replay and keeps the suggested idempotency check marked unverified. That distinction matters in practice: remembered facts are evidence to review, not permission for an AI to act.",
        "answer",
    ),
    Scene(
        "See the memory difference",
        "Memory Replay compares a fresh session with actual Hindsight recall. Shiftline's purpose is focused handoff: less repeated investigation, fewer forgotten constraints, and a human still making every operational decision.",
        "compare",
    ),
    Scene(
        "Human-led operations",
        "The incident here is fictional, not a real customer case. In a real deployment, use approved and redacted records, verify each source, and keep operators in control. Shiftline carries context forward; it does not resolve incidents autonomously.",
        "outro",
    ),
]


def ffmpeg_path() -> str:
    executable = imageio_ffmpeg.get_ffmpeg_exe()
    if not Path(executable).is_file():
        raise RuntimeError("The bundled FFmpeg executable is not available.")
    return executable


def synthesize_narration(audio_dir: Path) -> list[Path]:
    powershell = shutil.which("powershell.exe")
    if not powershell:
        raise RuntimeError("Windows PowerShell is required for the built-in narration voice.")

    clips = [audio_dir / f"scene-{index:02}.wav" for index in range(len(SCENES))]
    payload = [
        {"path": str(path), "text": scene.narration}
        for path, scene in zip(clips, SCENES)
    ]
    script = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$scenes = ConvertFrom-Json ([Console]::In.ReadToEnd())
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.Rate = -1
$voice.Volume = 100
$zira = $voice.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name -eq 'Microsoft Zira Desktop' } | Select-Object -First 1
if ($zira) { $voice.SelectVoice('Microsoft Zira Desktop') }
foreach ($scene in $scenes) {
    $voice.SetOutputToWaveFile([string]$scene.path)
    $voice.Speak([string]$scene.text)
    $voice.SetOutputToNull()
}
$voice.Dispose()
"""
    result = subprocess.run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        input=json.dumps(payload, ensure_ascii=True),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "Windows speech synthesis failed. "
            f"PowerShell detail: {result.stderr.strip() or result.stdout.strip()}"
        )
    if not all(path.is_file() and path.stat().st_size > 44 for path in clips):
        raise RuntimeError("Windows speech synthesis did not produce every narration clip.")
    return clips


def read_wave(path: Path) -> tuple[wave._wave_params, bytes]:
    with wave.open(str(path), "rb") as source:
        parameters = source.getparams()
        if parameters.comptype != "NONE" or parameters.sampwidth != 2:
            raise RuntimeError("Narration must be uncompressed 16-bit PCM audio.")
        return parameters, source.readframes(parameters.nframes)


def srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    value = timedelta(milliseconds=milliseconds)
    total = int(value.total_seconds())
    remainder = milliseconds % 1000
    hours, total = divmod(total, 3600)
    minutes, seconds = divmod(total, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{remainder:03}"


def caption_entries(scene: Scene, start: float, duration: float) -> list[str]:
    lines = textwrap.wrap(scene.narration, width=68)
    groups = [lines[index : index + 2] for index in range(0, len(lines), 2)]
    weights = [max(1, len(" ".join(group).split())) for group in groups]
    total_weight = sum(weights)
    result: list[str] = []
    elapsed = 0
    for group, weight in zip(groups, weights):
        cue_start = start + duration * elapsed / total_weight
        elapsed += weight
        cue_end = start + duration * elapsed / total_weight
        result.append(
            f"{srt_time(cue_start)} --> {srt_time(cue_end)}\n"
            + "\n".join(group)
        )
    return result


def save_wave_and_subtitles(
    output_audio: Path,
    clips: list[Path],
    clip_starts: list[float],
    video_duration: float,
) -> None:
    audio_parts: list[tuple[float, bytes, wave._wave_params]] = []
    cues: list[str] = []
    base_parameters: wave._wave_params | None = None
    for scene, path, start in zip(SCENES, clips, clip_starts):
        parameters, frames = read_wave(path)
        if base_parameters is not None and parameters[:3] != base_parameters[:3]:
            raise RuntimeError("Narration clips use incompatible audio formats.")
        base_parameters = parameters
        duration = parameters.nframes / parameters.framerate
        audio_parts.append((start, frames, parameters))
        cues.extend(caption_entries(scene, start, duration))

    assert base_parameters is not None
    sample_width = base_parameters.sampwidth
    silence = b"\x00" * sample_width
    cursor = 0
    with wave.open(str(output_audio), "wb") as destination:
        destination.setnchannels(base_parameters.nchannels)
        destination.setsampwidth(sample_width)
        destination.setframerate(base_parameters.framerate)
        for start, frames, parameters in audio_parts:
            start_frame = round(start * parameters.framerate)
            if start_frame < cursor:
                raise RuntimeError("Narration scenes overlap; refusing to produce a mistimed mix.")
            gap = start_frame - cursor
            if gap:
                destination.writeframesraw(silence * gap * parameters.nchannels)
            destination.writeframesraw(frames)
            cursor = start_frame + len(frames) // (
                sample_width * parameters.nchannels
            )
        final_frame = round(video_duration * base_parameters.framerate)
        if cursor < final_frame:
            destination.writeframesraw(
                silence * (final_frame - cursor) * base_parameters.nchannels
            )

    SUBTITLES.write_text(
        "\n\n".join(f"{index}\n{cue}" for index, cue in enumerate(cues, start=1)) + "\n",
        encoding="utf-8",
    )


def ensure_live_hindsight() -> dict[str, Any]:
    try:
        import urllib.request

        with urllib.request.urlopen(f"{APP_URL}/api/health", timeout=8) as response:
            health = json.loads(response.read())
    except Exception as exc:
        raise RuntimeError(
            f"Shiftline is not reachable at {APP_URL}. Start the live Hindsight app first."
        ) from exc
    if (
        health.get("ok") is not True
        or health.get("provider") != "Hindsight"
        or health.get("mode") != "hindsight"
    ):
        raise RuntimeError(
            "The recording requires a healthy live Hindsight connection; demo mode is not recorded."
        )
    return health


def require_provider(payload: dict[str, Any], operation: str) -> None:
    if payload.get("error"):
        detail = re.sub(
            r"hsk_[A-Za-z0-9_-]+",
            "[REDACTED]",
            str(payload["error"]),
        )
        raise RuntimeError(f"The live {operation} returned an error: {detail}")
    if payload.get("provider") != "Hindsight":
        raise RuntimeError(
            f"The live {operation} did not return the Hindsight provider "
            f"(received {payload.get('provider')!r})."
        )


def configure_scene(page: Page, scene: Scene) -> None:
    if scene.action == "intro":
        page.set_content(INTRO_HTML, wait_until="load")
        return
    if scene.action == "incident":
        page.goto(APP_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_function(
            "() => document.querySelector('#provider-badge')?.innerText.includes('Hindsight')",
            timeout=30000,
        )
        page.evaluate("window.scrollTo(0, 0)")
        return
    if scene.action == "retained":
        if "Hindsight" not in page.locator("#provider-badge").inner_text():
            raise RuntimeError("The retained-memory screen is not connected to Hindsight.")
        page.get_by_role("button", name="Review brief").click()
        return
    if scene.action == "reflect":
        page.get_by_role("button", name="What should I avoid doing again?").scroll_into_view_if_needed()
        with page.expect_response(
            lambda response: response.url.endswith("/api/recall")
            and response.request.method == "POST"
            and json.loads(response.request.post_data or "{}").get("synthesize") is True,
            timeout=90000,
        ) as response_info:
            page.get_by_role("button", name="What should I avoid doing again?").click()
        payload = response_info.value.json()
        require_provider(payload, "recall")
        if payload.get("answer_kind") != "Hindsight Reflect" or not payload.get("answer"):
            raise RuntimeError("Hindsight Reflect did not return a live answer for this handoff.")
        page.locator("#answer-panel").scroll_into_view_if_needed()
        return
    if scene.action == "answer":
        page.locator("#answer-panel").scroll_into_view_if_needed()
        if not page.locator("#answer-panel").is_visible():
            raise RuntimeError("The live Hindsight Reflect answer is not visible.")
        return
    if scene.action == "compare":
        with page.expect_response(
            lambda response: response.url.endswith("/api/compare")
            and response.request.method == "POST",
            timeout=90000,
        ) as response_info:
            page.get_by_role("button", name=re.compile("See the memory difference")).click()
        payload = response_info.value.json()
        require_provider(payload, "memory comparison")
        if not payload.get("memory_on", {}).get("memories"):
            raise RuntimeError("Hindsight returned no memories for the live comparison.")
        return
    if scene.action == "outro":
        page.locator("#close-compare").click(timeout=5000)
        page.set_content(OUTRO_HTML, wait_until="load")
        return
    raise RuntimeError(f"Unknown recording scene: {scene.action}")


def record(clips: list[Path], frames_dir: Path) -> tuple[Path, list[float], float]:
    frames_dir.mkdir(parents=True, exist_ok=True)
    clip_starts: list[float] = []
    frame_index = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        context: BrowserContext = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=1,
            color_scheme="dark",
        )
        page = context.new_page()
        configure_scene(page, SCENES[0])

        parameters: wave._wave_params | None = None
        for scene, clip in zip(SCENES, clips):
            if scene.action != SCENES[0].action:
                configure_scene(page, scene)
                page.wait_for_timeout(450)
            clip_parameters, frames = read_wave(clip)
            if parameters is not None and clip_parameters[:3] != parameters[:3]:
                raise RuntimeError("Narration clips use incompatible audio formats.")
            parameters = clip_parameters
            duration = clip_parameters.nframes / clip_parameters.framerate
            clip_starts.append(frame_index / SCREENSHOT_FPS)
            winsound.PlaySound(
                str(clip),
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
            frames_for_scene = max(1, math.ceil(duration * SCREENSHOT_FPS))
            scene_capture_start = time.perf_counter()
            for scene_frame in range(frames_for_scene):
                page.screenshot(
                    path=str(frames_dir / f"frame_{frame_index:06}.png"),
                    type="png",
                )
                frame_index += 1
                remaining = (scene_frame + 1) / SCREENSHOT_FPS - (
                    time.perf_counter() - scene_capture_start
                )
                if remaining > 0:
                    time.sleep(remaining)

        page.wait_for_timeout(600)
        page.screenshot(path=str(frames_dir / f"frame_{frame_index:06}.png"), type="png")
        frame_index += 1
        video_duration = frame_index / SCREENSHOT_FPS
        context.close()
        browser.close()

    if frame_index < 1:
        raise RuntimeError("The live browser capture did not produce any frames.")
    return frames_dir, clip_starts, video_duration


def mux_recording(frames_dir: Path, audio_path: Path) -> None:
    command = [
        ffmpeg_path(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        str(SCREENSHOT_FPS),
        "-i",
        str(frames_dir / "frame_%06d.png"),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "21",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(OUTPUT),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    if result.returncode:
        raise RuntimeError(f"FFmpeg could not package the live recording: {result.stderr.strip()}")


def main() -> None:
    health = ensure_live_hindsight()
    print(
        "Live Hindsight verified. Recording the actual Shiftline app against "
        f"bank {health.get('bank_id', 'configured bank')}."
    )
    with tempfile.TemporaryDirectory(prefix="shiftline-live-recording-") as temporary:
        work = Path(temporary)
        audio_dir = work / "narration"
        audio_dir.mkdir()
        clips = synthesize_narration(audio_dir)
        frames_dir, clip_starts, duration = record(clips, work / "browser-frames")
        mixed_audio = work / "narration.wav"
        save_wave_and_subtitles(mixed_audio, clips, clip_starts, duration)
        mux_recording(frames_dir, mixed_audio)
    print(f"Live recording: {OUTPUT}")
    print(f"Subtitles: {SUBTITLES}")
    print(f"Duration: {timedelta(seconds=round(duration))}")
    print(f"MP4 size: {OUTPUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
