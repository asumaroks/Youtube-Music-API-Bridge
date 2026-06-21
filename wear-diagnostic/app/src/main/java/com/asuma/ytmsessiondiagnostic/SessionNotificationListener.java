package com.asuma.ytmsessiondiagnostic;

import android.app.Notification;
import android.app.PendingIntent;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;

/** Notification access permits querying sessions and invoking YouTube's own notification actions. */
public final class SessionNotificationListener extends NotificationListenerService {
    private static final String YTM_PACKAGE = "com.google.android.apps.youtube.music";
    private static volatile SessionNotificationListener instance;

    @Override
    public void onListenerConnected() {
        instance = this;
    }

    @Override
    public void onListenerDisconnected() {
        if (instance == this) instance = null;
    }

    @Override
    public void onDestroy() {
        if (instance == this) instance = null;
        super.onDestroy();
    }

    static boolean sendNotificationAction(CharSequence expectedTitle) throws PendingIntent.CanceledException {
        SessionNotificationListener listener = instance;
        if (listener == null || expectedTitle == null) return false;
        StatusBarNotification[] notifications = listener.getActiveNotifications();
        if (notifications == null) return false;
        for (StatusBarNotification status : notifications) {
            if (!YTM_PACKAGE.equals(status.getPackageName())) continue;
            Notification.Action[] actions = status.getNotification().actions;
            if (actions == null) continue;
            for (Notification.Action action : actions) {
                if (action.title != null && expectedTitle.toString().contentEquals(action.title)) {
                    action.actionIntent.send();
                    return true;
                }
            }
        }
        return false;
    }

    static boolean sendNotificationActionAt(int index) throws PendingIntent.CanceledException {
        SessionNotificationListener listener = instance;
        if (listener == null) return false;
        StatusBarNotification[] notifications = listener.getActiveNotifications();
        if (notifications == null) return false;
        for (StatusBarNotification status : notifications) {
            if (!YTM_PACKAGE.equals(status.getPackageName())) continue;
            Notification.Action[] actions = status.getNotification().actions;
            if (actions == null || index < 0 || index >= actions.length) return false;
            actions[index].actionIntent.send();
            return true;
        }
        return false;
    }
}
