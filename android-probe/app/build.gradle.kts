plugins { id("com.android.application") }

// Golden Java<->Python contract fixtures. Ordinary test runs only READ them; they are rewritten
// solely by an approved protocol change: gradle testDebugUnitTest -Pvector.updateCrossLanguageFixtures=true
val crossLanguageFixtures = rootProject.file("../local-agent/tests/fixtures/cross_language")
val updateCrossLanguageFixtures = (findProperty("vector.updateCrossLanguageFixtures") ?: "false").toString()

android {
    namespace = "org.vector.probe"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.vector.probe"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "0.2.0"
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
    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            all {
                it.systemProperty("vector.crossLanguageFixtures", crossLanguageFixtures.absolutePath)
                it.systemProperty("vector.updateCrossLanguageFixtures", updateCrossLanguageFixtures)
                it.inputs.dir(crossLanguageFixtures).withPropertyName("crossLanguageFixtures")
            }
        }
    }
}

dependencies {
    implementation("com.google.code.gson:gson:2.11.0")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.16")
}
