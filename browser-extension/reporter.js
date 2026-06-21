(function () {
  "use strict";

  let lastSignature = "";
  let polling = false;

  function videoId() {
    const url = new URL(location.href);
    if (url.pathname === "/watch") return url.searchParams.get("v");
    const match = url.pathname.match(/^\/(?:shorts|live)\/([\w-]{11})/);
    if (match) return match[1];

    // YouTube Music can keep location at `/` while its internal player changes
    // tracks. The title link belongs to the active player and contains the exact ID.
    const playerLink = document.querySelector(
      "ytmusic-player-page .ytp-title-link[href*='watch'], " +
      "ytmusic-app .ytp-title-link[href*='watch'], " +
      ".html5-video-player .ytp-title-link[href*='watch']"
    );
    if (playerLink) {
      const playerUrl = new URL(playerLink.href, location.origin);
      const playerId = playerUrl.searchParams.get("v");
      if (playerId && /^[\w-]{11}$/.test(playerId)) return playerId;
    }
    return null;
  }

  function metadata() {
    const video = document.querySelector("video");
    const id = videoId();
    if (!video || !id || id.length !== 11) return null;
    const musicTitle = document.querySelector("ytmusic-player-bar .title");
    const musicArtist = document.querySelector("ytmusic-player-bar .byline");
    return {
      videoId: id,
      title: (musicTitle?.textContent || document.title.replace(/\s*-\s*YouTube(?: Music)?$/, "")).trim(),
      artist: (musicArtist?.textContent || "").trim(),
      playing: !video.paused && !video.ended,
      positionMs: Math.max(0, Math.round(video.currentTime * 1000)),
      source: `browser:${location.hostname}`
    };
  }

  async function report() {
    const item = metadata();
    if (!item) return;
    const signature = `${item.videoId}:${item.playing}`;
    if (signature === lastSignature && !item.playing) return;
    try {
      const response = await chrome.runtime.sendMessage({ type: "report-current", payload: item });
      if (response?.ok) lastSignature = signature;
    } catch (_) {
      // The local agent may be stopped; retry on the next interval.
    }
  }

  async function handleControl(command) {
    const video = document.querySelector("video");
    if (!video || command.videoId !== videoId()) return false;
    if (command.action === "play-pause") {
      if (video.paused) await video.play();
      else video.pause();
    } else {
      const selectors = command.action === "next"
        ? ["ytmusic-player-bar .next-button", ".ytp-next-button"]
        : ["ytmusic-player-bar .previous-button", ".ytp-prev-button"];
      const button = selectors.map(selector => document.querySelector(selector)).find(Boolean);
      if (!button) return false;
      button.click();
    }
    setTimeout(report, 300);
    return true;
  }

  async function pollCommand() {
    if (polling) return;
    const item = metadata();
    if (!item) return;
    polling = true;
    try {
      const response = await chrome.runtime.sendMessage({
        type: "poll-command",
        videoId: item.videoId
      });
      const command = response?.value?.command;
      if (response?.ok && command) await handleControl(command);
    } catch (_) {
      // The local agent may be stopped; retry on the next interval.
    } finally {
      polling = false;
    }
  }

  setInterval(report, 5000);
  setInterval(pollCommand, 1000);
  document.addEventListener("play", report, true);
  document.addEventListener("pause", report, true);
  report();
})();
