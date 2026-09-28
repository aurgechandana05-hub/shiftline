from __future__ import annotations

import math
import subprocess
import tempfile
import textwrap
import wave
from pathlib import Path

import imageio.v2 as imageio
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "Shiftline_Demo_Walkthrough.mp4"
SUBTITLES = ROOT / "Shiftline_Demo_Walkthrough.srt"
WIDTH, HEIGHT, FPS = 1280, 720, 20
UI_X, UI_Y, UI_W, UI_H = 22, 17, 1236, 580
FONT_DIR = Path(r"C:\Windows\Fonts")

COLORS = {
    "bg": "#0b111b",
    "sidebar": "#0d141f",
    "panel": "#101925",
    "raised": "#131e2b",
    "border": "#263443",
    "text": "#e8edf4",
    "muted": "#8998a8",
    "dim": "#66778a",
    "mint": "#75e5be",
    "amber": "#edc278",
    "coral": "#f08a86",
    "purple": "#c0a7fa",
    "blue": "#90b9fa",
}

SCENES = [
    {
        "title": "A better shift starts with context.",
        "narration": (
            "A new shift starts. Same incident, different engineer, and no time to read two hundred "
            "chat messages. Shiftline turns that handoff into context the next operator can act on."
        ),
        "kind": "title",
    },
    {
        "title": "One real workflow. One clear user.",
        "narration": (
            "This example follows Acme Logistics, a fictional customer with duplicate webhook deliveries. "
            "The goal is not autonomous incident response. It is helping a human inherit the evidence, "
            "decisions, and constraints that shaped the last shift."
        ),
        "kind": "overview",
    },
    {
        "title": "Start with what changed.",
        "narration": (
            "First, we see what changed: duplicate deliveries began just after a webhook replay. "
            "That timing belongs with the source, so the next person knows where this timeline entry came from."
        ),
        "kind": "changed",
    },
    {
        "title": "Keep the customer constraint visible.",
        "narration": (
            "There is also a customer constraint: their signing secret cannot be rotated before Friday. "
            "A generic summary may lose that detail. Here it is prominent and linked to the customer-call note."
        ),
        "kind": "constraint",
    },
    {
        "title": "Remember what not to repeat.",
        "narration": (
            "The previous replay made duplicates worse. Shiftline marks that attempt as a failed approach, "
            "not advice. During a handoff, remembering what not to repeat can matter as much as remembering "
            "what happened."
        ),
        "kind": "failed",
    },
    {
        "title": "Make the brief useful, and honest.",
        "narration": (
            "The next-shift brief groups the safe next check, the failed workaround, and the customer "
            "constraint. Each detail has a source. The idempotency check is explicitly unverified; "
            "a suggestion is not a verified fix."
        ),
        "kind": "brief",
    },
    {
        "title": "Compare a fresh session with recall.",
        "narration": (
            "Now compare a fresh session with memory enabled. Without context, the agent admits it does not "
            "know the earlier constraint. With recalled context, it shows the failed replay and the Friday "
            "deadline, with sources."
        ),
        "kind": "compare",
    },
    {
        "title": "A human closes the learning loop.",
        "narration": (
            "An operator can ask about the incident, then record whether a step worked, failed, or is still "
            "unverified. That confirmed outcome can be retained so a later shift has better evidence."
        ),
        "kind": "outcome",
    },
    {
        "title": "Carry context. Keep people in control.",
        "narration": (
            "This walkthrough is using Shiftline's clearly labeled local demo memory, not a live Hindsight "
            "connection. When configured, the app can use Hindsight retain, recall, and reflect for "
            "cross-session memory. Shiftline helps teams hand context forward, not hand over control."
        ),
        "kind": "end",
    },
]


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    filename = "consola.ttf" if mono else ("seguisb.ttf" if bold else "segoeui.ttf")
    path = FONT_DIR / filename
    if not path.exists():
        path = FONT_DIR / ("arialbd.ttf" if bold else "arial.ttf")
    return ImageFont.truetype(str(path), size=size)


FONTS = {
    "tiny": font(10),
    "small": font(12),
    "body": font(14),
    "body_bold": font(14, True),
    "medium": font(17),
    "heading": font(24, True),
    "large": font(44, True),
    "hero": font(66, True),
    "mono": font(11, mono=True),
    "mono_small": font(9, mono=True),
}


