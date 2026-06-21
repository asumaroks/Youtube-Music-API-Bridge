package com.asuma.ytmsessiondiagnostic;

import android.app.Activity;
import android.app.NotificationManager;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Color;
import android.media.MediaMetadata;
import android.media.Rating;
import android.media.session.MediaController;
import android.media.session.MediaSessionManager;
import android.media.session.PlaybackState;
import android.os.Bundle;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final String TAG = "YtmSessionDiagnostic";
    private static final String YTM_PACKAGE = "com.google.android.apps.youtube.music";

    private ComponentName listenerComponent;
    private MediaSessionManager sessionManager;
    private TextView reportView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        listenerComponent = new ComponentName(this, SessionNotificationListener.class);
        sessionManager = getSystemService(MediaSessionManager.class);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(12);
        root.setPadding(padding, padding, padding, padding);

        Button access = button("1. Notification access");
        access.setOnClickListener(v -> openNotificationAccess());
        root.addView(access);

        Button refresh = button("2. Refresh sessions");
        refresh.setOnClickListener(v -> refreshReport());
        root.addView(refresh);

        LinearLayout transport = new LinearLayout(this);
        transport.setOrientation(LinearLayout.HORIZONTAL);
        Button previous = button("Prev");
        previous.setOnClickListener(v -> sendTransportAction(1, "Previous"));
        Button playPause = button("Play/Pause");
        playPause.setOnClickListener(v -> sendTransportAction(2, "Play/Pause"));
        Button next = button("Next");
        next.setOnClickListener(v -> sendTransportAction(3, "Next"));
        transport.addView(previous, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        transport.addView(playPause, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        transport.addView(next, new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        root.addView(transport);

        Button tryLike = button("3. Like current if needed");
        tryLike.setOnClickListener(v -> tryAdvertisedLike());
        root.addView(tryLike);

        reportView = new TextView(this);
        reportView.setTextColor(Color.WHITE);
        reportView.setTextSize(12f);
        reportView.setTextIsSelectable(true);
        reportView.setPadding(0, dp(8), 0, dp(24));

        ScrollView scroll = new ScrollView(this);
        scroll.addView(reportView);
        root.addView(scroll, new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f));
        setContentView(root);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshReport();
    }

    private Button button(String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        return button;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private boolean hasNotificationAccess() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        return manager != null && manager.isNotificationListenerAccessGranted(listenerComponent);
    }

    private void openNotificationAccess() {
        try {
            startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
        } catch (Exception error) {
            Toast.makeText(this, "Notification access settings unavailable", Toast.LENGTH_LONG).show();
            Log.e(TAG, "Cannot open notification access settings", error);
        }
    }

    private List<MediaController> activeSessions() {
        if (!hasNotificationAccess()) {
            throw new SecurityException("Notification Listener access is not granted");
        }
        return sessionManager.getActiveSessions(listenerComponent);
    }

    private void refreshReport() {
        StringBuilder report = new StringBuilder();
        report.append("Notification access: ").append(hasNotificationAccess()).append('\n');
        try {
            List<MediaController> sessions = activeSessions();
            report.append("Active sessions: ").append(sessions.size()).append("\n\n");
            for (int index = 0; index < sessions.size(); index++) {
                appendController(report, index, sessions.get(index));
            }
            if (sessions.isEmpty()) {
                report.append("Start playback in YouTube Music, then refresh.\n");
            }
        } catch (SecurityException error) {
            report.append("Grant Notification access, return here, and refresh.\n");
        } catch (Exception error) {
            report.append("ERROR: ").append(error).append('\n');
            Log.e(TAG, "Session query failed", error);
        }
        String value = report.toString();
        reportView.setText(value);
        Log.i(TAG, "REPORT_BEGIN\n" + value + "REPORT_END");
    }

    private void appendController(StringBuilder out, int index, MediaController controller) {
        out.append("SESSION ").append(index + 1).append('\n');
        out.append("package=").append(controller.getPackageName()).append('\n');
        MediaMetadata metadata = controller.getMetadata();
        if (metadata == null) {
            out.append("metadata=null\n");
        } else {
            appendMetadata(out, metadata);
        }
        PlaybackState state = controller.getPlaybackState();
        if (state == null) {
            out.append("playbackState=null\n");
        } else {
            out.append("state=").append(stateName(state.getState())).append('\n');
            out.append("positionMs=").append(state.getPosition()).append('\n');
            out.append("actions=0x").append(Long.toHexString(state.getActions())).append('\n');
            List<PlaybackState.CustomAction> customActions = state.getCustomActions();
            out.append("customActions=").append(customActions.size()).append('\n');
            for (PlaybackState.CustomAction action : customActions) {
                out.append("  action=").append(action.getAction())
                        .append(" name=").append(action.getName())
                        .append(" icon=").append(action.getIcon()).append('\n');
            }
        }
        out.append('\n');
    }

    private void appendMetadata(StringBuilder out, MediaMetadata metadata) {
        appendValue(out, "mediaId", metadata.getString(MediaMetadata.METADATA_KEY_MEDIA_ID));
        appendValue(out, "mediaUri", metadata.getString(MediaMetadata.METADATA_KEY_MEDIA_URI));
        appendValue(out, "title", metadata.getText(MediaMetadata.METADATA_KEY_TITLE));
        appendValue(out, "artist", metadata.getText(MediaMetadata.METADATA_KEY_ARTIST));
        appendValue(out, "album", metadata.getText(MediaMetadata.METADATA_KEY_ALBUM));
        appendValue(out, "displayTitle", metadata.getText(MediaMetadata.METADATA_KEY_DISPLAY_TITLE));
        appendValue(out, "displaySubtitle", metadata.getText(MediaMetadata.METADATA_KEY_DISPLAY_SUBTITLE));
        Rating userRating = metadata.getRating(MediaMetadata.METADATA_KEY_USER_RATING);
        out.append("userRating=").append(describeRating(userRating)).append('\n');
        out.append("durationMs=").append(metadata.getLong(MediaMetadata.METADATA_KEY_DURATION)).append('\n');
        out.append("metadataKeys=").append(TextUtils.join(",", metadata.keySet())).append('\n');
    }

    private void appendValue(StringBuilder out, String name, CharSequence value) {
        out.append(name).append('=').append(value == null ? "<null>" : value).append('\n');
    }

    private void tryAdvertisedLike() {
        try {
            for (MediaController controller : activeSessions()) {
                if (!YTM_PACKAGE.equals(controller.getPackageName())) {
                    continue;
                }
                if (isThumbUp(controller.getMetadata())) {
                    Toast.makeText(this, "Current track is already liked", Toast.LENGTH_LONG).show();
                    return;
                }
                PlaybackState state = controller.getPlaybackState();
                if (state == null) continue;
                for (PlaybackState.CustomAction action : state.getCustomActions()) {
                    String searchable = (action.getAction() + " " + action.getName())
                            .toLowerCase(Locale.ROOT);
                    boolean like = searchable.contains("like")
                            || searchable.contains("thumb_up")
                            || searchable.contains("thumbs_up");
                    boolean dislike = searchable.contains("dislike")
                            || searchable.contains("thumb_down")
                            || searchable.contains("thumbs_down");
                    if (like && !dislike) {
                        if (SessionNotificationListener.sendNotificationAction(action.getName())) {
                            Toast.makeText(this, "Sent notification action: " + action.getName(), Toast.LENGTH_LONG).show();
                            reportView.postDelayed(this::refreshReport, 1000);
                            return;
                        }
                        Toast.makeText(this, "Matching YouTube notification action is unavailable", Toast.LENGTH_LONG).show();
                        return;
                    }
                }
            }
            Toast.makeText(this, "YouTube Music exposes no Like custom action", Toast.LENGTH_LONG).show();
        } catch (Exception error) {
            Toast.makeText(this, "Like diagnostic failed: " + error, Toast.LENGTH_LONG).show();
            Log.e(TAG, "Like diagnostic failed", error);
        }
    }

    private void sendTransportAction(int notificationIndex, String label) {
        try {
            if (SessionNotificationListener.sendNotificationActionAt(notificationIndex)) {
                Toast.makeText(this, label + " sent", Toast.LENGTH_SHORT).show();
                reportView.postDelayed(this::refreshReport, 700);
            } else {
                Toast.makeText(this, "YouTube Music notification is unavailable", Toast.LENGTH_LONG).show();
            }
        } catch (Exception error) {
            Toast.makeText(this, label + " failed: " + error, Toast.LENGTH_LONG).show();
            Log.e(TAG, label + " failed", error);
        }
    }

    private static String stateName(int state) {
        switch (state) {
            case PlaybackState.STATE_NONE: return "NONE";
            case PlaybackState.STATE_STOPPED: return "STOPPED";
            case PlaybackState.STATE_PAUSED: return "PAUSED";
            case PlaybackState.STATE_PLAYING: return "PLAYING";
            case PlaybackState.STATE_FAST_FORWARDING: return "FAST_FORWARDING";
            case PlaybackState.STATE_REWINDING: return "REWINDING";
            case PlaybackState.STATE_BUFFERING: return "BUFFERING";
            case PlaybackState.STATE_ERROR: return "ERROR";
            case PlaybackState.STATE_CONNECTING: return "CONNECTING";
            case PlaybackState.STATE_SKIPPING_TO_PREVIOUS: return "SKIPPING_TO_PREVIOUS";
            case PlaybackState.STATE_SKIPPING_TO_NEXT: return "SKIPPING_TO_NEXT";
            case PlaybackState.STATE_SKIPPING_TO_QUEUE_ITEM: return "SKIPPING_TO_QUEUE_ITEM";
            default: return Integer.toString(state);
        }
    }

    static boolean isThumbUp(MediaMetadata metadata) {
        if (metadata == null) return false;
        Rating rating = metadata.getRating(MediaMetadata.METADATA_KEY_USER_RATING);
        return rating != null
                && rating.isRated()
                && rating.getRatingStyle() == Rating.RATING_THUMB_UP_DOWN
                && rating.isThumbUp();
    }

    private static String describeRating(Rating rating) {
        if (rating == null) return "<null>";
        if (!rating.isRated()) return "unrated(style=" + rating.getRatingStyle() + ")";
        if (rating.getRatingStyle() == Rating.RATING_THUMB_UP_DOWN) {
            return rating.isThumbUp() ? "thumb_up" : "thumb_down";
        }
        if (rating.getRatingStyle() == Rating.RATING_HEART) {
            return rating.hasHeart() ? "heart" : "no_heart";
        }
        return "rated(style=" + rating.getRatingStyle() + ")";
    }
}
