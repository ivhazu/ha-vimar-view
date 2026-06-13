# Contributing to ha-vimar-view

> 🇮🇹 [Italiano](#italiano) | 🇬🇧 [English](#english)

---

## Italiano

### Come contribuire al supporto di nuovi dispositivi

Grazie per voler contribuire! Questa guida spiega come intercettare il traffico del protocollo Vimar View per aggiungere il supporto a nuovi dispositivi (tapparelle, scenari, climatizzatori, citofoni, ecc.).

La procedura è completamente **user-friendly**: niente root, niente comandi da terminale per il certificato, niente configurazioni avanzate. Bastano un PC e un emulatore Android.

> ⚠️ **Prerequisiti**: PC con Windows/Mac/Linux, account MyVimar attivo con almeno un impianto configurato.

---

### Strumenti necessari

| Strumento | Uso | Download |
|---|---|---|
| **Android Studio** | Emulatore Android | [developer.android.com/studio](https://developer.android.com/studio) |
| **Node.js** | Richiesto da apk-mitm | [nodejs.org](https://nodejs.org) — scarica la versione **LTS**, installer `.msi` |
| **apk-mitm** | Patcha l'APK per accettare il proxy | `npm install -g apk-mitm` |
| **mitmproxy** | Intercetta il traffico | [mitmproxy.org](https://mitmproxy.org/) (incluso `mitmweb`) |
| **APK Vimar View** | App da installare nell'emulatore | [APKPure](https://apkpure.com) |

---

### Procedura passo-passo

**1. Installa Android Studio**
Scarica da [developer.android.com/studio](https://developer.android.com/studio) e installa con le opzioni di default.

**2. Crea ed avvia un emulatore**
- **Tools → Device Manager → +** → scegli **Pixel 3a**
- Immagine: **API 33 "Tiramisu"** con **Google APIs** (va bene anche con Play Store)
- Avvia l'emulatore con ▶

**3. Attiva il WiFi nell'emulatore**
Apri le impostazioni dell'emulatore e assicurati che la rete **AndroidWifi** sia **attiva** (è il passaggio facile da dimenticare ma essenziale: senza WiFi attivo l'emulatore non instrada correttamente il traffico verso il proxy).

**4. Installa Node.js**
Scarica l'installer **Windows Installer (.msi)** da [nodejs.org](https://nodejs.org) (versione LTS) ed esegui con le opzioni di default.

Se PowerShell dà errore "esecuzione script disabilitata", esegui prima:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**5. Avvia mitmproxy**
```bash
pip install mitmproxy
mitmweb --listen-port 8080
```
Si apre `http://127.0.0.1:8081` nel browser — **lascialo aperto**.

**6. Configura il proxy nell'emulatore**
- Impostazioni emulatore → **WiFi → AndroidWifi → modifica**
- Proxy manuale:
  - **Host**: `10.0.2.2`
  - **Port**: `8080`

**7. Installa il certificato mitmproxy**
Nel browser dell'emulatore vai su `http://mitm.it` → scarica e installa il certificato per **Android** (CA certificate).

**8. Patcha l'APK con apk-mitm**
```bash
npm install -g apk-mitm
```
Scarica l'APK di **Vimar View** da [APKPure](https://apkpure.com) (formato `.apk`, non `.xapk` se possibile), poi:
```bash
apk-mitm vimar-view.apk
```
Genera un file `*-patched.apk`.

> Se l'app è un App Bundle (più file), scarica il `.xapk` da APKPure e ripeti il comando con quel file.

**9. Installa l'APK patchato**
Trascina semplicemente il file `*-patched.apk` sulla finestra dell'emulatore — si installa automaticamente.

**10. Cattura il traffico**
- Apri l'app **Vimar View** patchata nell'emulatore e fai login con le tue credenziali MyVimar
- Naviga nei dispositivi/scenari che vuoi documentare (apri tapparelle, attiva scenari, ecc.)
- In mitmweb, **File → Save** → salva il file `flows`

---

### Cosa fare con il file `flows`

**1. Apri una Issue su GitHub** con titolo `[NEW DEVICE] <tipo dispositivo>` o `[BUG] <descrizione>` e allega il file `flows`.

**2. Indica nel messaggio:**
- Il modello/codice commerciale del dispositivo Vimar
- Cosa hai fatto nell'app mentre catturavi (es. "ho aperto la tapparella al 50%")
- Eventuali messaggi di errore visti in Home Assistant

**3. In alternativa, apri una Pull Request** con l'implementazione seguendo la struttura esistente dei file `light.py`, `cover.py`, `sensor.py`, ecc.

---

### Risoluzione problemi comuni

**Non vedo traffico in mitmweb**
- Verifica che il WiFi **AndroidWifi** sia attivo nell'emulatore (passo 3) — senza questo il proxy non funziona anche se configurato correttamente
- Verifica che host/porta del proxy siano `10.0.2.2:8080`

**L'app non si connette / errore di sistema**
- Assicurati di aver installato il certificato mitmproxy (passo 7) **prima** di aprire l'app patchata
- Riavvia l'emulatore dopo aver installato il certificato

**apk-mitm dice "Android App Bundle"**
- Scarica il file `.xapk` da APKPure invece del singolo `.apk` e ripeti `apk-mitm` con quel file

**L'APK patchato non si installa**
- Verifica di aver trascinato il file `*-patched.apk` (non l'originale) sulla finestra dell'emulatore

---

## English

### How to contribute support for new devices

Thank you for wanting to contribute! This guide explains how to intercept Vimar View protocol traffic to add support for new devices (roller shutters, scenes, air conditioners, intercoms, etc.).

The procedure is fully **user-friendly**: no root, no terminal commands for certificates, no advanced configuration. Just a PC and an Android emulator.

> ⚠️ **Prerequisites**: PC with Windows/Mac/Linux, active MyVimar account with at least one configured plant.

---

### Required tools

| Tool | Use | Download |
|---|---|---|
| **Android Studio** | Android emulator | [developer.android.com/studio](https://developer.android.com/studio) |
| **Node.js** | Required by apk-mitm | [nodejs.org](https://nodejs.org) — download the **LTS** version, `.msi` installer |
| **apk-mitm** | Patches the APK to trust the proxy | `npm install -g apk-mitm` |
| **mitmproxy** | Intercepts traffic | [mitmproxy.org](https://mitmproxy.org/) (includes `mitmweb`) |
| **Vimar View APK** | App to install in the emulator | [APKPure](https://apkpure.com) |

---

### Step-by-step procedure

**1. Install Android Studio**
Download from [developer.android.com/studio](https://developer.android.com/studio) and install with default options.

**2. Create and start an emulator**
- **Tools → Device Manager → +** → choose **Pixel 3a**
- Image: **API 33 "Tiramisu"** with **Google APIs** (Play Store version is fine too)
- Start the emulator with ▶

**3. Enable WiFi in the emulator**
Open the emulator settings and make sure the **AndroidWifi** network is **enabled** (this is the easy step to miss but it's essential: without WiFi enabled the emulator won't route traffic through the proxy correctly).

**4. Install Node.js**
Download the **Windows Installer (.msi)** from [nodejs.org](https://nodejs.org) (LTS version) and install with default options.

If PowerShell gives a "script execution disabled" error, run first:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

**5. Start mitmproxy**
```bash
pip install mitmproxy
mitmweb --listen-port 8080
```
This opens `http://127.0.0.1:8081` in your browser — **keep it open**.

**6. Configure the proxy in the emulator**
- Emulator settings → **WiFi → AndroidWifi → modify**
- Manual proxy:
  - **Host**: `10.0.2.2`
  - **Port**: `8080`

**7. Install the mitmproxy certificate**
In the emulator's browser go to `http://mitm.it` → download and install the certificate for **Android** (CA certificate).

**8. Patch the APK with apk-mitm**
```bash
npm install -g apk-mitm
```
Download the **Vimar View** APK from [APKPure](https://apkpure.com) (`.apk` format if possible, not `.xapk`), then:
```bash
apk-mitm vimar-view.apk
```
This generates a `*-patched.apk` file.

> If the app is an App Bundle (multiple files), download the `.xapk` from APKPure and repeat the command with that file.

**9. Install the patched APK**
Simply drag and drop the `*-patched.apk` file onto the emulator window — it installs automatically.

**10. Capture traffic**
- Open the patched **Vimar View** app in the emulator and log in with your MyVimar credentials
- Navigate to the devices/scenes you want to document (open shutters, trigger scenes, etc.)
- In mitmweb, **File → Save** → save the `flows` file

---

### What to do with the `flows` file

**1. Open a GitHub Issue** titled `[NEW DEVICE] <device type>` or `[BUG] <description>` and attach the `flows` file.

**2. Include in your message:**
- The Vimar device model/commercial code
- What you did in the app while capturing (e.g. "I opened the shutter to 50%")
- Any error messages seen in Home Assistant

**3. Alternatively, open a Pull Request** with the implementation following the existing structure of `light.py`, `cover.py`, `sensor.py`, etc.

---

### Common troubleshooting

**No traffic in mitmweb**
- Make sure **AndroidWifi** is enabled in the emulator (step 3) — without this the proxy won't work even if configured correctly
- Check that the proxy host/port are `10.0.2.2:8080`

**App doesn't connect / system error**
- Make sure you installed the mitmproxy certificate (step 7) **before** opening the patched app
- Restart the emulator after installing the certificate

**apk-mitm says "Android App Bundle"**
- Download the `.xapk` file from APKPure instead of the single `.apk` and repeat `apk-mitm` with that file

**Patched APK won't install**
- Make sure you dragged the `*-patched.apk` file (not the original) onto the emulator window

---

*For questions or help, open an [Issue](https://github.com/ivhazu/ha-vimar-view/issues) on GitHub.*
