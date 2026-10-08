# VECTOR Probe — Phase 8B development build

This is the Android companion source for the Phase 8B control plane. It performs
no physical diagnostic, component authenticity assessment, or scoring. The only
advertised capability is `CONTROL_CHANNEL`: HELLO, GET_CAPABILITIES, HEARTBEAT.
The three challenge operations are validated but return UNAVAILABLE without work.

## Build and verification

Use JDK 17, Gradle **8.11.1**, Android SDK platform **35**, and Build Tools **35.0.0**.
The Android Gradle plugin is pinned to 8.9.2; Gson to 2.11.0; JUnit to 4.13.2.
Gradle must be installed separately; this repository does not bundle a wrapper or
download/accept SDK licenses automatically. Set `ANDROID_HOME` or an ignored
`local.properties` to your SDK location, then from this directory run:

```powershell
gradle :app:testDebugUnitTest :app:lintDebug :app:compileDebugJavaWithJavac :app:assembleDebug
```

Debug signing uses the standard external development keystore. Do not copy any
keystore or password into this repository. Release is unsigned and the app
explicitly refuses the development bootstrap when `BuildConfig.DEBUG` is false.
Production bootstrap/signing is not implemented or authorized in this increment.
The desktop trust record can pin other signer fingerprints, but this does not
make the current development bootstrap suitable for a production release.

## Enroll and install explicitly

1. Build and inspect `app/build/outputs/apk/debug/app-debug.apk`.
2. Obtain the SHA-256 certificate fingerprint from your known development signing
   key through trusted local tooling. Do not take the expected fingerprint from
   the phone or automatically trust whichever signer an unknown APK reports.
3. From `local-agent`, run the fixed-artifact enrollment utility:

   ```powershell
   uv run python -m vector_agent.probe.trust_build --sdk-root <SDK-directory> --java <JDK-java.exe> --expected-signer <64-lowercase-hex-certificate-SHA256>
   ```

   It accepts only this repository's fixed debug output, runs `apksigner verify`,
   requires exactly one matching signer, checks package/version/debug metadata
   with aapt2, and checks the whole APK hash before and after verification. It
   writes an ignored public trust record in `local-agent/.data/probe-trust.json`.
   There are no keys in this record. Restart the local agent to reload it. A
   custom agent data directory needs this record placed there by the operator.
4. Manually install this exact APK using Android's normal tools and consent. No
   desktop install/update/uninstall endpoint exists. Do not replace or uninstall
   an unknown signer automatically. A rebuild/update requires explicit enrollment
   again, even when signed by the same development key.
5. Discover the device through the existing device API. Use the protected Probe
   `discover`, then `launch` control actions. The app asks for on-device consent.
6. Tap **Allow connection**, then invoke `connect`. Closing/backgrounding the
   app, pressing **Decline / stop**, expiry, or transport loss revokes consent.
   Reconnect requires a new Allow action; there is no persistent permission grant.

The development path supports the Android owner profile (user 0), provisional
API 26+, normal non-root ADB, readable installed APK hashing, and permitted
`run-as` access to the verified debug app. OEM/profile restrictions fail closed.
These assumptions need real-device qualification; no devices are qualified yet.

## Permission audit

The manifest declares **zero permissions**. The app uses a visible Activity and
an abstract Unix-domain socket, not a TCP listener or foreground/background
service. No INTERNET, notification, storage, camera, microphone, sensor, location,
phone, contacts, account, accessibility, device-admin, VPN, or privileged
permission is needed or requested. There is no automatic permission grant.

`FLAG_SECURE` protects the consent screen from ordinary capture, and the Allow
button rejects obscured touches. `FLAG_KEEP_SCREEN_ON` prevents screen timeout
during active sessions. The exported launcher Activity processes no intent extras
and never treats launch as consent. Backup is disabled. The private bootstrap
contains only an ephemeral key/socket name or fixed consent state, and never
device identifiers or personal content.

Allow/Deny protects against accidental connection and other on-device apps, but
the ADB-authorized development host is inside the Phase 8B trust boundary.
Phase 8B is not designed to resist a malicious authorized ADB host. Production
non-debuggable pairing and cryptographic consent are future roadmap items.

See [the Phase 8B boundary and review handoff](../docs/PHASE_8B_PROBE.md).