def rgb(color: str) -> tuple[int, int, int]:
    value = color.removeprefix("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    fill: str,
    outline: str | None = None,
    radius: int = 8,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, color: str, size: int = 10) -> None:
    draw.text(xy, text.upper(), fill=color, font=font(size, mono=True))


def wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    max_width: int,
    face: ImageFont.FreeTypeFont,
    fill: str,
    line_gap: int = 4,
) -> int:
    x, y = xy
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=face)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    for line in lines:
        draw.text((x, y), line, fill=fill, font=face)
        y += face.size + line_gap
    return y


def new_canvas() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), rgb(COLORS["bg"]))
    pixels = np.asarray(image).copy()
    top = np.array(rgb("#0c1721"), dtype=np.float32)
    bottom = np.array(rgb(COLORS["bg"]), dtype=np.float32)
    for y in range(HEIGHT):
        amount = y / HEIGHT
        pixels[y, :, :] = (top * (1 - amount) + bottom * amount).astype(np.uint8)
    return Image.fromarray(pixels)


def draw_browser_frame(draw: ImageDraw.ImageDraw) -> None:
    rounded(draw, (UI_X, UI_Y, UI_X + UI_W, UI_Y + UI_H), "#0f1721", "#2a3947", 11, 1)
    rounded(draw, (UI_X + 1, UI_Y + 1, UI_X + UI_W - 1, UI_Y + 36), "#121b26", None, 10)
    draw.rectangle((UI_X + 1, UI_Y + 25, UI_X + UI_W - 1, UI_Y + 36), fill="#121b26")
    for index, color in enumerate(("#e68179", "#e7bd72", "#70c49b")):
        draw.ellipse((UI_X + 14 + index * 15, UI_Y + 13, UI_X + 21 + index * 15, UI_Y + 20), fill=color)
    rounded(draw, (UI_X + 89, UI_Y + 8, UI_X + 838, UI_Y + 28), "#0c141e", "#202e3d", 6)
    draw.text((UI_X + 105, UI_Y + 11), "●   Shiftline / INC-2048", fill="#9cabb8", font=FONTS["tiny"])
    draw.text((UI_X + UI_W - 182, UI_Y + 12), "SHIFTLINE  ·  PRODUCT PREVIEW", fill="#879a9f", font=FONTS["mono_small"])


def card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    title: str,
    accent: str = "#314150",
    fill: str | None = None,
) -> None:
    rounded(draw, box, fill or COLORS["panel"], accent, 9)
    draw.text((box[0] + 16, box[1] + 13), title, fill=COLORS["text"], font=FONTS["body_bold"])
    draw.line((box[0] + 15, box[1] + 42, box[2] - 15, box[1] + 42), fill="#23303d", width=1)


