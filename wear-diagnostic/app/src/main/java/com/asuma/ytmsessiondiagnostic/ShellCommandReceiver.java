package com.asuma.ytmsessiondiagnostic;

import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.media.MediaMetadata;
import android.media.session.MediaController;
import android.media.session.MediaSessionManager;
import android.media.session.PlaybackState;
import android.net.Uri;

import java.util.List;

/** ADB-shell-only entrypoint for liking the active YouTube Music session. */
public final class ShellCommandReceiver extends BroadcastReceiver {
    private static final String YTM_PACKAGE = "com.google.android.apps.youtube.music";
    private static final String THUMBS_UP_ACTION = "thumbs_up_action";

    @Override
    public void onReceive(Context context, Intent intent) {
        boolean requestLike = "com.asuma.ytmsessiondiagnostic.LIKE_CURRENT".equals(intent.getAction());
        boolean requestStatus = "com.asuma.ytmsessiondiagnostic.STATUS_CURRENT".equals(intent.getAction());
        boolean requestPrevious = "com.asuma.ytmsessiondiagnostic.PREVIOUS".equals(intent.getAction());
        boolean requestNext = "com.asuma.ytmsessiondiagnostic.NEXT".equals(intent.getAction());
        boolean requestPlayPause = "com.asuma.ytmsessiondiagnostic.PLAY_PAUSE".equals(intent.getAction());
        if (!requestLike && !requestStatus && !requestPrevious && !requestNext && !requestPlayPause) {
            setResult(10, "unsupported_action", null);
            return;
        }
        try {
            MediaSessionManager manager = context.getSystemService(MediaSessionManager.class);
            ComponentName listener = new ComponentName(context, SessionNotificationListener.class);
            List<MediaController> sessions = manager.getActiveSessions(listener);
            for (MediaController controller : sessions) {
                if (!YTM_PACKAGE.equals(controller.getPackageName())) continue;
                PlaybackState state = controller.getPlaybackState();
                if (state == null) {
                    setResult(11, "youtube_music_state_missing", null);
                    return;
                }
                boolean playing = state.getState() == PlaybackState.STATE_PLAYING;
                MediaMetadata metadata = controller.getMetadata();
                String title = metadata == null ? "" : metadata.getString(MediaMetadata.METADATA_KEY_TITLE);
                String artist = metadata == null ? "" : metadata.getString(MediaMetadata.METADATA_KEY_ARTIST);
                boolean liked = MainActivity.isThumbUp(metadata);
                PlaybackState.CustomAction thumbsUpAction = null;
                for (PlaybackState.CustomAction action : state.getCustomActions()) {
                    if (THUMBS_UP_ACTION.equals(action.getAction())) {
                        thumbsUpAction = action;
                        break;
                    }
                }
                String likeActionName = thumbsUpAction == null ? "" : thumbsUpAction.getName().toString();
                if (requestStatus) {
                    setResult(0,
                            "session=1&playing=" + (playing ? "1" : "0")
                                    + "&liked=" + (liked ? "1" : "0")
                                    + "&title=" + Uri.encode(title == null ? "" : title)
                                    + "&artist=" + Uri.encode(artist == null ? "" : artist)
                                    + "&positionMs=" + Math.max(0, state.getPosition())
                                    + "&likeAction=" + Uri.encode(likeActionName),
                            null);
                    return;
                }
                if (requestPrevious || requestNext || requestPlayPause) {
                    int notificationIndex = requestPrevious ? 1 : (requestPlayPause ? 2 : 3);
                    String command = requestPrevious ? "previous" : (requestPlayPause ? "play-pause" : "next");
                    if (SessionNotificationListener.sendNotificationActionAt(notificationIndex)) {
                        setResult(0, "control_notification_action_sent:" + command, null);
                    } else {
                        setResult(16, "notification_control_missing:" + command, null);
                    }
                    return;
                }
                if (!playing) {
                    setResult(11, "youtube_music_not_playing", null);
                    return;
                }
                if (liked) {
                    setResult(0, "already_liked:" + title, null);
                    return;
                }
                if (thumbsUpAction != null
                        && SessionNotificationListener.sendNotificationAction(thumbsUpAction.getName())) {
                    setResult(0, "like_notification_action_sent:" + title, null);
                    return;
                }
                setResult(12, "thumbs_up_action_missing", null);
                return;
            }
            setResult(13, "youtube_music_session_missing", null);
        } catch (SecurityException error) {
            setResult(14, "notification_access_missing", null);
        } catch (Exception error) {
            setResult(15, "error:" + error.getClass().getSimpleName(), null);
        }
    }
}
