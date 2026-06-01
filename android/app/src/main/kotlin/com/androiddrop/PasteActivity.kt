package com.androiddrop

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.widget.Toast
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/**
 * Invisible activity for the Mac → Android direction. Opened when the user taps the
 * "Copied on Mac" notification.
 *
 * Same trick as [ClipSendActivity]: writing to the clipboard on Android 10+ also
 * requires a focused window, so we briefly (and invisibly) come to the foreground,
 * pull the clipboard content from the Mac, write it, and finish. Images are also
 * saved to the gallery so the screenshot actually lands on the phone.
 */
class PasteActivity : Activity() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var handled = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (!hasFocus || handled) return
        handled = true

        scope.launch {
            val prefs = Prefs(this@PasteActivity)
            val built = if (!prefs.isConfigured) null
                        else try { withContext(Dispatchers.IO) { buildClip(prefs) } }
                             catch (e: Exception) { null }

            if (built != null) {
                // Must run while we still have focus (Android 10+ clipboard rule) — we
                // haven't called finish() yet, so the window is still foreground.
                val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(built.clip)
                toast(built.message)
            } else {
                toast("Couldn't get clipboard from Mac")
            }

            finish()
            @Suppress("DEPRECATION")
            overridePendingTransition(0, 0)
        }
    }

    private data class Built(val clip: ClipData, val message: String)

    /** Blocking — call inside Dispatchers.IO. Fetches from the Mac and prepares the clip. */
    private fun buildClip(prefs: Prefs): Built? {
        val metaResp = Uploader.getOutbox(prefs)
        if (!metaResp.isSuccessful) return null
        val meta = JSONObject(metaResp.body?.string() ?: return null)

        return when (meta.optString("type")) {
            "text" -> {
                val text = meta.optString("text")
                if (text.isBlank()) null
                else Built(ClipData.newPlainText("From Mac", text), "✓ Pasted from Mac")
            }
            "image" -> {
                val fileResp = Uploader.getOutboxFile(prefs)
                if (!fileResp.isSuccessful) return null
                val bytes = fileResp.body?.bytes() ?: return null
                val mime = meta.optString("mime", "image/png")
                val uri = saveToGallery(bytes, mime) ?: return null  // pre-Android 10: skipped
                Built(ClipData.newUri(contentResolver, "From Mac", uri), "✓ Screenshot saved to Gallery")
            }
            else -> null
        }
    }

    /** Save image bytes into Pictures/AndroidDrop via MediaStore (Android 10+). */
    private fun saveToGallery(bytes: ByteArray, mime: String): Uri? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return null  // pre-10: skip gallery
        val resolver = contentResolver
        val name = "Mac-${System.currentTimeMillis()}.png"
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, name)
            put(MediaStore.Images.Media.MIME_TYPE, mime)
            put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/AndroidDrop")
        }
        val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return null
        return try {
            resolver.openOutputStream(uri)?.use { it.write(bytes) } ?: return null
            uri
        } catch (e: Exception) {
            resolver.delete(uri, null, null)
            null
        }
    }

    private fun toast(msg: String) =
        Toast.makeText(applicationContext, msg, Toast.LENGTH_SHORT).show()
}
