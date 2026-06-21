import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import ytm_like


class CurrentTrackTests(unittest.TestCase):
    def test_extracts_supported_urls(self):
        self.assertEqual(ytm_like.extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "dQw4w9WgXcQ")
        self.assertEqual(ytm_like.extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=2"), "dQw4w9WgXcQ")
        self.assertIsNone(ytm_like.extract_video_id("https://example.com/watch?v=dQw4w9WgXcQ"))

    def test_rejects_stale_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"YTM_LIKE_HOME": directory}
        ), patch.object(ytm_like, "windows_desktop_running", return_value=False), patch.object(
            ytm_like, "wear_adb_current", return_value=None
        ):
            item = ytm_like.NowPlaying("dQw4w9WgXcQ", reported_at=time.time() - 60)
            ytm_like.save_current(item)
            with self.assertRaisesRegex(RuntimeError, "stale"):
                ytm_like.load_current(max_age=10)

    def test_payload_requires_exact_id(self):
        with self.assertRaisesRegex(ValueError, "videoId"):
            ytm_like.NowPlaying.from_payload({"title": "ambiguous metadata"})

    def test_reporter_auth_and_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"YTM_LIKE_HOME": directory}
        ), patch.object(ytm_like, "windows_desktop_running", return_value=False), patch.object(
            ytm_like, "wear_adb_current", return_value=None
        ):
            server = ytm_like.ThreadingHTTPServer(("127.0.0.1", 0), ytm_like.ReporterHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/api/v1/report"
            body = json.dumps({"videoId": "dQw4w9WgXcQ", "playing": True}).encode()
            try:
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"))
                self.assertEqual(rejected.exception.code, 401)
                request = urllib.request.Request(
                    url,
                    data=body,
                    method="POST",
                    headers={
                        "Authorization": f"Bearer {ytm_like.reporter_token()}",
                        "Content-Type": "application/json",
                    },
                )
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.status, 200)
                self.assertEqual(ytm_like.load_current().video_id, "dQw4w9WgXcQ")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_like_url_endpoint_rates_exact_video(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"YTM_LIKE_HOME": directory}
        ), patch.object(ytm_like, "like_video") as like, patch.object(
            ytm_like, "get_video_rating", return_value="like"
        ):
            server = ytm_like.ThreadingHTTPServer(("127.0.0.1", 0), ytm_like.ReporterHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f"http://127.0.0.1:{server.server_port}/api/v1/like-url"
            body = json.dumps({
                "url": "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
                "source": "ios-share",
            }).encode()
            request = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {ytm_like.reporter_token()}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request) as response:
                    payload = json.loads(response.read())
                self.assertTrue(payload["verified"])
                self.assertEqual(payload["rating"], "like")
                like.assert_called_once_with("dQw4w9WgXcQ", ytm_like.ReporterHandler.client_secrets)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_like_uses_official_rate_endpoint(self):
        response = MagicMock(status_code=204)
        session = MagicMock()
        session.post.return_value = response
        with (
            patch.object(ytm_like, "youtube_credentials", return_value=object()),
            patch("google.auth.transport.requests.AuthorizedSession", return_value=session),
        ):
            ytm_like.like_video("dQw4w9WgXcQ", Path("unused.json"))
        session.post.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/videos/rate",
            params={"id": "dQw4w9WgXcQ", "rating": "like"},
            timeout=20,
        )

    def test_reads_rating_from_official_endpoint(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"items": [{"videoId": "dQw4w9WgXcQ", "rating": "like"}]}
        session = MagicMock()
        session.get.return_value = response
        with (
            patch.object(ytm_like, "youtube_credentials", return_value=object()),
            patch("google.auth.transport.requests.AuthorizedSession", return_value=session),
        ):
            self.assertEqual(ytm_like.get_video_rating("dQw4w9WgXcQ", Path("unused.json")), "like")
        session.get.assert_called_once_with(
            "https://www.googleapis.com/youtube/v3/videos/getRating",
            params={"id": "dQw4w9WgXcQ"},
            timeout=20,
        )

    def test_auto_discovers_downloaded_client_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            downloaded = Path(directory) / "client_secret_123.apps.googleusercontent.com.json"
            downloaded.write_text("{}")
            original_is_file = Path.is_file
            with (
                patch("pathlib.Path.cwd", return_value=Path(directory)),
                patch(
                    "pathlib.Path.is_file",
                    autospec=True,
                    side_effect=lambda value: False
                    if value == Path("client_secret.json")
                    else original_is_file(value),
                ),
            ):
                self.assertEqual(ytm_like.resolve_client_secrets(Path("client_secret.json")), downloaded)

    def test_rejects_web_oauth_client(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "client_secret.json"
            path.write_text('{"web": {}}')
            with self.assertRaisesRegex(RuntimeError, "Desktop app"):
                ytm_like.validate_desktop_client(path)

    def test_windows_desktop_song_response(self):
        payload = {
            "videoId": "dQw4w9WgXcQ",
            "title": "Desktop song",
            "artist": "Artist",
            "isPaused": False,
        }
        with patch.object(ytm_like, "_desktop_request", return_value=(200, payload)):
            item = ytm_like.windows_desktop_current()
        self.assertEqual(item.video_id, "dQw4w9WgXcQ")
        self.assertEqual(item.source, "windows-youtube-music-api")
        self.assertTrue(item.playing)

    def test_wear_status_provider(self):
        with patch.object(ytm_like, "_adb_devices", return_value=["watch:1234"]), patch.object(
            ytm_like,
            "_adb_broadcast",
            return_value=(0, "playing=1&liked=0&title=Track%20One&artist=Artist"),
        ):
            item = ytm_like.wear_adb_current()
        self.assertIsNotNone(item)
        self.assertEqual(item.title, "Track One")
        self.assertEqual(item.source, "wearos-adb:watch:1234")

    def test_wear_like_is_idempotent(self):
        with patch.object(
            ytm_like,
            "_adb_broadcast",
            return_value=(0, "playing=1&liked=1&title=Track&artist=Artist"),
        ) as broadcast:
            self.assertEqual(ytm_like.wear_adb_like("watch:1234", "Track", "Artist"), "like")
        broadcast.assert_called_once_with("watch:1234", "STATUS_CURRENT")

    def test_browser_command_is_claimed_only_by_matching_video(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"YTM_LIKE_HOME": directory}
        ):
            item = ytm_like.NowPlaying("dQw4w9WgXcQ", source="browser:music.youtube.com")
            command = ytm_like.save_browser_command("next", item)
            self.assertIsNone(ytm_like.take_browser_command("aaaaaaaaaaa"))
            claimed = ytm_like.take_browser_command("dQw4w9WgXcQ")
            self.assertEqual(claimed["id"], command["id"])
            self.assertIsNone(ytm_like.take_browser_command("dQw4w9WgXcQ"))

    def test_windows_desktop_control_verifies_transition(self):
        before = ytm_like.NowPlaying("dQw4w9WgXcQ", source="windows-youtube-music-api")
        after = ytm_like.NowPlaying("aaaaaaaaaaa", source="windows-youtube-music-api")
        with patch.object(
            ytm_like, "windows_desktop_current", side_effect=[before, after]
        ), patch.object(ytm_like, "_desktop_request", return_value=(204, None)) as request, patch(
            "time.sleep"
        ):
            result = ytm_like.windows_desktop_control("next")
        self.assertEqual(result.video_id, "aaaaaaaaaaa")
        request.assert_called_once_with("/api/v1/next", method="POST")

    def test_control_active_prefers_windows_desktop(self):
        after = ytm_like.NowPlaying("dQw4w9WgXcQ", source="windows-youtube-music-api")
        with patch.object(ytm_like, "windows_desktop_running", return_value=True), patch.object(
            ytm_like, "windows_desktop_control", return_value=after
        ) as desktop, patch.object(ytm_like, "wear_adb_current") as wear:
            result = ytm_like.control_active("play-pause")
        self.assertTrue(result["verified"])
        desktop.assert_called_once_with("play-pause")
        wear.assert_not_called()

    def test_load_current_prefers_running_windows_desktop(self):
        desktop = ytm_like.NowPlaying(
            "dQw4w9WgXcQ", source="windows-youtube-music-api", reported_at=time.time()
        )
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"YTM_LIKE_HOME": directory}), (
            patch.object(ytm_like, "windows_desktop_running", return_value=True)
        ), patch.object(ytm_like, "windows_desktop_current", return_value=desktop) as current, patch.object(
            ytm_like, "linux_mpris_current"
        ) as mpris:
            result = ytm_like.load_current()
        self.assertEqual(result.source, "windows-youtube-music-api")
        current.assert_called_once_with()
        mpris.assert_not_called()

    def test_windows_desktop_like_checks_track_and_state(self):
        current = ytm_like.NowPlaying(
            "dQw4w9WgXcQ", source="windows-youtube-music-api", reported_at=time.time()
        )
        responses = [
            (200, {"state": "INDIFFERENT"}),
            (204, None),
            (200, {"state": "LIKE"}),
        ]
        with patch.object(ytm_like, "windows_desktop_current", return_value=current) as current_call, patch.object(
            ytm_like, "_desktop_request", side_effect=responses
        ) as request, patch("time.sleep"):
            self.assertEqual(ytm_like.windows_desktop_like("dQw4w9WgXcQ"), "like")
        self.assertEqual(current_call.call_count, 2)
        self.assertEqual(request.call_args_list[1].args, ("/api/v1/like",))
        self.assertEqual(request.call_args_list[1].kwargs, {"method": "POST"})


if __name__ == "__main__":
    unittest.main()
