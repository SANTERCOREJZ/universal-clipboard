package com.androiddrop

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * The activity that appears in the Android Share Sheet.
 *
 * In Android, an Activity = a screen. When another app (Photos, Chrome, Files…) triggers
 * a Share action, the OS creates this Activity and passes the shared content via an Intent.
 *
 * Intent = a message/event that carries data between apps.
 * Here it carries the file URI or text that the user shared.
 *
 * This activity shows a translucent "Sending…" overlay, uploads the content to the Mac,
 * shows a toast (small popup) with the result, then closes itself.
 */
class ShareActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_share)

        val prefs = Prefs(this)

        // If the Mac IP isn't configured, send the user to Settings first.
        if (!prefs.isConfigured) {
            Toast.makeText(this, "Open AndroidDrop and enter your Mac's IP first.", Toast.LENGTH_LONG).show()
            startActivity(Intent(this, SettingsActivity::class.java))
            finish()
            return
        }

        try {
            when (intent.action) {
                Intent.ACTION_SEND -> handleSend(intent, prefs)
                else -> abort("Unsupported share type")
            }
        } catch (e: Exception) {
            abort("Unexpected error: ${e.javaClass.simpleName}: ${e.message}")
        }
    }

    private fun handleSend(intent: Intent, prefs: Prefs) {
        val mimeType = intent.type ?: "application/octet-stream"

        if (mimeType == "text/plain") {
            val text = intent.getStringExtra(Intent.EXTRA_TEXT)
            if (text.isNullOrBlank()) { abort("No text found"); return }
            sendText(text, prefs)
        } else {
            // getParcelableExtra API changed in Android 13 (API 33) — handle both old and new.
            val uri: Uri? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                intent.getParcelableExtra(Intent.EXTRA_STREAM, Uri::class.java)
            } else {
                @Suppress("DEPRECATION")
                intent.getParcelableExtra(Intent.EXTRA_STREAM)
            }
            if (uri == null) { abort("No file found"); return }
            sendFile(uri, mimeType, prefs)
        }
    }

    private fun sendText(text: String, prefs: Prefs) {
        setStatus("Sending text…")
        // lifecycleScope.launch = "run this block without blocking the UI thread"
        // Dispatchers.IO = run on a background thread (for network / disk work)
        lifecycleScope.launch(Dispatchers.IO) {
            val (ok, msg) = try {
                val resp = Uploader.uploadText(prefs, text)
                Pair(resp.isSuccessful, if (resp.isSuccessful) "Text sent to Mac ✓" else "Server error ${resp.code}")
            } catch (e: Exception) {
                Pair(false, "Connection failed: ${e.message}")
            }
            // withContext(Main) jumps back to the main thread — only it can touch the UI.
            withContext(Dispatchers.Main) { done(ok, msg) }
        }
    }

    private fun sendFile(uri: Uri, mimeType: String, prefs: Prefs) {
        setStatus("Sending file…")
        lifecycleScope.launch(Dispatchers.IO) {
            val (ok, msg) = try {
                val resp = Uploader.uploadFile(prefs, contentResolver, uri, mimeType)
                Pair(resp.isSuccessful, if (resp.isSuccessful) "Sent to Mac ✓" else "Server error ${resp.code}")
            } catch (e: Exception) {
                Pair(false, "Connection failed: ${e.message}")
            }
            withContext(Dispatchers.Main) { done(ok, msg) }
        }
    }

    private fun setStatus(text: String) {
        findViewById<TextView>(R.id.tvStatus).text = text
    }

    private fun done(ok: Boolean, message: String) {
        Toast.makeText(this, message, if (ok) Toast.LENGTH_SHORT else Toast.LENGTH_LONG).show()
        finish()
    }

    private fun abort(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
        finish()
    }
}
