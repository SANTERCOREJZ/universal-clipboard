package com.androiddrop

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*

/**
 * Foreground service — keeps running in the background and shows a persistent notification.
 *
 * Unlike a regular service, a foreground service:
 *   - Cannot be killed by the OS to free memory (as long as it's in foreground)
 *   - Must show a notification (the "tray" the user asked for)
 *   - Restarts automatically if killed (START_STICKY)
 *
 * The notification has a "Send Clipboard" button. Because Android 10+ blocks clipboard
 * access from background services, the button opens ClipSendActivity (transparent, instant)
 * which reads the clipboard and sends the result back here via ACTION_SHOW_RESULT.
 */
class DropService : Service() {

    companion object {
        const val ACTION_SHOW_RESULT = "com.androiddrop.SHOW_RESULT"
        const val EXTRA_RESULT = "result"
        private const val CHANNEL_ID = "androiddrop_status"
        const val NOTIF_ID = 1

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, DropService::class.java))
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var pingJob: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null  // not a bound service

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startForeground(NOTIF_ID, buildNotification("Starting…"))
        startPingLoop()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // ClipSendActivity calls this with the upload result to update the notification text.
        if (intent?.action == ACTION_SHOW_RESULT) {
            val msg = intent.getStringExtra(EXTRA_RESULT) ?: return START_STICKY
            pingJob?.cancel()          // pause status updates while showing result
            updateNotif(msg)
            scope.launch {
                delay(4_000)           // show result for 4 seconds, then resume pinging
                startPingLoop()
            }
        }
        return START_STICKY  // if killed, restart automatically
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }

    // ── Status ping loop ──────────────────────────────────────────────────────

    private fun startPingLoop() {
        pingJob?.cancel()
        pingJob = scope.launch {
            while (true) {
                val prefs = Prefs(this@DropService)
                val status = when {
                    !prefs.isConfigured -> "Open app to set Mac IP"
                    else -> {
                        val ok = withContext(Dispatchers.IO) {
                            try { Uploader.healthCheck(prefs).isSuccessful }
                            catch (e: Exception) { false }
                        }
                        if (ok) "Mac connected" else "Mac unreachable"
                    }
                }
                updateNotif(status)
                delay(30_000)  // re-check every 30 seconds
            }
        }
    }

    // ── Notification builder ──────────────────────────────────────────────────

    private fun buildNotification(statusText: String): Notification {
        // "Send Clipboard" button opens ClipSendActivity (transparent, reads clipboard, sends, closes).
        val sendPending = PendingIntent.getActivity(
            this, 0,
            Intent(this, ClipSendActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_tile)
            .setContentTitle("AndroidDrop")
            .setContentText(statusText)
            .setOngoing(true)           // cannot be swiped away
            .setSilent(true)            // no sound or vibration
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .addAction(0, "Send Clipboard", sendPending)
            .build()
    }

    private fun updateNotif(status: String) {
        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(NOTIF_ID, buildNotification(status))
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "AndroidDrop Status",
                NotificationManager.IMPORTANCE_LOW   // LOW = silent, shows in status bar
            ).apply {
                description = "Persistent status and send button"
                setShowBadge(false)
            }
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .createNotificationChannel(channel)
        }
    }
}
