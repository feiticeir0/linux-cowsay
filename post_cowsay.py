#!/usr/bin/env python3
"""Generate a colored cowsay image and post it to Bluesky."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
from urllib import error, request

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
DEFAULT_GENERATOR = "fortune | cowsay | lolcat -f"
BLUESKY_PDS = "https://bsky.social"
DEFAULT_POST_TEXT = "cowsay"
DEFAULT_BG = (11, 14, 20)
DEFAULT_FG = (238, 238, 238)
DEFAULT_FONT_SIZE = 18

ColorLine = List[Tuple[str, Tuple[int, int, int]]]


def load_env_file(path: Path) -> Dict[str, str]:
    """Parse a simple KEY=VALUE .env file without external dependencies."""
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_config() -> Dict[str, str]:
    """Load config from environment first, then fallback to local .env file."""
    env_path = Path(__file__).with_name(".env")
    file_values = load_env_file(env_path)
    config = {
        "identifier": os.getenv("BSKY_IDENTIFIER", file_values.get("BSKY_IDENTIFIER", "")),
        "app_password": os.getenv("BSKY_APP_PASSWORD", file_values.get("BSKY_APP_PASSWORD", "")),
        "generator_cmd": os.getenv("COWSAY_GENERATOR", file_values.get("COWSAY_GENERATOR", DEFAULT_GENERATOR)),
        "pds_host": os.getenv("BSKY_PDS_HOST", file_values.get("BSKY_PDS_HOST", BLUESKY_PDS)),
        "post_text": os.getenv("BSKY_POST_TEXT", file_values.get("BSKY_POST_TEXT", DEFAULT_POST_TEXT)),
        "font_path": os.getenv("BSKY_FONT_PATH", file_values.get("BSKY_FONT_PATH", "")),
        "font_size": os.getenv("BSKY_FONT_SIZE", file_values.get("BSKY_FONT_SIZE", str(DEFAULT_FONT_SIZE))),
    }
    missing = [name for name, value in config.items() if name in ("identifier", "app_password") and not value]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing required config: {names}. Set .env or environment variables.")
    return config


def run_generator(command: str) -> str:
    """Run fortune/cowsay/lolcat pipeline and return ANSI-colored text output."""
    normalized = command
    if re.search(r"\blolcat\b", command) and not re.search(r"\blolcat\b\s+(-f|--force)\b", command):
        normalized = re.sub(r"\blolcat\b", "lolcat -f", command, count=1)
    try:
        proc = subprocess.run(
            ["bash", "-lc", normalized],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "TERM": os.getenv("TERM", "xterm-256color"),
                "COLORTERM": os.getenv("COLORTERM", "truecolor"),
                "CLICOLOR_FORCE": "1",
                "FORCE_COLOR": "3",
            },
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise RuntimeError(f"Generator command failed: {stderr or 'unknown error'}") from exc
    output = proc.stdout
    if not output:
        raise RuntimeError("Generator command produced empty output.")
    if "\x1b[" not in output and "lolcat" in normalized:
        raise RuntimeError("No ANSI color codes produced by lolcat. Check if lolcat is installed and supports -f.")
    return output


def ansi_256_to_rgb(code: int) -> Tuple[int, int, int]:
    """Convert an ANSI 256-color index into an RGB tuple."""
    if code < 16:
        basic = [
            (0, 0, 0),
            (128, 0, 0),
            (0, 128, 0),
            (128, 128, 0),
            (0, 0, 128),
            (128, 0, 128),
            (0, 128, 128),
            (192, 192, 192),
            (128, 128, 128),
            (255, 0, 0),
            (0, 255, 0),
            (255, 255, 0),
            (0, 0, 255),
            (255, 0, 255),
            (0, 255, 255),
            (255, 255, 255),
        ]
        return basic[code]
    if code <= 231:
        idx = code - 16
        r = idx // 36
        g = (idx % 36) // 6
        b = idx % 6
        levels = [0, 95, 135, 175, 215, 255]
        return (levels[r], levels[g], levels[b])
    gray = 8 + (code - 232) * 10
    return (gray, gray, gray)


def parse_ansi_lines(ansi_text: str) -> List[ColorLine]:
    """Parse ANSI escape sequences into per-character colorized lines."""
    lines: List[ColorLine] = [[]]
    color = DEFAULT_FG
    i = 0
    while i < len(ansi_text):
        ch = ansi_text[i]
        if ch == "\x1b" and i + 1 < len(ansi_text) and ansi_text[i + 1] == "[":
            end = ansi_text.find("m", i + 2)
            if end == -1:
                i += 1
                continue
            raw_params = ansi_text[i + 2 : end]
            params = [int(p) if p else 0 for p in raw_params.split(";")]
            j = 0
            while j < len(params):
                p = params[j]
                if p == 0:
                    color = DEFAULT_FG
                elif p in (39,):
                    color = DEFAULT_FG
                elif 30 <= p <= 37:
                    color = ansi_256_to_rgb(p - 30)
                elif 90 <= p <= 97:
                    color = ansi_256_to_rgb(p - 90 + 8)
                elif p == 38 and j + 1 < len(params):
                    mode = params[j + 1]
                    if mode == 5 and j + 2 < len(params):
                        color = ansi_256_to_rgb(params[j + 2])
                        j += 2
                    elif mode == 2 and j + 4 < len(params):
                        color = (params[j + 2], params[j + 3], params[j + 4])
                        j += 4
                j += 1
            i = end + 1
            continue
        if ch == "\r":
            i += 1
            continue
        if ch == "\n":
            lines.append([])
        else:
            lines[-1].append((ch, color))
        i += 1
    while lines and not lines[-1]:
        lines.pop()
    return lines or [[(" ", DEFAULT_FG)]]


def plain_text_from_ansi(ansi_text: str) -> str:
    return ANSI_RE.sub("", ansi_text).strip()


def load_monospace_font(image_font_module, requested_path: str, font_size: int):
    """Load a monospace TTF font from configured path or common Linux defaults."""
    candidates = []
    if requested_path:
        candidates.append(requested_path)
    candidates.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
            "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        ]
    )
    for path in candidates:
        if path and Path(path).exists():
            return image_font_module.truetype(path, font_size)
    raise RuntimeError(
        "No monospace TTF font found. Install DejaVu Sans Mono or set BSKY_FONT_PATH."
    )


def render_png(ansi_text: str, out_path: Path, font_path: str, font_size: int) -> None:
    """Render ANSI-colored ASCII art into a PNG while preserving monospaced layout."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow is required. Install with: pip install pillow") from exc

    lines = parse_ansi_lines(ansi_text)
    font = load_monospace_font(ImageFont, font_path, font_size)
    left, top, right, bottom = font.getbbox("M")
    char_w = max(1, right - left)
    line_h = max(1, bottom - top) + 4

    width_chars = max(len(line) for line in lines)
    height_lines = len(lines)
    pad = 20
    width = max(200, pad * 2 + width_chars * char_w)
    height = max(120, pad * 2 + height_lines * line_h)

    img = Image.new("RGB", (width, height), DEFAULT_BG)
    draw = ImageDraw.Draw(img)
    y = pad
    for line in lines:
        line_len = len(line)
        idx = 0
        while idx < line_len:
            # Draw runs of same color together to keep alignment stable and faster.
            run_color = line[idx][1]
            start = idx
            while idx < line_len and line[idx][1] == run_color:
                idx += 1
            run_text = "".join(ch for ch, _ in line[start:idx])
            draw.text((pad + start * char_w, y), run_text, font=font, fill=run_color)
        y += line_h
    img.save(out_path, format="PNG", optimize=True)


