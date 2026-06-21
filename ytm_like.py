#!/usr/bin/env python3
"""Like the exact YouTube video currently reported by a browser/player."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request as UrlRequest, urlopen

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
DESKTOP_API_BASE = "http://127.0.0.1:26538"
DESKTOP_EXE = Path.home() / "AppData/Local/Programs/youtube-music/YouTube Music.exe"


def app_dir() -> Path:
    root = os.environ.get("YTM_LIKE_HOME")
    path = Path(root) if root else Path.home() / ".ytm-like"
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path() -> Path:
    return app_dir() / "current.json"


def command_path() -> Path:
    return app_dir() / "browser-command.json"


def token_path() -> Path:
    return app_dir() / "token.json"


def secret_path() -> Path:
    return app_dir() / "reporter-token"


def desktop_token_path() -> Path:
    return app_dir() / "desktop-api-token"


def reporter_token() -> str:
    path = secret_path()
    if not path.exists():
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text(encoding="utf-8").strip()


def resolve_client_secrets(path: Path) -> Path:
    if path.is_file():
        return path
    if path == Path("client_secret.json"):
        candidates = sorted(Path.cwd().glob("client_secret*.json"))
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise RuntimeError("Multiple client_secret*.json files found; use --client-secrets")
    raise RuntimeError(f"OAuth client file not found: {path}")


def validate_desktop_client(path: Path) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid OAuth client JSON: {path}") from exc
    if "installed" not in payload:
        kind = "Web application" if "web" in payload else "unknown"
        raise RuntimeError(
            f"OAuth client type is {kind}; create a Desktop app OAuth client and replace {path.name}"
        )


def extract_video_id(value: str | None) -> str | None:
    if not value:
        return None
    if VIDEO_ID_RE.fullmatch(value):
        return value
    parsed = urlparse(value)
    host = parsed.hostname or ""
    candidate = None
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [None])[0]
        elif parsed.path.startswith(("/shorts/", "/live/", "/embed/")):
            candidate = parsed.path.split("/")[2]
    return candidate if candidate and VIDEO_ID_RE.fullmatch(candidate) else None


@dataclass
class NowPlaying:
    video_id: str
    title: str = ""
    artist: str = ""
    source: str = "unknown"
    playing: bool = True
    reported_at: float = 0.0
    position_ms: int = 0

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "NowPlaying":
        video_id = extract_video_id(str(payload.get("videoId") or payload.get("url") or ""))
        if not video_id:
            raise ValueError("A valid 11-character YouTube videoId or URL is required")
        return cls(
            video_id=video_id,
            title=str(payload.get("title") or "")[:500],
            artist=str(payload.get("artist") or "")[:500],
            source=str(payload.get("source") or "reporter")[:100],
            playing=bool(payload.get("playing", True)),
            reported_at=time.time(),
            position_ms=max(0, int(payload.get("positionMs") or 0)),
        )


def save_current(item: NowPlaying) -> None:
    temporary = state_path().with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(item), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(state_path())


def save_browser_command(action: str, item: NowPlaying) -> dict[str, Any]:
    command = {
        "id": secrets.token_urlsafe(12),
        "action": action,
        "videoId": item.video_id,
        "createdAt": time.time(),
    }
    temporary = command_path().with_suffix(".tmp")
    temporary.write_text(json.dumps(command), encoding="utf-8")
    temporary.replace(command_path())
    return command


def take_browser_command(video_id: str) -> dict[str, Any] | None:
    try:
        command = json.loads(command_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if time.time() - float(command.get("createdAt", 0)) > 15:
        command_path().unlink(missing_ok=True)
        return None
    if command.get("videoId") != video_id:
        return None
    try:
        command_path().unlink()
    except OSError:
        return None
    return command


def windows_desktop_running() -> bool:
    if sys.platform != "win32" or not DESKTOP_EXE.is_file():
        return False
    command = (
        "$target='" + str(DESKTOP_EXE).replace("'", "''") + "';"
        "$count=@(Get-CimInstance Win32_Process -Filter \"Name='YouTube Music.exe'\" "
        "-ErrorAction SilentlyContinue | Where-Object {$_.ExecutablePath -eq $target}).Count;"
        "Write-Output $count"
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=4,
            check=False,
            creationflags=creation_flags,
        )
        return result.returncode == 0 and int(result.stdout.strip() or "0") > 0
    except (FileNotFoundError, ValueError, subprocess.SubprocessError):
        return False


def _desktop_token() -> str:
    environment_token = os.environ.get("YTM_DESKTOP_TOKEN", "").strip()
    if environment_token:
        return environment_token
    try:
        return desktop_token_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _authorize_desktop() -> str:
    request = UrlRequest(f"{DESKTOP_API_BASE}/auth/ytm-like-script", data=b"", method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("YouTube Music Desktop API authorization was denied or failed") from exc
    token = str(payload.get("accessToken") or "")
    if not token:
        raise RuntimeError("YouTube Music Desktop API returned no access token")
    desktop_token_path().write_text(token, encoding="utf-8")
    try:
        desktop_token_path().chmod(0o600)
    except OSError:
        pass
    return token


def _desktop_request(path: str, method: str = "GET", authorize: bool = True) -> tuple[int, Any]:
    token = _desktop_token()

    def send(access_token: str) -> tuple[int, Any]:
        headers = {"Accept": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        request = UrlRequest(
            f"{DESKTOP_API_BASE}{path}",
            data=b"" if method == "POST" else None,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=4) as response:
                status = response.status
                body = response.read()
        except HTTPError as exc:
            if exc.code == 401:
                return 401, None
            raise RuntimeError(f"YouTube Music Desktop API returned HTTP {exc.code} for {path}") from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Cannot reach YouTube Music Desktop API at {DESKTOP_API_BASE}") from exc
        if not body:
            return status, None
        try:
            return status, json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"YouTube Music Desktop API returned invalid JSON for {path}") from exc

    status, payload = send(token)
    if status == 401 and authorize:
        status, payload = send(_authorize_desktop())
    if status == 401:
        raise RuntimeError("YouTube Music Desktop API authorization is required")
    return status, payload


def windows_desktop_current(require_playing: bool = True) -> NowPlaying:
    status, payload = _desktop_request("/api/v1/song")
    if status == 204 or not isinstance(payload, dict):
        raise RuntimeError("YouTube Music Desktop API reports no current song")
    video_id = extract_video_id(str(payload.get("videoId") or payload.get("url") or ""))
    if not video_id:
        raise RuntimeError("YouTube Music Desktop API returned no valid videoId")
    item = NowPlaying(
        video_id=video_id,
        title=str(payload.get("title") or "")[:500],
        artist=str(payload.get("artist") or "")[:500],
        source="windows-youtube-music-api",
        playing=not bool(payload.get("isPaused", False)),
        reported_at=time.time(),
        position_ms=max(0, int(float(payload.get("elapsedSeconds") or 0) * 1000)),
    )
    if require_playing and not item.playing:
        raise RuntimeError("YouTube Music Desktop current song is paused")
    return item


def windows_desktop_like(expected_video_id: str) -> str:
    before = windows_desktop_current()
    if before.video_id != expected_video_id:
        raise RuntimeError("Current desktop song changed before Like; refusing to rate the wrong song")
    _, state_payload = _desktop_request("/api/v1/like-state")
    state = str((state_payload or {}).get("state") or "")
    if state != "LIKE":
        status, _ = _desktop_request("/api/v1/like", method="POST")
        if status != 204:
            raise RuntimeError(f"YouTube Music Desktop Like returned HTTP {status}")
        for _ in range(10):
            time.sleep(0.2)
            _, state_payload = _desktop_request("/api/v1/like-state")
            state = str((state_payload or {}).get("state") or "")
            if state == "LIKE":
                break
    after = windows_desktop_current(require_playing=False)
    if after.video_id != expected_video_id:
        raise RuntimeError("Desktop song changed while setting Like; result cannot be attributed safely")
    if state != "LIKE":
        raise RuntimeError(f"YouTube Music Desktop did not confirm Like; state is {state or 'unknown'}")
    return "like"


def windows_desktop_control(action: str) -> NowPlaying:
    endpoints = {
        "previous": "/api/v1/previous",
        "next": "/api/v1/next",
        "play-pause": "/api/v1/toggle-play",
    }
    before = windows_desktop_current(require_playing=False)
    status, _ = _desktop_request(endpoints[action], method="POST")
    if status != 204:
        raise RuntimeError(f"YouTube Music Desktop control returned HTTP {status}")
    for _ in range(20):
        time.sleep(0.2)
        after = windows_desktop_current(require_playing=False)
        if action == "play-pause":
            changed = after.playing != before.playing
        elif action == "previous":
            changed = after.video_id != before.video_id or (
                before.position_ms > 1500 and after.position_ms < before.position_ms - 1000
            )
        else:
            changed = after.video_id != before.video_id
        if changed:
            return after
    raise RuntimeError(f"YouTube Music Desktop did not confirm {action}")


def _adb_devices() -> list[str]:
    adb = shutil.which("adb")
    if not adb:
        return []
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [adb, "devices"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            check=False,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    devices = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            devices.append(fields[0])
    # Prefer an explicit host:port serial over duplicate mDNS aliases.
    return sorted(set(devices), key=lambda value: (":" not in value, value))


def _adb_broadcast(serial: str, action: str) -> tuple[int, str]:
    adb = shutil.which("adb")
    if not adb:
        raise RuntimeError("adb is not installed")
    component = "com.asuma.ytmsessiondiagnostic/.ShellCommandReceiver"
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                adb, "-s", serial, "shell", "am", "broadcast", "-W",
                "-a", f"com.asuma.ytmsessiondiagnostic.{action}",
                "-n", component,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            check=False,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Wear OS ADB command failed for {serial}") from exc
    output = result.stdout + "\n" + result.stderr
    match = re.search(r'Broadcast completed: result=(-?\d+)(?:, data="([^"]*)")?', output)
    if result.returncode != 0 or not match:
        raise RuntimeError(f"Wear OS diagnostic receiver unavailable on {serial}")
    return int(match.group(1)), match.group(2) or ""


def _parse_wear_status(data: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(data, keep_blank_values=True).items()}


def wear_adb_status(serial: str, require_playing: bool = True) -> NowPlaying | None:
    try:
        result, data = _adb_broadcast(serial, "STATUS_CURRENT")
    except RuntimeError:
        return None
    fields = _parse_wear_status(data)
    has_session = fields.get("session") == "1" or fields.get("playing") == "1"
    playing = fields.get("playing") == "1"
    if result == 0 and has_session and (playing or not require_playing):
        return NowPlaying(
            video_id="",
            title=fields.get("title", "")[:500],
            artist=fields.get("artist", "")[:500],
            source=f"wearos-adb:{serial}",
            playing=playing,
            reported_at=time.time(),
            position_ms=max(0, int(fields.get("positionMs", "0") or 0)),
        )
    return None


def wear_adb_current(require_playing: bool = True) -> NowPlaying | None:
    for serial in _adb_devices():
        item = wear_adb_status(serial, require_playing=require_playing)
        if item:
            return item
    return None


def wear_adb_like(serial: str, expected_title: str, expected_artist: str) -> str:
    status_result, status_data = _adb_broadcast(serial, "STATUS_CURRENT")
    before = _parse_wear_status(status_data)
    if status_result != 0 or before.get("playing") != "1":
        raise RuntimeError("YouTube Music is not playing on the Wear OS device")
    if before.get("title", "") != expected_title or before.get("artist", "") != expected_artist:
        raise RuntimeError("Wear OS song changed before Like; refusing to rate the wrong song")
    if before.get("liked") == "1":
        return "like"
    result, data = _adb_broadcast(serial, "LIKE_CURRENT")
    if result != 0 or not data.startswith(("like_notification_action_sent:", "already_liked:")):
        raise RuntimeError(f"Wear OS Like failed: {data or 'receiver error ' + str(result)}")
    for _ in range(10):
        time.sleep(0.25)
        status_result, status_data = _adb_broadcast(serial, "STATUS_CURRENT")
        after = _parse_wear_status(status_data)
        if status_result != 0:
            continue
        if after.get("title", "") != expected_title or after.get("artist", "") != expected_artist:
            raise RuntimeError("Wear OS song changed while setting Like")
        if after.get("liked") == "1" or (
            before.get("likeAction")
            and after.get("likeAction")
            and after.get("likeAction") != before.get("likeAction")
        ):
            return "like"
    raise RuntimeError("Wear OS MediaSession did not confirm thumb-up rating")


def wear_adb_control(serial: str, action: str, before: NowPlaying) -> NowPlaying:
    receiver_action = {
        "previous": "PREVIOUS",
        "next": "NEXT",
        "play-pause": "PLAY_PAUSE",
    }[action]
    result, data = _adb_broadcast(serial, receiver_action)
    if result != 0 or not data.startswith("control_notification_action_sent:"):
        raise RuntimeError(f"Android/Wear OS {action} failed: {data or 'receiver error ' + str(result)}")
    for _ in range(20):
        time.sleep(0.25)
        after = wear_adb_status(serial, require_playing=False)
        if not after:
            continue
        if action == "play-pause":
            changed = after.playing != before.playing
        elif action == "previous":
            changed = after.title != before.title or after.artist != before.artist or (
                before.position_ms > 1500 and after.position_ms < before.position_ms - 1000
            )
        else:
            changed = after.title != before.title or after.artist != before.artist
        if changed:
            time.sleep(0.5)
            confirmed = wear_adb_status(serial, require_playing=False)
            if not confirmed:
                continue
            if action == "play-pause":
                stable = confirmed.playing == after.playing
            elif action == "previous" and after.title == before.title and after.artist == before.artist:
                stable = confirmed.position_ms < before.position_ms - 500
            else:
                stable = confirmed.title == after.title and confirmed.artist == after.artist
            if stable:
                return confirmed
    raise RuntimeError(f"Android/Wear OS did not confirm {action}")


def linux_mpris_current() -> NowPlaying | None:
    if not sys.platform.startswith("linux"):
        return None
    command = [
        "playerctl", "metadata", "--format",
        "{{status}}\t{{xesam:url}}\t{{xesam:title}}\t{{xesam:artist}}",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=False)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        fields = line.split("\t", 3)
        if len(fields) < 2 or fields[0].lower() != "playing":
            continue
        video_id = extract_video_id(fields[1])
        if video_id:
            return NowPlaying(
                video_id=video_id,
                title=fields[2] if len(fields) > 2 else "",
                artist=fields[3] if len(fields) > 3 else "",
                source="linux-mpris",
                reported_at=time.time(),
            )
    return None


def linux_mpris_control(action: str) -> dict[str, Any] | None:
    if not sys.platform.startswith("linux") or not shutil.which("playerctl"):
        return None
    command = {
        "previous": "previous",
        "next": "next",
        "play-pause": "play-pause",
    }[action]
    result = subprocess.run(
        ["playerctl", command], capture_output=True, text=True, timeout=4, check=False
    )
    if result.returncode != 0:
        return None
    return {"source": "linux-mpris", "action": action, "verified": True}


def load_reported_current(max_age: int = 300) -> NowPlaying:
    try:
        payload = json.loads(state_path().read_text(encoding="utf-8"))
        item = NowPlaying(**payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("No browser player was reported") from exc
    age = time.time() - item.reported_at
    if age > max_age or not item.source.startswith("browser:"):
        raise RuntimeError("No recent browser player was reported")
    return item


def browser_control(action: str, before: NowPlaying) -> NowPlaying:
    save_browser_command(action, before)
    for _ in range(40):
        time.sleep(0.2)
        try:
            after = load_reported_current(max_age=30)
        except RuntimeError:
            continue
        if after.reported_at <= before.reported_at:
            continue
        if action == "play-pause":
            changed = after.playing != before.playing
        elif action == "previous":
            changed = after.video_id != before.video_id or (
                before.position_ms > 1500 and after.position_ms < before.position_ms - 1000
            )
        else:
            changed = after.video_id != before.video_id
        if changed:
            return after
    command_path().unlink(missing_ok=True)
    raise RuntimeError(f"Browser extension did not confirm {action}")


def control_active(action: str) -> dict[str, Any]:
    if action not in {"previous", "next", "play-pause"}:
        raise ValueError(f"Unsupported control action: {action}")
    if windows_desktop_running():
        after = windows_desktop_control(action)
        return {"source": after.source, "action": action, "verified": True, "current": asdict(after)}
    wear = wear_adb_current(require_playing=(action != "play-pause"))
    if wear:
        serial = wear.source.removeprefix("wearos-adb:")
        after = wear_adb_control(serial, action, wear)
        return {"source": after.source, "action": action, "verified": True, "current": asdict(after)}
    linux_result = linux_mpris_control(action)
    if linux_result:
        return linux_result
    browser = load_reported_current()
    after = browser_control(action, browser)
    return {"source": after.source, "action": action, "verified": True, "current": asdict(after)}


def load_current(max_age: int = 30) -> NowPlaying:
    if windows_desktop_running():
        item = windows_desktop_current()
        save_current(item)
        return item
    wear = wear_adb_current()
    if wear:
        return wear
    live = linux_mpris_current()
    if live:
        save_current(live)
        return live
    try:
        payload = json.loads(state_path().read_text(encoding="utf-8"))
        item = NowPlaying(**payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("No exact current video was reported") from exc
    age = time.time() - item.reported_at
    if age > max_age:
        raise RuntimeError(f"Current-video report is stale ({age:.0f}s; maximum {max_age}s)")
    if not item.playing:
        raise RuntimeError("The last reported video is paused")
    return item


def youtube_credentials(client_secrets: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError("Install dependencies: python -m pip install -r requirements.txt") from exc

    credentials = None
    if token_path().exists():
        credentials = Credentials.from_authorized_user_file(str(token_path()), [YOUTUBE_SCOPE])
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        client_secrets = resolve_client_secrets(client_secrets)
        validate_desktop_client(client_secrets)
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), [YOUTUBE_SCOPE])
        credentials = flow.run_local_server(host="localhost", port=0, open_browser=True)
    token_path().write_text(credentials.to_json(), encoding="utf-8")
    return credentials


def like_video(video_id: str, client_secrets: Path) -> None:
    from google.auth.transport.requests import AuthorizedSession

    credentials = youtube_credentials(client_secrets)
    response = AuthorizedSession(credentials).post(
        "https://www.googleapis.com/youtube/v3/videos/rate",
        params={"id": video_id, "rating": "like"},
        timeout=20,
    )
    if response.status_code != 204:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(f"YouTube API returned HTTP {response.status_code}: {detail}")


def get_video_rating(video_id: str, client_secrets: Path) -> str:
    from google.auth.transport.requests import AuthorizedSession

    credentials = youtube_credentials(client_secrets)
    response = AuthorizedSession(credentials).get(
        "https://www.googleapis.com/youtube/v3/videos/getRating",
        params={"id": video_id},
        timeout=20,
    )
    if response.status_code != 200:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(f"YouTube rating check returned HTTP {response.status_code}: {detail}")
    items = response.json().get("items", [])
    if len(items) != 1 or items[0].get("videoId") != video_id:
        raise RuntimeError("YouTube rating check returned no matching video")
    return str(items[0].get("rating", "unspecified"))


class ReporterHandler(BaseHTTPRequestHandler):
    server_version = "YtmLike/1.0"
    client_secrets = Path("client_secret.json")

    def _json(self, code: int, value: dict[str, Any]) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._json(204, {})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/v1/command":
            supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
            if not supplied or not secrets.compare_digest(supplied, reporter_token()):
                self._json(401, {"ok": False, "error": "Invalid reporter token"})
                return
            video_id = parse_qs(parsed.query).get("videoId", [""])[0]
            command = take_browser_command(video_id)
            if command:
                self._json(200, {"ok": True, "command": command})
            else:
                self._json(204, {})
            return
        if parsed.path != "/api/v1/current":
            self._json(404, {"ok": False, "error": "Not found"})
            return
        try:
            self._json(200, {"ok": True, "current": asdict(load_current())})
        except RuntimeError as exc:
            self._json(404, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/api/v1/report", "/api/v1/like-url", "/api/v1/control"}:
            self._json(404, {"ok": False, "error": "Not found"})
            return
        supplied = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not supplied or not secrets.compare_digest(supplied, reporter_token()):
            self._json(401, {"ok": False, "error": "Invalid reporter token"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 16_384:
                raise ValueError("Invalid body size")
            payload = json.loads(self.rfile.read(length))
            if self.path == "/api/v1/control":
                result = control_active(str(payload.get("action") or ""))
                self._json(200, {"ok": True, **result})
                return
            item = NowPlaying.from_payload(payload)
            save_current(item)
            if self.path == "/api/v1/like-url":
                like_video(item.video_id, self.client_secrets)
                rating = get_video_rating(item.video_id, self.client_secrets)
                if rating != "like":
                    raise RuntimeError(f"YouTube did not confirm Like; current rating is {rating}")
                self._json(200, {
                    "ok": True,
                    "rating": rating,
                    "verified": True,
                    "current": asdict(item),
                })
            else:
                self._json(200, {"ok": True, "current": asdict(item)})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except RuntimeError as exc:
            self._json(502, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-secrets", type=Path, default=Path("client_secret.json"))
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="receive exact current-video reports")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8888)
    current = commands.add_parser("current", help="show the fresh current video")
    current.add_argument("--max-age", type=int, default=30)
    like = commands.add_parser("like-current", help="like the fresh current video")
    like.add_argument("--max-age", type=int, default=30)
    commands.add_parser("previous", help="play the previous track on the active provider")
    commands.add_parser("next", help="play the next track on the active provider")
    commands.add_parser("play-pause", help="toggle play/pause on the active provider")
    commands.add_parser("token", help="show the local reporter token")
    commands.add_parser("auth", help="authorize YouTube access without liking a video")
    args = parser.parse_args()

    try:
        if args.command == "serve":
            token = reporter_token()
            ReporterHandler.client_secrets = args.client_secrets
            print(f"Reporter: http://{args.host}:{args.port}/api/v1/report")
            print(f"Reporter token: {token}")
            ThreadingHTTPServer((args.host, args.port), ReporterHandler).serve_forever()
        elif args.command == "current":
            print(json.dumps(asdict(load_current(args.max_age)), ensure_ascii=False, indent=2))
        elif args.command == "like-current":
            item = load_current(args.max_age)
            if item.source == "windows-youtube-music-api":
                rating = windows_desktop_like(item.video_id)
                verified_by = "YouTube Music Desktop /api/v1/like-state"
            elif item.source.startswith("wearos-adb:"):
                serial = item.source.removeprefix("wearos-adb:")
                rating = wear_adb_like(serial, item.title, item.artist)
                verified_by = "Wear OS YouTube Music MediaSession USER_RATING"
            else:
                like_video(item.video_id, args.client_secrets)
                rating = get_video_rating(item.video_id, args.client_secrets)
                verified_by = "YouTube Data API videos.getRating"
            if rating != "like":
                raise RuntimeError(f"YouTube did not confirm Like; current rating is {rating}")
            print(json.dumps({
                "ok": True,
                "rating": rating,
                "verified": True,
                "verified_by": verified_by,
                "current": asdict(item),
            }, ensure_ascii=False))
        elif args.command in {"previous", "next", "play-pause"}:
            result = control_active(args.command)
            print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        elif args.command == "token":
            print(reporter_token())
        elif args.command == "auth":
            youtube_credentials(args.client_secrets)
            print(json.dumps({"ok": True, "authorized": True}, ensure_ascii=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # CLI boundary
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
