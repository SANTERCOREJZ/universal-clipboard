package com.androiddrop

import android.content.Context

/**
 * SharedPreferences wrapper — persists the Mac IP, port, and token between app launches.
 *
 * SharedPreferences is Android's simple key-value store, like a small JSON file on disk.
 * In Kotlin, `var ip: String get()/set()` is a property with custom getter and setter —
 * similar to Python's @property decorator.
 */
class Prefs(context: Context) {
    private val sp = context.getSharedPreferences("androiddrop", Context.MODE_PRIVATE)

    var ip: String
        get() = sp.getString("ip", "") ?: ""
        set(v) { sp.edit().putString("ip", v).apply() }

    var port: Int
        get() = sp.getInt("port", 8765)
        set(v) { sp.edit().putInt("port", v).apply() }

    var token: String
        get() = sp.getString("token", "changeme") ?: "changeme"
        set(v) { sp.edit().putString("token", v).apply() }

    val baseUrl: String get() = "http://$ip:$port"
    val isConfigured: Boolean get() = ip.isNotBlank()
}
