package com.androiddrop

import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Invisible activity that exists only to read the clipboard and send it to Mac.
 *
 * Why a separate Activity instead of reading clipboard in DropService directly?
 * Android 10+ only allows clipboard access when an Activity is in the foreground.
 * Background services are blocked. This Activity is fully transparent and closes
 * itself as soon as the upload finishes — the user barely notices it.
 *
 * Flow: notification button tap → this Activity opens → reads clipboard →
 *       uploads → tells DropService the result → finishes.
 */
class ClipSendActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // No setContentView — the activity is fully transparent (set via theme in themes.xml).

        val prefs = Prefs(this)
        if (!prefs.isConfigured) {
            reportAndFinish("Open app to set Mac IP")
            return
        }

        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val item = clipboard.primaryClip?.getItemAt(0)

        val imageUri = item?.uri?.let { uri ->
            try {
                if (contentResolver.getType(uri)?.startsWith("image/") == true) uri else null
            } catch (e: Exception) { null }
        }
        val text = if (imageUri == null) item?.coerceToText(this)?.toString() else null

        if (imageUri == null && text.isNullOrBlank()) {
            reportAndFinish("Clipboard is empty")
            return
        }

        lifecycleScope.launch {
            val (ok, msg) = withContext(Dispatchers.IO) {
                try {
                    if (imageUri != null) {
                        val mime = try { contentResolver.getType(imageUri) ?: "image/png" }
                                   catch (e: Exception) { "image/png" }
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
            reportAndFinish(msg)
        }
    }

    private fun reportAndFinish(message: String) {
        // Tell DropService to update the notification text with the result.
        ContextCompat.startForegroundService(
            this,
            Intent(this, DropService::class.java).apply {
                action = DropService.ACTION_SHOW_RESULT
                putExtra(DropService.EXTRA_RESULT, message)
            }
        )
        finish()
    }
}
