# Contributing to Vimar View Cloud

🇬🇧 English · [🇮🇹 Italiano](CONTRIBUTING.it.md)

Thanks for helping! This integration exists because people shared captures, tested betas and sent code. There are several ways to contribute:

| I want to… | How |
|---|---|
| Report a bug | Open an [issue](https://github.com/ivhazu/ha-vimar-view/issues) with the integration version, what happened and a [debug log](#1-debug-log-no-tools-needed) |
| Get a new device supported | Send a [capture](#capturing-the-app-traffic) of the Vimar VIEW app while you use that device |
| Fix or add code | Open a [pull request](#pull-requests) |
| Improve translations or docs | Edit `custom_components/vimar_cloud/translations/*.json`, `README*.md` or this guide and open a pull request |

---

## What we need to support a new device

Every Vimar device is described by the gateway with a **type** (`sftype`, `sstype`) and a list of **elements** (`SFE_State_…` to read, `SFE_Cmd_…` to send). To support it we need to see:

1. how the device is **described** (the `sfdiscovery` response),
2. how its **state** arrives (`getstatus` / `changestatus`),
3. which **commands** the app sends when you use it (`doaction`), and what happens after.

There are three ways to get this, from the easiest to the most complete.

## Capturing the app traffic

### 1. Debug log (no tools needed)

If the device already shows up in Home Assistant, even as unknown, a **debug log** is often enough:

1. **Settings → Devices & services → Vimar View Cloud → ⋮ → Enable debug logging**.
2. Use the device from the **Vimar app** (switch it on and off, move it, change its mode…), writing down what you did and when.
3. Disable debug logging: Home Assistant downloads the log. Lines like `Vimar: status idsf=… SFE_…=…` show every value the gateway sends.

This shows states but not the commands, so for new controls one of the methods below is better.

### 2. Frida (recommended)

[Frida](https://frida.re) reads the messages **inside the app**, already decrypted. No proxy and no certificates: the app works exactly as usual (with mitmproxy, for example, the *Routines* section disappears). It captures both the WebSocket and the REST calls.

**You need:** an Android device with **root**, or the **Android Studio emulator** with a *Google APIs* system image (these allow `adb root`).

**1. Prepare the emulator** (skip if you use a rooted phone)
- Install [Android Studio](https://developer.android.com/studio), then **Tools → Device Manager → +** → e.g. *Pixel 3a*.
- System image: **API 33 "Tiramisu" – Google APIs – x86_64** (*not* a "Google Play" image: those cannot run as root).
- Start the emulator and check that the **AndroidWifi** network is connected.
- Download the **Vimar VIEW** APK (e.g. from APKPure) and drag it onto the emulator window to install it. Open it and log in.

**2. Download the tools**
- `frida-inject` **16.7.19** from the [Frida releases](https://github.com/frida/frida/releases/tag/16.7.19):
  `frida-inject-16.7.19-android-x86_64.xz` for the emulator, `frida-inject-16.7.19-android-arm64.xz` for most phones. Extract the `.xz` (e.g. with 7-Zip).
  Use the **16.x** series: from 17.0 the Java bridge needed by the script is no longer built into `frida-inject`.
- The script [`tools/vimar_logger.js`](tools/vimar_logger.js) from this repository.

**3. Copy them to the device** (from the Android SDK `platform-tools` folder)
```bash
adb root                      # emulator only; on a rooted phone use "su" in the shell below
adb push frida-inject-16.7.19-android-x86_64 /data/local/tmp/frida-inject
adb push vimar_logger.js /data/local/tmp/vimar_logger.js
```

**4. Open the Vimar app, then attach the logger**
```bash
adb shell
su                            # rooted phone only
chmod 755 /data/local/tmp/frida-inject
/data/local/tmp/frida-inject -p $(pidof com.vimar.view) -s /data/local/tmp/vimar_logger.js 2>&1 | tee /data/local/tmp/vimar_log.txt
```
You should see `[+] WebSocket OkHttp agganciato` and `[+] HTTP OkHttp agganciato`.

**5. Use the device in the app**, slowly, one action at a time, and note what you did.

**6. Stop and get the log:** `Ctrl+C`, then `exit` (twice on a phone), then:
```bash
adb pull /data/local/tmp/vimar_log.txt
```

> [!TIP]
> If Windows refuses to load Frida on your PC ("an Application Control policy has blocked this file"), that is Smart App Control: `frida-inject` runs on the device, so it is not affected.

### 3. mitmproxy (no root)

[mitmproxy](https://mitmproxy.org) intercepts the traffic between the app and the cloud. It does not need root, but the app uses certificate pinning: the APK must be patched, and some sections (such as *Routines*) are hidden while the proxy is active. Device messages are captured fine.

<details>
<summary><b>Step by step</b></summary>

1. Create and start an emulator as in the Frida method (any image is fine) and check that **AndroidWifi** is **connected**: without it the traffic does not go through the proxy.
2. Install [Node.js LTS](https://nodejs.org) and then `npm install -g apk-mitm`. On Windows, if PowerShell refuses to run scripts: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
3. Install mitmproxy (`pip install mitmproxy`) and start `mitmweb --listen-port 8080`; the web UI opens at `http://127.0.0.1:8081`.
4. In the emulator: **Settings → Wi-Fi → AndroidWifi → edit → Proxy: manual**, host `10.0.2.2`, port `8080`.
5. In the emulator browser open `http://mitm.it` and install the **Android** certificate.
6. Patch the Vimar VIEW APK: `apk-mitm vimar-view.apk` (use the `.xapk` if it is an App Bundle), then drag the `*-patched.apk` onto the emulator.
7. Open the app, log in and use the device. In mitmweb, **File → Save** saves the `flows` file.

If you see no traffic, check AndroidWifi and the proxy settings; if the app cannot connect, install the certificate before opening the app and restart the emulator.
</details>

## Sending the capture

> [!WARNING]
> Captures contain **personal data**: your e-mail, access tokens, the gateway DUID, the plant id, secrets and even the GPS position of the plant. **Never post them as they are.**

Mask them with [`tools/sanitize_log.py`](tools/sanitize_log.py), then **read the result** before posting:

```bash
python tools/sanitize_log.py vimar_log.txt     # writes vimar_log.sanitized.txt
```

Then open an [issue](https://github.com/ivhazu/ha-vimar-view/issues) titled `[NEW DEVICE] <device>` with:
- the Vimar **product code** of the device (e.g. 30804);
- **what you did** in the app during the capture, in order (e.g. "opened the shutter to 50%, then stopped it");
- the **sanitized** capture as an attachment.

## Pull requests

- Start from the **latest `main`**, and keep the pull request focused: no unrelated changes, formatting or removed comments in other parts of the code.
- New entities must be created **only when the device exposes them** (check the device elements), so other users do not get entities stuck on "unknown".
- Detect devices by **type** (`sstype`, `SFE_…`), never by fixed ids: ids change from one plant to another.
- Never wait for a WebSocket response from inside the message handler (it blocks the read loop): send commands without waiting there.
- Add or update **tests** and the **README** (both languages). Leave the version number to the maintainer.

### Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install homeassistant pytest pytest-asyncio
python -m pytest tests
```

| File | Purpose |
|---|---|
| `api.py` | Cloud client: OAuth2 login, WebSocket, discovery, commands, REST API |
| `__init__.py` | Setup, routine tracker, gateway log, telemetry |
| `light.py`, `cover.py`, `climate.py`, `switch.py`, `sensor.py`, `number.py`, `select.py`, `button.py` | Entities by platform |
| `routines.py`, `gateway_log.py`, `telemetry.py`, `services.py` | Routines, event log, energy telemetry, services |
| `config_flow.py` | Setup flow (gateway list from the account) |
| `tools/` | Capture and sanitizing helpers for contributors |

Thank you! 🙏
