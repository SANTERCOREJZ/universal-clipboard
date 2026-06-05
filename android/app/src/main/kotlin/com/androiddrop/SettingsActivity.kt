package com.androiddrop

import android.Manifest
import android.content.ClipboardManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.widget.Button
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.textfield.TextInputEditText
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class SettingsActivity : AppCompatActivity() {

    // ActivityResultLauncher handles the permission dialog result — modern Android way.
    private val notifPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) DropService.start(this)
        else Toast.makeText(this, "Enable notifications to see the tray icon", Toast.LENGTH_LONG).show()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        // On Android 13+ ask for notification permission first, then start the service.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                == PackageManager.PERMISSION_GRANTED) {
                DropService.start(this)
            } else {
                notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        } else {
            DropService.start(this)
        }

        val prefs   = Prefs(this)
        val etIp    = findViewById<TextInputEditText>(R.id.etIp)
        val etPort  = findViewById<TextInputEditText>(R.id.etPort)
        val etToken = findViewById<TextInputEditText>(R.id.etToken)
        val btnSave      = findViewById<Button>(R.id.btnSave)
        val btnTest      = findViewById<Button>(R.id.btnTest)
        val btnDiscover  = findViewById<Button>(R.id.btnDiscover)
        val btnClipboard = findViewById<Button>(R.id.btnClipboard)
        val btnRepair    = findViewById<Button>(R.id.btnRepair)

        etIp.setText(prefs.ip)
        etPort.setText(prefs.port.toString())
        etToken.setText(prefs.token)

        btnSave.setOnClickListener {
            val ip = etIp.text.toString().trim()
            if (ip.isBlank()) { etIp.error = "Required"; return@setOnClickListener }
            prefs.ip    = ip
            prefs.port  = etPort.text.toString().trim().toIntOrNull() ?: 8765
            prefs.token = etToken.text.toString().trim().ifBlank { "changeme" }
            Toast.makeText(this, "Saved!", Toast.LENGTH_SHORT).show()
        }

        btnTest.setOnClickListener {
            val ip = etIp.text.toString().trim()
            if (ip.isBlank()) { Toast.makeText(this, "Enter an IP first", Toast.LENGTH_SHORT).show(); return@setOnClickListener }

            prefs.ip    = ip
            prefs.port  = etPort.text.toString().trim().toIntOrNull() ?: 8765
            prefs.token = etToken.text.toString().trim().ifBlank { "changeme" }

            btnTest.isEnabled = false
            btnTest.text = "Testing…"

            lifecycleScope.launch(Dispatchers.IO) {
                val (ok, msg) = try {
                    val resp = Uploader.healthCheck(prefs)
                    Pair(resp.isSuccessful, if (resp.isSuccessful) "✓ Connected to Mac!" else "Error ${resp.code}")
                } catch (e: Exception) {
                    Pair(false, "Cannot reach Mac:\n${e.message}")
                }
                withContext(Dispatchers.Main) {
                    btnTest.isEnabled = true
                    btnTest.text = "Test"
                    Toast.makeText(this@SettingsActivity, msg, if (ok) Toast.LENGTH_SHORT else Toast.LENGTH_LONG).show()
                }
            }
        }

        btnDiscover.setOnClickListener {
            btnDiscover.isEnabled = false
            btnDiscover.text = "Searching…"

            // mDNS browse off the main thread; fills in the IP/port it finds.
            lifecycleScope.launch {
                val found = Discovery.findMac(this@SettingsActivity)
                btnDiscover.isEnabled = true
                btnDiscover.text = "Find Mac automatically"
                if (found != null) {
                    etIp.setText(found.ip)
                    etPort.setText(found.port.toString())
                    prefs.ip   = found.ip
                    prefs.port = found.port
                    Toast.makeText(this@SettingsActivity, "✓ Found Mac at ${found.ip}", Toast.LENGTH_SHORT).show()
                } else {
                    Toast.makeText(
                        this@SettingsActivity,
                        "No Mac found. Make sure AndroidDrop is running on the Mac and both are on the same Wi-Fi.",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        }

        btnRepair.setOnClickListener {
            // Forget the pinned Mac key — the next connection will trust-on-first-use again.
            // Use this only if you switched Macs or rebuilt the Mac app's certificate.
            prefs.certPin = ""
            Toast.makeText(this, "Pairing reset — will trust the next Mac you connect to.", Toast.LENGTH_LONG).show()
        }

        btnClipboard.setOnClickListener {
            if (!prefs.isConfigured) {
                Toast.makeText(this, "Save the Mac IP first", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            // ClipboardManager = Android clipboard API, like NSPasteboard on Mac.
            // Can only read it while app is in foreground (Android 10+ restriction).
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = clipboard.primaryClip?.getItemAt(0)

            if (clip == null) {
                Toast.makeText(this, "Clipboard is empty", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            btnClipboard.isEnabled = false
            btnClipboard.text = "Sending…"

            // Check if clipboard contains an image URI (Samsung screenshot, copied image, etc.)
            val imageUri = clip.uri?.takeIf { uri ->
                contentResolver.getType(uri)?.startsWith("image/") == true
            }

            lifecycleScope.launch(Dispatchers.IO) {
                val (ok, msg) = try {
                    if (imageUri != null) {
                        val mimeType = contentResolver.getType(imageUri) ?: "image/png"
                        val resp = Sender.send(this@SettingsActivity, prefs) {
                            Uploader.uploadFile(prefs, contentResolver, imageUri, mimeType)
                        }
                        Pair(resp.isSuccessful, if (resp.isSuccessful) "✓ Screenshot sent to Mac!" else "Error ${resp.code}")
                    } else {
                        val text = clip.coerceToText(this@SettingsActivity).toString()
                        if (text.isBlank()) return@launch
                        val resp = Sender.send(this@SettingsActivity, prefs) {
                            Uploader.uploadText(prefs, text)
                        }
                        Pair(resp.isSuccessful, if (resp.isSuccessful) "✓ Clipboard sent to Mac!" else "Error ${resp.code}")
                    }
                } catch (e: Exception) {
                    Pair(false, "Failed: ${e.message}")
                }
                withContext(Dispatchers.Main) {
                    btnClipboard.isEnabled = true
                    btnClipboard.text = "Send clipboard to Mac"
                    Toast.makeText(this@SettingsActivity, msg, if (ok) Toast.LENGTH_SHORT else Toast.LENGTH_LONG).show()
                }
            }
        }
    }
}