def app_shell(image: Image.Image, active: str = "Escalations") -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(image)
    draw_browser_frame(draw)
    content_top = UI_Y + 37
    side_x = UI_X + 1
    side_bottom = UI_Y + UI_H - 1
    draw.rectangle((side_x, content_top, UI_X + 184, side_bottom), fill=COLORS["sidebar"])
    draw.line((UI_X + 184, content_top, UI_X + 184, side_bottom), fill="#1d2a37")
    rounded(draw, (UI_X + 16, content_top + 15, UI_X + 44, content_top + 43), COLORS["mint"], None, 8)
    draw.text((UI_X + 22, content_top + 17), "S", fill="#0d211a", font=FONTS["body_bold"])
    draw.text((UI_X + 52, content_top + 17), "shiftline", fill="#e7edf3", font=font(17, True))
    label(draw, (UI_X + 17, content_top + 67), "Workspace", "#728397", 9)
    rounded(draw, (UI_X + 14, content_top + 84, UI_X + 170, content_top + 128), "#111d29", "#243444", 7)
    rounded(draw, (UI_X + 24, content_top + 94, UI_X + 48, content_top + 118), "#7767be", None, 6)
    draw.text((UI_X + 32, content_top + 97), "N", fill="#fff", font=FONTS["small"])
    draw.text((UI_X + 56, content_top + 92), "Northstar Systems", fill="#dce5ec", font=FONTS["tiny"])
    draw.text((UI_X + 56, content_top + 108), "Support & Reliability", fill="#768798", font=font(9))
    label(draw, (UI_X + 17, content_top + 150), "Navigation", "#728397", 9)
    nav_items = [("Overview", "▦"), ("Escalations", "▣"), ("Memory trail", "◷"), ("Memory replay", "✧"), ("Audit activity", "◇")]
    for index, (name, symbol) in enumerate(nav_items):
        y = content_top + 166 + index * 34
        if name == active:
            rounded(draw, (UI_X + 8, y, UI_X + 174, y + 29), "#173026", None, 6)
        draw.text((UI_X + 22, y + 6), symbol, fill=COLORS["mint"] if name == active else "#77889a", font=FONTS["body"])
        draw.text((UI_X + 49, y + 8), name, fill="#b6e9d7" if name == active else "#9ba9b7", font=FONTS["small"])
    draw.line((UI_X + 13, side_bottom - 60, UI_X + 169, side_bottom - 60), fill="#25313e")
    rounded(draw, (UI_X + 20, side_bottom - 43, UI_X + 46, side_bottom - 17), "#a87355", None, 13)
    draw.text((UI_X + 26, side_bottom - 38), "AM", fill="#24130f", font=font(9, True))
    draw.text((UI_X + 53, side_bottom - 42), "Alex Morgan", fill="#d8e1e9", font=FONTS["tiny"])
    draw.text((UI_X + 53, side_bottom - 27), "Escalation lead", fill="#788899", font=font(9))
    draw.rectangle((UI_X + 185, content_top, UI_X + UI_W - 1, content_top + 36), fill="#0c141e")
    draw.line((UI_X + 185, content_top + 36, UI_X + UI_W - 1, content_top + 36), fill="#202c38")
    draw.text((UI_X + 209, content_top + 12), "Escalations   ›   INC-2048", fill="#9cabb8", font=FONTS["tiny"])
    rounded(draw, (UI_X + UI_W - 205, content_top + 7, UI_X + UI_W - 36, content_top + 29), "#17291f", "#355443", 11)
    draw.ellipse((UI_X + UI_W - 194, content_top + 15, UI_X + UI_W - 189, content_top + 20), fill=COLORS["amber"])
    draw.text((UI_X + UI_W - 183, content_top + 12), "Local demo · not Hindsight", fill="#e3c98f", font=font(9))
    return draw


def app_content_start() -> tuple[int, int, int]:
    return UI_X + 207, UI_Y + 93, UI_X + UI_W - 24


def draw_incident_header(draw: ImageDraw.ImageDraw, show_actions: bool = False) -> None:
    x, y, right = app_content_start()
    label(draw, (x, y, right, y + 10), "●  Live escalation   /   Updated 8 min ago", "#aab9c5", 9)
    draw.ellipse((x, y + 2, x + 7, y + 9), fill="#e7a082")
    draw.text((x, y + 22), "Webhook deliveries are duplicating.", fill=COLORS["text"], font=FONTS["heading"])
    draw.text((x, y + 55), "INC-2048   ·   Acme Logistics   ·   Fictional demo customer", fill="#9aa9b7", font=FONTS["small"])
    rounded(draw, (right - 185, y + 18, right - 105, y + 47), "#111b26", "#334252", 6)
    draw.text((right - 170, y + 26), "P1 · HIGH", fill=COLORS["coral"], font=FONTS["mono_small"])
    rounded(draw, (right - 96, y + 18, right, y + 47), "#1d3029", "#3b634f", 6)
    draw.text((right - 82, y + 26), "Investigating", fill="#b8e9d2", font=font(10))