def post_json(url: str, payload: dict, headers: Dict[str, str] | None = None) -> dict:
    """POST JSON and decode JSON response with useful error messages."""
    encoded = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = request.Request(url=url, data=encoded, headers=req_headers, method="POST")
    try:
        with request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc}") from exc


def post_bytes(url: str, payload: bytes, content_type: str, headers: Dict[str, str] | None = None) -> dict:
    """POST raw bytes and decode JSON response."""
    req_headers = {"Content-Type": content_type}
    if headers:
        req_headers.update(headers)
    req = request.Request(url=url, data=payload, headers=req_headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error calling {url}: {exc}") from exc


def create_session(pds_host: str, identifier: str, app_password: str) -> dict:
    """Create an authenticated AT Protocol session."""
    return post_json(
        f"{pds_host}/xrpc/com.atproto.server.createSession",
        {"identifier": identifier, "password": app_password},
    )


def upload_blob(pds_host: str, jwt: str, image_bytes: bytes) -> dict:
    """Upload PNG bytes and return Bluesky blob descriptor."""
    uploaded = post_bytes(
        f"{pds_host}/xrpc/com.atproto.repo.uploadBlob",
        image_bytes,
        content_type="image/png",
        headers={"Authorization": f"Bearer {jwt}"},
    )
    blob = uploaded.get("blob")
    if not blob:
        raise RuntimeError("uploadBlob response missing blob field.")
    return blob


def create_post(pds_host: str, did: str, jwt: str, text: str, image_blob: dict, alt_text: str) -> dict:
    """Publish post with image embed and alt text."""
    payload = {
        "repo": did,
        "collection": "app.bsky.feed.post",
        "record": {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "embed": {
                "$type": "app.bsky.embed.images",
                "images": [
                    {
                        "alt": alt_text[:1000],
                        "image": image_blob,
                    }
                ],
            },
        },
    }
    return post_json(
        f"{pds_host}/xrpc/com.atproto.repo.createRecord",
        payload,
        headers={"Authorization": f"Bearer {jwt}"},
    )


def main() -> int:
    """Entrypoint: generate image, upload blob, then publish post."""
    try:
        cfg = get_config()
        ansi_output = run_generator(cfg["generator_cmd"])
        plain_text = plain_text_from_ansi(ansi_output)
        png_path = Path(__file__).with_name("last_cowsay.png")
        font_size = int(cfg["font_size"])
        render_png(ansi_output, png_path, cfg["font_path"], font_size)
        image_bytes = png_path.read_bytes()
        session = create_session(cfg["pds_host"], cfg["identifier"], cfg["app_password"])
        did = session["did"]
        jwt = session["accessJwt"]
        blob = upload_blob(cfg["pds_host"], jwt, image_bytes)
        result = create_post(cfg["pds_host"], did, jwt, cfg["post_text"], blob, plain_text)
        uri = result.get("uri", "(no uri returned)")
        print(f"Posted successfully: {uri}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
