package com.androiddrop

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * All network calls to the Mac server.
 *
 * OkHttp is like Python's `requests` library — you build a Request and execute it.
 * These functions are BLOCKING (synchronous) — always call them from a background thread
 * (e.g. inside lifecycleScope.launch(Dispatchers.IO) { ... }).
 *
 * `object` in Kotlin is a singleton — like a module with only static methods in Python.
 */
object Uploader {

    // One shared client — it manages a connection pool internally, so don't create one per request.
    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)   // large files need more write time
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    /** Upload a file from a content URI (the Android-safe way to access files from other apps). */
    fun uploadFile(
        prefs: Prefs,
        resolver: ContentResolver,
        uri: Uri,
        mimeType: String,
    ): Response {
        val filename = resolveFilename(resolver, uri) ?: "file"
        // ContentResolver is Android's privacy gateway — you read file bytes through it,
        // never with a direct file path (other apps' files aren't on your filesystem).
        val bytes = resolver.openInputStream(uri)?.readBytes()
            ?: error("Cannot read file from URI")

        return uploadBytes(prefs, bytes, filename, mimeType)
    }

    /** Upload raw bytes already read into memory (used by the clipboard sender). */
    fun uploadBytes(
        prefs: Prefs,
        bytes: ByteArray,
        filename: String,
        mimeType: String,
    ): Response {
        // Android sometimes passes wildcard types like "image/*" in the Intent.
        // OkHttp requires a concrete media type (no wildcards), so we sanitize here.
        val safeMime = if (mimeType.contains("*")) "application/octet-stream" else mimeType

        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", filename, bytes.toRequestBody(safeMime.toMediaType()))
            .addFormDataPart("filename", filename)
            .addFormDataPart("mime_type", safeMime)
            .build()

        return http.newCall(
            Request.Builder()
                .url("${prefs.baseUrl}/push")
                .header("x-token", prefs.token)
                .post(body)
                .build()
        ).execute()
    }

    /** Send plain text to the /text endpoint. */
    fun uploadText(prefs: Prefs, text: String): Response {
        // org.json.JSONObject is built into Android — no extra library needed.
        val json = JSONObject().apply {
            put("text", text)
            put("source", "android")
        }.toString()

        return http.newCall(
            Request.Builder()
                .url("${prefs.baseUrl}/text")
                .header("x-token", prefs.token)
                .post(json.toRequestBody("application/json".toMediaType()))
                .build()
        ).execute()
    }

    /** Mac → Android: pull the current outgoing clipboard metadata (and text, if text). */
    fun getOutbox(prefs: Prefs): Response {
        return http.newCall(
            Request.Builder()
                .url("${prefs.baseUrl}/outbox")
                .header("x-token", prefs.token)
                .get()
                .build()
        ).execute()
    }

    /** Mac → Android: download the current outgoing clipboard image bytes. */
    fun getOutboxFile(prefs: Prefs): Response {
        return http.newCall(
            Request.Builder()
                .url("${prefs.baseUrl}/outbox/file")
                .header("x-token", prefs.token)
                .get()
                .build()
        ).execute()
    }

    /** Ping /health to verify the IP and token are correct before the first real send. */
    fun healthCheck(prefs: Prefs): Response {
        return http.newCall(
            Request.Builder()
                .url("${prefs.baseUrl}/health")
                .header("x-token", prefs.token)
                .get()
                .build()
        ).execute()
    }

    private fun resolveFilename(resolver: ContentResolver, uri: Uri): String? {
        val cursor = resolver.query(uri, null, null, null, null) ?: return null
        return cursor.use { c ->
            val col = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (c.moveToFirst() && col >= 0) c.getString(col) else null
        }
    }
}