def draw_overview_panel(draw: ImageDraw.ImageDraw, kind: str, highlighted: bool = True) -> None:
    x, y, right = app_content_start()
    width = right - x
    top = y + 88
    card(draw, (x, top, right, top + 375), "Incident overview", "#2b3547")
    impact_y = top + 55
    rounded(draw, (x + 15, impact_y, right - 15, impact_y + 53), "#121e2a", "#263444", 6)
    draw.rectangle((x + 15, impact_y, x + 18, impact_y + 53), fill="#9885e5")
    label(draw, (x + 29, impact_y + 8), "Customer impact", "#9cabb7", 8)
    wrapped(
        draw,
        (x + 29, impact_y + 25),
        "Duplicate webhook events are reaching live orders and the fulfillment partner.",
        width - 58,
        font(11),
        "#cbd5de",
    )
    rows = [
        ("WHAT CHANGED", "Duplicates began after a webhook replay at 14:32 UTC.", "Support ticket INC-2048", COLORS["blue"]),
        ("CUSTOMER CONSTRAINT", "Signing secret rotation must wait until Friday.", "Customer call · 15:06 UTC", COLORS["amber"]),
        ("DO NOT REPEAT", "Replaying the batch made duplicate deliveries worse.", "On-call note · 15:24 UTC", COLORS["coral"]),
    ]
    selected = {"changed": 0, "constraint": 1, "failed": 2}.get(kind)
    for index, (heading, body, source, accent) in enumerate(rows):
        row_top = impact_y + 65 + index * 63
        draw.line((x + 14, row_top, right - 14, row_top), fill="#24313e")
        color = accent if selected == index and highlighted else "#97a6b2"
        label(draw, (x + 27, row_top + 9), heading, color, 9)
        draw.text((x + 27, row_top + 25), body, fill="#d0d9e1", font=FONTS["small"])
        draw.text((x + 27, row_top + 44), "↗  " + source, fill="#8798a6", font=font(9))
        if selected == index and highlighted:
            rounded(draw, (x + 19, row_top + 4, right - 20, row_top + 59), "#121b23", accent, 6)
            draw.text((x + 27, row_top + 9), heading, fill=accent, font=font(9, True))
            draw.text((x + 27, row_top + 25), body, fill="#e3eaf0", font=FONTS["small"])
            draw.text((x + 27, row_top + 44), "↗  " + source, fill="#afbdc7", font=font(9))
    rounded(draw, (x + 15, top + 340, right - 15, top + 370), "#101d23", "#273a3a", 5)
    draw.text((x + 27, top + 349), "SYNTHETIC SCENARIO   ·   SOURCE-LINKED HANDOFF", fill="#9fb8ab", font=FONTS["mono_small"])


def draw_brief_panel(draw: ImageDraw.ImageDraw, left: int, top: int, width: int) -> None:
    right = left + width
    rounded(draw, (left, top, right, top + 333), "#12211d", "#385344", 9)
    label(draw, (left + 17, top + 15), "●  Next shift brief", "#8fd5b7", 9)
    draw.text((left + 17, top + 38), "Take over with context.", fill="#ecf3ef", font=font(20, True))
    draw.text((left + 17, top + 66), "Evidence, constraints, and the next safe check.", fill="#9bb1a6", font=FONTS["tiny"])
    rounded(draw, (left + 15, top + 88, right - 15, top + 121), "#192920", "#324b3c", 6)
    draw.text((left + 26, top + 99), "4 memories recalled  ·  SOURCED", fill="#c1e6d3", font=font(10, True))
    sections = [
        ("SAFE NEXT CHECK", "Compare one delivery ID and idempotency key.", COLORS["mint"]),
        ("AVOID REPEATING", "Replay increased duplicate deliveries.", COLORS["coral"]),
        ("KEEP IN MIND", "Signing secret cannot rotate until Friday.", COLORS["amber"]),
    ]
    for index, (title, body, accent) in enumerate(sections):
        row_top = top + 132 + index * 53
        draw.line((left + 15, row_top, right - 15, row_top), fill="#2a3d34")
        label(draw, (left + 17, row_top + 8), title, accent, 8)
        wrapped(draw, (left + 17, row_top + 24), body, width - 32, font(10), "#d4e0d9", 2)
        draw.text((right - 46, row_top + 8), f"H-{index + 1:02}", fill="#89bc9f", font=FONTS["mono_small"])
    draw.text((left + 16, top + 300), "Suggestions are evidence — verify before acting.", fill="#91a49a", font=font(9))


