# Build Android AAB (Release)

Builds a signed release Android App Bundle (.aab) for Android projects in `D:\App_DEV\`.

**IMPORTANT:** Before running, read `build.gradle` to get the correct `applicationId`, `versionCode`, and `versionName` for the current project. Do NOT assume this is the x-file-manager project.

## General Steps

1. Read `android/app/build.gradle` to get `applicationId`, `versionCode`, `versionName`
2. Set JAVA_HOME to JDK 17 and run Gradle bundleRelease
3. Rename output from `app-release.aab` → `<applicationId>-vc<versionCode>.aab`

```powershell
$env:JAVA_HOME = "D:\Program Files\jdk-17.0.19.10-hotspot"
Set-Location "<project>\android"
.\gradlew bundleRelease
Rename-Item "app\build\outputs\bundle\release\app-release.aab" "<applicationId>-vc<versionCode>.aab"
```

---

## Project: Top Notch (`D:\App_DEV\top-notch`)

- Package: `com.topnotch.progress` · versionCode: `1` · versionName: `1.0.0`
- Release signing currently uses **debug keystore** (replace before Play Store upload)
- Output: `android\app\build\outputs\bundle\release\com.topnotch.progress-vc1.aab`

### Known fix — `Unresolved reference 'currentActivity'`
In RN 0.76 New Architecture, `currentActivity` was removed from `ReactContextBaseJavaModule`.
**File:** `android/app/src/main/java/com/topnotch/overlay/TopNotchOverlayModule.kt:92`
**Fix:** Change `currentActivity` → `reactApplicationContext.currentActivity`

---

## Project: X File Manager (`D:\App_DEV\x-file-manager`)

- Package: `com.xfilemanager` (check build.gradle)
- Requires buffer polyfill in `metro.config.js`

### `Unable to resolve module buffer`
- Install: `npm install buffer` in project root
- Create `metro.config.js` with:
  ```js
  const { getDefaultConfig } = require('expo/metro-config');
  const path = require('path');
  const config = getDefaultConfig(__dirname);
  config.resolver.extraNodeModules = {
    ...config.resolver.extraNodeModules,
    buffer: path.resolve(__dirname, 'node_modules/buffer'),
  };
  module.exports = config;
  ```

### Signing config not found
- Check `android/gradle.properties` has:
  ```
  RELEASE_STORE_FILE=<path-to-keystore>.jks
  RELEASE_KEY_ALIAS=<key-alias>
  RELEASE_STORE_PASSWORD=<store-password>
  RELEASE_KEY_PASSWORD=<key-password>
  ```
- Do NOT commit `gradle.properties` with real values — add it to `.gitignore`

---

## Common Errors (all projects)

### Wrong Java version
- JDK 17 is at `D:\Program Files\jdk-17.0.19.10-hotspot`
- Always set: `$env:JAVA_HOME = "D:\Program Files\jdk-17.0.19.10-hotspot"` before running gradlew

### `currentActivity` unresolved reference (RN 0.76+)
- Replace `currentActivity` with `reactApplicationContext.currentActivity` in any native module extending `ReactContextBaseJavaModule`
