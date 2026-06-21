# iPhone fallback: Share → Shortcut → Like

iOS does not expose another app's Now Playing session to third-party apps.
`MPNowPlayingInfoCenter` is for setting metadata for media played by the calling
app, not reading YouTube Music. Therefore the supported iPhone workflow starts
from the YouTube Music **Share** action, which supplies an exact track URL.

## Server

Run the existing agent behind a private HTTPS endpoint (VPN, Tailscale, Caddy,
or nginx):

```console
python ytm_like.py serve --host 0.0.0.0
```

The Shortcut calls:

```http
POST /api/v1/like-url
Authorization: Bearer <reporter token>
Content-Type: application/json

{"url":"<Shortcut Input>","source":"ios-share","playing":true}
```

The endpoint extracts the exact 11-character `videoId`, calls the official
YouTube Data API `videos.rate`, then verifies the result with `getRating`.

## Shortcut actions

1. Create a Shortcut that accepts **URLs** from the Share Sheet.
2. Add **Get Contents of URL**.
3. URL: `https://your-private-host/api/v1/like-url`.
4. Method: `POST`; request body: JSON.
5. Add fields: `url` = **Shortcut Input**, `source` = `ios-share`, `playing` = `true`.
6. Add header `Authorization` = `Bearer <token from python ytm_like.py token>`.
7. Add **Show Result**.

Do not expose this endpoint over plain HTTP or the public internet. The bearer
token authorizes changing the YouTube rating.

## Limitation

This requires one explicit Share action on iPhone. Fully automatic detection of
the track playing in the native YouTube Music iOS app is unavailable through
public Apple or YouTube APIs.

## Previous / Next / Play-Pause

An iPhone Shortcut may use Apple's built-in local media actions (Play/Pause and
Skip) when iOS exposes them for the current player. This runs on the iPhone and
cannot be invoked by the Windows/Linux agent as an API. The native YouTube Music
session remains inaccessible to third-party iOS apps.