def draw_incident_scene(image: Image.Image, scene: dict[str, str], scene_number: int) -> None:
    draw = app_shell(image)
    x, y, right = app_content_start()
    draw_incident_header(draw)
    kind = scene["kind"]

    if kind in {"overview", "changed", "constraint", "failed"}:
        draw_overview_panel(draw, kind, kind != "overview")
        rounded(draw, (x, y + 72, right, y + 104), "#211e18", "#5a4931", 6)
        draw.text((x + 12, y + 82), "SHIFT HANDOFF IN PROGRESS", fill="#edcc8b", font=FONTS["mono_small"])
        draw.text((x + 264, y + 82), "One customer constraint and a failed workaround need attention.", fill="#b9a582", font=FONTS["tiny"])
        if kind != "overview":
            color = {"changed": COLORS["blue"], "constraint": COLORS["amber"], "failed": COLORS["coral"]}[kind]
            message = {
                "changed": "TIMESTAMPED CHANGE  ·  STARTED AFTER THE REPLAY",
                "constraint": "CUSTOMER CONSTRAINT  ·  DO NOT REQUEST ROTATION BEFORE FRIDAY",
                "failed": "FAILED APPROACH  ·  DO NOT REPLAY THIS BATCH AGAIN",
            }[kind]
            rounded(draw, (right - 359, UI_Y + UI_H - 57, right - 12, UI_Y + UI_H - 21), "#111922", color, 7)
            draw.text((right - 344, UI_Y + UI_H - 45), message, fill=color, font=FONTS["mono_small"])
        return

    draw_overview_panel(draw, "overview", False)
    brief_x = x + (right - x) // 2 + 6
    draw_brief_panel(draw, brief_x, y + 83, right - brief_x)
    if kind == "brief":
        rounded(draw, (brief_x + 13, y + 83 + 125, right - 13, y + 83 + 174), "#1b271e", COLORS["mint"], 6)
        rounded(draw, (brief_x + 13, y + 83 + 178, right - 13, y + 83 + 227), "#271d20", COLORS["coral"], 6)
        rounded(draw, (brief_x + 13, y + 83 + 231, right - 13, y + 83 + 280), "#272419", COLORS["amber"], 6)


def draw_compare_scene(image: Image.Image) -> None:
    draw = app_shell(image, "Memory replay")
    x, y, right = app_content_start()
    label(draw, (x, y), "Memory replay  /  Fresh session comparison", "#9cb0bf", 9)
    draw.text((x, y + 20), "Same question. Different context.", fill=COLORS["text"], font=FONTS["heading"])
    draw.text((x, y + 52), "What should I know before taking over Acme Logistics INC-2048?", fill="#a8b6c2", font=FONTS["small"])
    gap = 14
    col_w = (right - x - gap) // 2
    top = y + 87
    card(draw, (x, top, x + col_w, top + 287), "Without memory", "#334151", "#111a25")
    label(draw, (x + 17, top + 54), "FRESH SESSION", "#93a1ad", 8)
    wrapped(draw, (x + 17, top + 81), "I do not have previous shift context. I can see there is a webhook escalation, but I do not know what the customer constraint was.", col_w - 36, FONTS["body"], "#bcc9d4", 7)
    draw.text((x + 17, top + 205), "No source history available", fill="#8493a0", font=FONTS["tiny"])

    right_x = x + col_w + gap
    card(draw, (right_x, top, right, top + 287), "Hindsight memory", "#44654e", "#13221e")
    label(draw, (right_x + 17, top + 54), "WHEN HINDSIGHT IS CONNECTED", "#83cfaf", 8)
    facts = [
        ("FAILED APPROACH", "Replay increased duplicate deliveries.", "On-call note · 15:24 UTC", COLORS["coral"]),
        ("CUSTOMER CONSTRAINT", "Signing secret cannot rotate until Friday.", "Customer call · 15:06 UTC", COLORS["amber"]),
        ("INCIDENT CHANGE", "Duplicates started after replay at 14:32.", "Support ticket INC-2048", COLORS["blue"]),
    ]
    for index, (heading, body, source, accent) in enumerate(facts):
        row_y = top + 75 + index * 62
        rounded(draw, (right_x + 14, row_y, right - 14, row_y + 54), "#17241f", "#314738", 5)
        label(draw, (right_x + 24, row_y + 7), heading, accent, 7)
        draw.text((right_x + 24, row_y + 21), body, fill="#d2e0d8", font=font(10))
        draw.text((right_x + 24, row_y + 38), source, fill="#91aa9a", font=font(8))
    rounded(draw, (x, top + 302, right, top + 329), "#211d16", "#5b492b", 5)
    draw.text((x + 11, top + 310), "Current run: local demo memory · not Hindsight", fill="#e1c18a", font=FONTS["tiny"])


