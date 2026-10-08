plugins { id("com.android.application") }

android {
    namespace = "org.vector.probe"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.vector.probe"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
    buildFeatures { buildConfig = true }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    // Only development signing is authorized. Release stays unsigned and cannot
    // use the development-only run-as bootstrap; no fallback to an open channel.
    buildTypes { getByName("release") { isDebuggable = false } }
    lint { abortOnError = true; warningsAsErrors = true }
}

dependencies {
    implementation("com.google.code.gson:gson:2.11.0")
    testImplementation("junit:junit:4.13.2")
}
