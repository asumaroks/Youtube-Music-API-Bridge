# Android / Wear OS YouTube Music Session Bridge

This universal APK runs on Android phones and Wear OS. It checks whether the installed YouTube Music app exposes an active Android `MediaSession`, metadata, and a Like notification action.

## On the phone or watch

1. Start playback in YouTube Music.
2. Open **YTM Session Diagnostic**.
3. Tap **Notification access** and enable the diagnostic listener.
4. Return and tap **Refresh sessions**.
5. Inspect `mediaId`, `mediaUri`, `metadataKeys`, `actions`, and `customActions`.
6. Only if a Like custom action is listed, tap **Like current if needed**.
7. Use **Prev**, **Play/Pause**, and **Next** for transport control.

The app invokes the `PendingIntent` action created by YouTube Music itself. It does not guess a track from title/artist and does not use accessibility automation.

## ADB report

```console
adb logcat -c
adb shell am start -n com.asuma.ytmsessiondiagnostic/.MainActivity
adb logcat -d -s YtmSessionDiagnostic:I
```

ADB can request an idempotent Like directly. The exported receiver requires the
signature-level `android.permission.DUMP`, which is held by adb shell but not by
ordinary third-party apps:

```console
adb shell am broadcast -W \
  -a com.asuma.ytmsessiondiagnostic.LIKE_CURRENT \
  -n com.asuma.ytmsessiondiagnostic/.ShellCommandReceiver
```

Machine-readable current-session status:

```console
adb shell am broadcast -W \
  -a com.asuma.ytmsessiondiagnostic.STATUS_CURRENT \
  -n com.asuma.ytmsessiondiagnostic/.ShellCommandReceiver
```

ADB transport actions use the same shell-only receiver with actions
`PREVIOUS`, `NEXT`, and `PLAY_PAUSE`.

## Build

```console
gradlew.bat :app:assembleDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`.