def draw_outcome_scene(image: Image.Image) -> None:
    draw = app_shell(image)
    x, y, right = app_content_start()
    draw_incident_header(draw)
    draw_overview_panel(draw, "overview", False)
    brief_x = x + (right - x) // 2 + 6
    draw_brief_panel(draw, brief_x, y + 83, right - brief_x)
    top = y + 83 + 340
    card(draw, (brief_x, top, right, top + 91), "Close the loop", "#394b59")
    options = [("Worked", COLORS["mint"]), ("Failed", COLORS["coral"]), ("Unverified", COLORS["amber"])]
    button_w = (right - brief_x - 42) // 3
    for index, (text, color) in enumerate(options):
        left = brief_x + 15 + index * (button_w + 5)
        rounded(draw, (left, top + 50, left + button_w, top + 72), "#111b24", color if index == 0 else "#344250", 5)
        draw.text((left + 8, top + 54), text, fill=color if index == 0 else "#a1adb7", font=FONTS["tiny"])
    rounded(draw, (x, y + 428, x + 216, y + 463), "#151f29", "#30404f", 6)
    draw.text((x + 11, y + 439), "Ask about the handoff   ↗", fill="#a6d9cc", font=FONTS["small"])
    rounded(draw, (x + 230, y + 428, x + 522, y + 463), "#192a21", "#3a5c45", 6)
    draw.text((x + 242, y + 439), "Human-confirmed outcome → retained", fill="#b5dfc7", font=FONTS["tiny"])


def draw_title_scene(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    for x in range(WIDTH):
        for y in range(0, 500, 5):
            dx = (x - 1050) / 780
            dy = (y - 100) / 550
            glow = max(0, 1 - math.sqrt(dx * dx + dy * dy)) * .17
            base = np.array(rgb("#101d29"), dtype=float)
            accent = np.array(rgb("#284938"), dtype=float)
            value = (base * (1 - glow) + accent * glow).astype(np.uint8)
            draw.line((x, y, x, y + 5), fill=tuple(value.tolist()))
    rounded(draw, (60, 58, 281, 91), "#15281f", "#355b47", 14)
    draw.ellipse((76, 70, 84, 78), fill=COLORS["mint"])
    draw.text((94, 67), "SHIFTLINE  ·  PRODUCT WALKTHROUGH", fill="#b5e4d0", font=FONTS["mono_small"])
    draw.text((60, 169), "A better shift starts", fill=COLORS["text"], font=FONTS["hero"])
    draw.text((60, 247), "with", fill=COLORS["text"], font=FONTS["hero"])
    draw.text((60, 325), "context.", fill=COLORS["mint"], font=FONTS["hero"])
    draw.text((64, 438), "Carry the context. Not the whole conversation.", fill="#b2c1cb", font=FONTS["medium"])
    rounded(draw, (824, 161, 1172, 491), "#111c26", "#2a3c49", 12)
    label(draw, (854, 194), "NEXT SHIFT  ·  INC-2048", "#a6c6b3", 9)
    draw.text((852, 227), "Before you", fill="#b3c1cb", font=FONTS["heading"])
    draw.text((852, 258), "touch anything…", fill="#eff3f5", font=font(25, True))
    draw.line((854, 309, 1140, 309), fill="#314239")
    facts = [
        ("DO NOT REPEAT", "Replay made it worse", COLORS["coral"]),
        ("CUSTOMER LIMIT", "Wait until Friday", COLORS["amber"]),
        ("SAFE NEXT CHECK", "Verify idempotency key", COLORS["mint"]),
    ]
    for i, (heading, detail, color) in enumerate(facts):
        py = 330 + i * 48
        draw.ellipse((856, py + 2, 864, py + 10), fill=color)
        draw.text((875, py), heading, fill=color, font=FONTS["mono_small"])
        draw.text((875, py + 17), detail, fill="#d2dce3", font=FONTS["small"])
    draw.text((62, 561), "A CUSTOMER-SUPPORT HANDOFF BUILT AROUND PERSISTENT CONTEXT", fill="#7f928f", font=FONTS["mono_small"])


def draw_end_scene(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    rounded(draw, (60, 54, 266, 88), "#162921", "#375e4a", 15)
    draw.ellipse((75, 67, 83, 75), fill=COLORS["mint"])
    draw.text((94, 64), "SHIFTLINE  ·  THE TAKEAWAY", fill="#b4e4d0", font=FONTS["mono_small"])
    draw.text((61, 155), "Carry context.", fill=COLORS["text"], font=font(54, True))
    draw.text((61, 222), "Keep people in control.", fill=COLORS["mint"], font=font(54, True))
    draw.text((66, 326), "A safe handoff remembers the evidence,", fill="#bdcbd4", font=FONTS["heading"])
    draw.text((66, 360), "the failed fix, and what still needs checking.", fill="#bdcbd4", font=FONTS["heading"])
    rounded(draw, (65, 433, 1126, 501), "#201d17", "#64502f", 9)
    draw.text((85, 450), "DEMO MODE", fill=COLORS["amber"], font=FONTS["mono"])
    draw.text((205, 447), "This video uses local demo memory — not a live Hindsight service.", fill="#dfd3b8", font=FONTS["small"])
    draw.text((205, 470), "Configure Hindsight for persistent, cross-session retain · recall · reflect.", fill="#b5a989", font=FONTS["tiny"])
    draw.text((67, 554), "SHIFTLINE    ·    CUSTOMER ESCALATION CONTEXT THAT SURVIVES THE SHIFT", fill="#839791", font=FONTS["mono_small"])


def fit_caption(draw: ImageDraw.ImageDraw, text: str) -> list[str]:
    face = font(18, True)
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=face)[2] > 1130:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:2]


