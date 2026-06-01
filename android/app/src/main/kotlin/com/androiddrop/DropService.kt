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
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Foreground service — keeps running in the background and shows a persistent notification.
 *
 * It does two long-lived jobs:
 *   1. Status ping loop: every 30s checks the Mac is reachable (and rediscovers it via
 *      mDNS if the saved IP went stale), updating the persistent notification text.
 *   2. WebSocket to the Mac (Mac → Android direction): stays connected and, when the Mac
 *      copies something, shows a tappable "Copied on Mac" notification. Tapping it opens
 *      the invisible PasteActivity which writes the content into this phone's clipboard
 *      (and saves screenshots to the gallery).
 *
 * START_STICKY restarts the service if the OS kills it. The WebSocket reconnects on its own.
 */
class DropService : Service() {

    companion object {
        const val ACTION_SHOW_RESULT = "com.androiddrop.SHOW_RESULT"
        const val EXTRA_RESULT = "result"
        private const val CHANNEL_ID = "androiddrop_status"
        private const val INCOMING_CHANNEL_ID = "androiddrop_incoming"
        const val NOTIF_ID = 1
        private const val INCOMING_NOTIF_ID = 2
        private const val WS_RETRY_MS = 4_000L

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, DropService::class.java))
        }
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var pingJob: Job? = null

    // Long-lived client for the WebSocket: keep-alive pings, no read timeout.
    private val wsClient = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .connectTimeout(8, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .build()
    private var ws: WebSocket? = null
    private var destroyed = false

    override fun onBind(intent: Intent?): IBinder? = null  // not a bound service

    override fun onCreate() {
        super.onCreate()
        createChannels()
        startForeground(NOTIF_ID, buildNotification("Starting…"))
        startPingLoop()
        openWs()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // ClipSendActivity (legacy path) can call this with a result to show in the notification.
        if (intent?.action == ACTION_SHOW_RESULT) {
            val msg = intent.getStringExtra(EXTRA_RESULT) ?: return START_STICKY
            pingJob?.cancel()
            updateNotif(msg)
            scope.launch {
                delay(4_000)
                startPingLoop()
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        destroyed = true
        ws?.cancel()
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
                        var ok = withContext(Dispatchers.IO) {
                            try { Uploader.healthCheck(prefs).isSuccessful }
                            catch (e: Exception) { false }
                        }
                        // Self-heal: if the saved IP no longer answers, the Mac may have
                        // a new address — rediscover it via mDNS and update the saved IP.
                        if (!ok) {
                            val found = Discovery.findMac(this@DropService)
                            if (found != null) {
                                prefs.ip   = found.ip
                                prefs.port = found.port
                                ok = withContext(Dispatchers.IO) {
                                    try { Uploader.healthCheck(prefs).isSuccessful }
                                    catch (e: Exception) { false }
                                }
                            }
                        }
                        if (ok) "Mac connected" else "Mac unreachable"
                    }
                }
                updateNotif(status)
                delay(30_000)  // re-check every 30 seconds
            }
        }
    }

    // ── WebSocket (Mac → Android) ───────────────────────────────────────────────

    private val wsListener = object : WebSocketListener() {
        override fun onMessage(webSocket: WebSocket, text: String) {
            handleIncoming(text)
        }
        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (ws === webSocket) ws = null
            scheduleWsRetry()
        }
        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            if (ws === webSocket) ws = null
            scheduleWsRetry()
        }
    }

    private fun openWs() {
        if (destroyed || ws != null) return
        val prefs = Prefs(this)
        if (!prefs.isConfigured) { scheduleWsRetry(); return }
        ws = wsClient.newWebSocket(
            Request.Builder()
                .url("${prefs.baseUrl}/ws")
                .header("x-token", prefs.token)
                .build(),
            wsListener
        )
    }

    private fun scheduleWsRetry() {
        if (destroyed) return
        scope.launch {
            delay(WS_RETRY_MS)
            if (!destroyed && ws == null) openWs()
        }
    }

    private fun handleIncoming(text: String) {
        val ev = try { JSONObject(text) } catch (e: Exception) { return }
        val type = ev.optString("type")
        if (type != "text" && type != "image") return

        val seq = ev.optInt("seq", -1)
        val prefs = Prefs(this)
        if (seq in 0..prefs.lastInboxSeq) return  // already shown this clip
        if (seq >= 0) prefs.lastInboxSeq = seq

        showIncoming(type, ev.optString("preview"))
    }

    private fun showIncoming(type: String, preview: String) {
        val tapIntent = PendingIntent.getActivity(
            this, 1,
            Intent(this, PasteActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val title = if (type == "image") "Image copied on Mac" else "Copied on Mac"
        val line = preview.ifBlank { "Tap to paste on this phone" }

        val notif = NotificationCompat.Builder(this, INCOMING_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_tile)
            .setContentTitle(title)
            .setContentText(line)
            .setStyle(NotificationCompat.BigTextStyle().bigText("$line\n\nTap to paste on this phone"))
            .setAutoCancel(true)
            .setContentIntent(tapIntent)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()

        (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
            .notify(INCOMING_NOTIF_ID, notif)
    }

    // ── Persistent status notification ──────────────────────────────────────────

    private fun buildNotification(statusText: String): Notification {
        // "Send Clipboard" button opens ClipSendActivity (transparent, reads clipboard, sends, closes).
        val sendPending = PendingIntent.getActivity(
            this, 0,
            Intent(this, ClipSendActivity::class.java).apply {
                // Own task + no animation so tapping the button doesn't visibly "open the app".
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_NO_ANIMATION
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

    private fun createChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        // Persistent, silent status channel.
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "AndroidDrop Status", NotificationManager.IMPORTANCE_LOW).apply {
                description = "Persistent status and send button"
                setShowBadge(false)
            }
        )

        // Pop-up channel for "copied on Mac" alerts.
        nm.createNotificationChannel(
            NotificationChannel(INCOMING_CHANNEL_ID, "Clipboard from Mac", NotificationManager.IMPORTANCE_DEFAULT).apply {
                description = "Notifies when the Mac copies something"
            }
        )
    }
}
