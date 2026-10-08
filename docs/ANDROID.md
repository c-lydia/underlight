# Android and Flutter on Underlight desktops

Ubuntu/Debian and EndeavourOS/Arch use the same `underlight-android` helper and
Android Studio launcher. Native Linux Android Studio and emulator setup targets
x86_64 desktops. The [phone terminal profile](TERMINAL.md) deliberately excludes
these desktop SDKs and GUI applications.

Run the normal Underlight installer first. To install prerequisites and reuse
an existing Flutter SDK, or clone stable Flutter if none is found:

```sh
underlight-android setup
```

For a new Android Studio installation, download the Linux `.tar.gz` from
[Google](https://developer.android.com/studio), then pass the downloaded file:

```sh
underlight-android setup ~/Downloads/android-studio-VERSION-linux.tar.gz
```

The archive installs under `~/.local/share/underlight/android-studio`. Existing
installations are preserved. The helper also discovers native installs under
`/opt/android-studio`, `/usr/share/android-studio`, `~/android-studio`, and
versioned `~/android-studio*/android-studio` directories. Set
`ANDROID_STUDIO_HOME` explicitly for another location. It also accepts an
`android-studio` launcher on PATH. Flatpak SDK isolation is not configured.

Ubuntu's `underlight-install-extras --with-android` and EndeavourOS's
`./install-endeavouros.sh --with-android` invoke the same optional setup. Setup
installs distro prerequisites, ADB and USB rules, Java, and Flutter build tools.
It does not accept SDK licenses, select an API version, or download AVD images
on the user's behalf.

## Finish the SDK setup

1. Run `underlight-android studio` and complete Android Studio's Setup Wizard.
2. In SDK Manager, select the Android API/platform and build tools your project
   needs, plus **Android SDK Platform-Tools**, **Android SDK Command-line Tools
   (latest)**, and **Android Emulator**.
3. Create an AVD in Device Manager and download its system image.
4. Install the Flutter plugin in Studio if desired; the Flutter SDK is separate.
5. Run `underlight-android flutter doctor --android-licenses`, review the
   licenses, then run `underlight-android doctor`.

See [Flutter's Android setup guide](https://docs.flutter.dev/platform-integration/android/setup)
for the currently supported SDK requirements.

## Commands and environment

```sh
underlight-android studio /path/to/project
underlight-android adb devices -l
underlight-android flutter doctor -v
underlight-android flutter run
underlight-android sdk --list
underlight-android emulator                  # choose an existing AVD
underlight-android emulator My_AVD -gpu auto # explicit AVD and emulator options
underlight-android doctor
```

The helper discovers `~/Android/Sdk` or `/opt/android-sdk`. `ANDROID_HOME` takes
precedence; a pre-existing `ANDROID_SDK_ROOT` is kept consistent. SDK platform
tools, emulator, and `cmdline-tools/latest/bin` are added to the command's PATH.
An explicit `FLUTTER_ROOT` takes precedence; otherwise an existing `flutter` on
PATH is preserved, followed by `~/develop/flutter`, `~/flutter`,
`~/projects/flutter`, and the managed SDK at
`~/.local/share/underlight/flutter`. A pre-existing `JAVA_HOME` is preserved;
otherwise the helper uses Studio's bundled JDK when available.

For direct `adb`, `flutter`, `emulator`, and CUDA commands in Bash or Zsh, add:

```sh
[ ! -r "$HOME/.config/underlight/toolchains.sh" ] || . "$HOME/.config/underlight/toolchains.sh"
```

Open a new terminal or source that file. The installer links the shared file
without replacing your shell startup files. The desktop provides an Android
Studio application entry and **Super+X → Android & Flutter**; the wide terminal
network lab exposes the desktop tools too.

## Devices, acceleration, and GPU selection

Enable USB debugging on a physical phone and approve the computer on the phone.
Use ADB's standard `pair`/`connect` commands for Android wireless debugging.
For hardware-accelerated emulators, enable CPU virtualization in firmware and
ensure your user has read/write access to `/dev/kvm`. If your distribution uses
the `kvm` group, add yourself to it and log out/in. `underlight-android doctor`
runs the emulator acceleration check and Flutter doctor. See Google's
[acceleration guide](https://developer.android.com/studio/run/emulator-acceleration).

Underlight leaves emulator renderer selection to the emulator. If its automatic
renderer fails, pass a renderer option supported by `emulator -help-gpu`. To
request discrete NVIDIA rendering explicitly:

```sh
underlight-gpu-run underlight-android emulator My_AVD
```

A loaded NVIDIA driver/library mismatch still requires the host driver to be
reloaded, normally by rebooting after an update. Changing SDK paths cannot fix
that mismatch.