def scene_frame(scene: dict[str, str], index: int) -> Image.Image:
    image = new_canvas()
    if scene["kind"] == "title":
        draw_title_scene(image)
    elif scene["kind"] == "end":
        draw_end_scene(image)
    else:
        draw_incident_scene(image, scene, index)

    draw = ImageDraw.Draw(image)
    draw.line((56, 610, WIDTH - 56, 610), fill="#283642", width=1)
    lines = fit_caption(draw, scene["narration"])
    for line_index, line in enumerate(lines):
        draw.text((59, 624 + line_index * 25), line, fill="#ecf2f4", font=font(17, True))
    draw.text((60, 692), "ILLUSTRATIVE UI WALKTHROUGH  ·  FICTIONAL DATA  ·  LOCAL DEMO MEMORY", fill="#71838e", font=font(8, mono=True))
    draw.text((WIDTH - 98, 688), f"{index:02d} / {len(SCENES):02d}", fill="#8da29d", font=FONTS["mono_small"])
    return image


def make_voice_clip(text: str, output: Path) -> None:
    encoded = subprocess.list2cmdline([text])
    path_literal = str(output).replace("'", "''")
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice('Microsoft Zira Desktop'); $s.Rate = -1; $s.Volume = 94; "
        f"$s.SetOutputToWaveFile('{path_literal}'); $s.Speak({encoded}); "
        "$s.SetOutputToNull(); $s.Dispose()"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not output.exists() or output.stat().st_size < 64:
        raise RuntimeError(
            "Windows text-to-speech failed: " + (result.stderr.strip() or result.stdout.strip())
        )


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, millis_part = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d},{millis_part:03d}"


