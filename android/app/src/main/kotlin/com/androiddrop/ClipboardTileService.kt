package com.androiddrop

import android.content.ClipboardManager
import android.content.Context
import android.os.Build
import android.service.quicksettings.Tile
import android.service.quicksettings.TileService
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/**
 * Quick Settings tile — the button in the notification shade.
 *
 * Lifecycle:
 *   onStartListening() — shade is open, tile is visible: ping Mac, show connection status
 *   onClick()          — user tapped the tile: send clipboard content
 *   onDestroy()        — tile removed or service killed: cancel all coroutines
 *
 * Tile states:
 *   STATE_ACTIVE   = colored  → Mac reachable, ready
 *   STATE_INACTIVE = grey     → Mac not reachable / not configured
 *   STATE_UNAVAILABLE = dimmed, unclickable → currently sending
 */
class ClipboardTileService : TileService() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)

    // Short-timeout client just for the health-check ping — we don't want to block the shade for 10s.
    private val pingClient = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .build()

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }

    // Called every time the tile becomes visible (user pulls down shade).
    override fun onStartListening() {
        super.onStartListening()
        val prefs = Prefs(this)

        if (!prefs.isConfigured) {
            setTile(Tile.STATE_INACTIVE, "Open app to set IP")
            return
        }

        setTile(Tile.STATE_ACTIVE, "Checking…")

        scope.launch {
            val reachable = withContext(Dispatchers.IO) {
                try {
                    pingClient.newCall(
                        Request.Builder()
                            .url("${prefs.baseUrl}/health")
                            .header("x-token", prefs.token)
                            .get()
                            .build()
                    ).execute().isSuccessful
                } catch (e: Exception) {
                    false
                }
            }
            setTile(
                state    = if (reachable) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE,
                subtitle = if (reachable) "Mac connected" else "Mac unreachable"
            )
        }
    }

    override fun onClick() {
        super.onClick()

        val prefs = Prefs(this)
        if (!prefs.isConfigured) {
            setTile(Tile.STATE_INACTIVE, "Open app to set IP")
            return
        }

        // Clipboard must be read here on the main thread inside onClick().
        // Android 10+ only grants clipboard access during user-initiated interactions.
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val item = clipboard.primaryClip?.getItemAt(0)

        // Check if clipboard holds an image URI (e.g. Samsung screenshot).
        val imageUri = item?.uri?.let { uri ->
            try {
                if (contentResolver.getType(uri)?.startsWith("image/") == true) uri else null
            } catch (e: Exception) {
                null
            }
        }
        // Otherwise treat it as text.
        val text = if (imageUri == null) item?.coerceToText(this)?.toString() else null

        if (imageUri == null && text.isNullOrBlank()) {
            setTile(Tile.STATE_ACTIVE, "Clipboard is empty")
            return
        }

        setTile(Tile.STATE_UNAVAILABLE, "Sending…")

        scope.launch {
            val (ok, result) = withContext(Dispatchers.IO) {
                try {
                    if (imageUri != null) {
                        val mime = try {
                            contentResolver.getType(imageUri) ?: "image/png"
                        } catch (e: Exception) {
                            "image/png"
                        }
                        val resp = Uploader.uploadFile(prefs, contentResolver, imageUri, mime)
                        Pair(resp.isSuccessful, if (resp.isSuccessful) "✓ Image sent!" else "Error ${resp.code}")
                    } else {
                        val resp = Uploader.uploadText(prefs, text!!)
                        Pair(resp.isSuccessful, if (resp.isSuccessful) "✓ Sent!" else "Error ${resp.code}")
                    }
                } catch (e: Exception) {
                    Pair(false, "× ${e.message?.take(40)}")
                }
            }

            setTile(
                state    = if (ok) Tile.STATE_ACTIVE else Tile.STATE_INACTIVE,
                subtitle = result
            )
        }
    }

    private fun setTile(state: Int, subtitle: String) {
        qsTile?.apply {
            this.state = state
            this.label = "AndroidDrop"
            // subtitle is supported from Android 10 (API 29)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                this.subtitle = subtitle
            }
            updateTile()
        }
    }
}
