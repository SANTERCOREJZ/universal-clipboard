// App-level build file: defines how to compile the app and what libraries to use.
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.androiddrop"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.androiddrop"
        minSdk = 26          // Android 8.0 — covers ~97% of devices
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = "11"
    }
}

dependencies {
    // AndroidX core + AppCompat: standard Android backwards-compat libraries
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    // Material Design components (buttons, text fields, cards)
    implementation("com.google.android.material:material:1.12.0")
    // Lifecycle/coroutines: lets us run background tasks tied to Activity lifetime
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    // OkHttp: HTTP client — like Python's requests library
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    // Kotlin coroutines: async/await for Android — like Python's asyncio
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