def compose_audio(voice_paths: list[Path], output: Path) -> tuple[list[tuple[float, float]], wave._wave_params]:
    with wave.open(str(voice_paths[0]), "rb") as sample:
        params = sample.getparams()
    if params.sampwidth != 2:
        raise RuntimeError(f"Expected 16-bit synthesized speech, got {params.sampwidth * 8}-bit audio.")

    timings: list[tuple[float, float]] = []
    frame_rate = params.framerate
    gap_frames = int(frame_rate * .38)
    with wave.open(str(output), "wb") as destination:
        destination.setnchannels(params.nchannels)
        destination.setsampwidth(params.sampwidth)
        destination.setframerate(frame_rate)
        cursor = 0
        for path in voice_paths:
            with wave.open(str(path), "rb") as source:
                current = source.getparams()
                if (
                    current.framerate != frame_rate
                    or current.nchannels != params.nchannels
                    or current.sampwidth != params.sampwidth
                ):
                    raise RuntimeError("Speech clips do not share the same audio format.")
                audio = source.readframes(source.getnframes())
            start = cursor / frame_rate
            duration = len(audio) // params.nchannels // params.sampwidth / frame_rate
            destination.writeframesraw(audio)
            timings.append((start, start + duration))
            silence = b"\0" * gap_frames * params.nchannels * params.sampwidth
            destination.writeframesraw(silence)
            cursor += len(audio) // (params.sampwidth * params.nchannels) + gap_frames
    return timings, params


def create_srt(timings: list[tuple[float, float]]) -> str:
    entries = []
    for index, (scene, timing) in enumerate(zip(SCENES, timings), start=1):
        start, end = timing
        caption = textwrap.fill(scene["narration"], width=82)
        entries.append(f"{index}\n{srt_timestamp(start)} --> {srt_timestamp(end)}\n{caption}")
    return "\n\n".join(entries) + "\n"


def transition_frames(
    previous: np.ndarray,
    current: np.ndarray,
    count: int,
) -> list[np.ndarray]:
    generated: list[np.ndarray] = []
    for step in range(1, count + 1):
        amount = step / count
        frame = np.clip(previous * (1 - amount) + current * amount, 0, 255).astype(np.uint8)
        generated.append(frame)
    return generated


def main() -> None:
    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    with tempfile.TemporaryDirectory(prefix="shiftline_video_") as temporary:
        temp_dir = Path(temporary)
        voice_paths: list[Path] = []
        for index, scene in enumerate(SCENES, start=1):
            output = temp_dir / f"voice_{index:02d}.wav"
            make_voice_clip(scene["narration"], output)
            voice_paths.append(output)

        audio_path = temp_dir / "narration.wav"
        timings, audio_params = compose_audio(voice_paths, audio_path)
        SUBTITLES.write_text(
            "\ufeff" + create_srt(timings),
            encoding="utf-8",
        )

        target = temp_dir / "visual_track.mp4"
        writer = imageio.get_writer(
            target,
            fps=FPS,
            codec="libx264",
            quality=8,
            macro_block_size=1,
            pixelformat="yuv420p",
            ffmpeg_log_level="error",
            output_params=["-movflags", "+faststart"],
        )
        crossfade_count = round(.42 * FPS)
        try:
            previous: np.ndarray | None = None
            for index, (scene, timing) in enumerate(zip(SCENES, timings), start=1):
                rendered = scene_frame(scene, index)
                current = np.asarray(rendered, dtype=np.uint8)
                audio_start, audio_end = timing
                hold_seconds = audio_end - audio_start + .38
                if index > 1:
                    hold_seconds -= crossfade_count / FPS
                    assert previous is not None
                    for frame in transition_frames(previous, current, crossfade_count):
                        writer.append_data(frame)
                for _ in range(max(1, round(hold_seconds * FPS))):
                    writer.append_data(current)
                previous = current
                print(f"Rendered scene {index}/{len(SCENES)}: {scene['title']}")
        finally:
            writer.close()

        ffmpeg_command = [
            str(ffmpeg),
            "-y",
            "-i",
            str(target),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            str(audio_params.framerate),
            "-shortest",
            "-movflags",
            "+faststart",
            str(OUTPUT),
        ]
        result = subprocess.run(ffmpeg_command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError("Could not package the video: " + result.stderr[-3000:])

    size_mb = OUTPUT.stat().st_size / (1024 * 1024)
    print(f"Video: {OUTPUT} ({size_mb:.1f} MB)")
    print(f"Captions: {SUBTITLES}")
    print(f"Duration: {timings[-1][1] + .38:.1f} seconds")


if __name__ == "__main__":
    main()
