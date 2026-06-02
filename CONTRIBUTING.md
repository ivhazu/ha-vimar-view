# Contributing to ha-vimar-view

> 🇮🇹 [Italiano](#italiano) | 🇬🇧 [English](#english)

---

## Italiano

### Come contribuire al supporto di nuovi dispositivi

Grazie per voler contribuire! Questa guida spiega come intercettare il traffico del protocollo Vimar View per aggiungere il supporto a nuovi dispositivi (tapparelle, climatizzatori, citofoni, ecc.).

> ⚠️ **Prerequisiti**: PC con Windows/Mac/Linux, connessione WiFi, account MyVimar attivo.

---

### Strumenti necessari

| Strumento | Uso | Download |
|---|---|---|
| **Python 3.8+** | Richiesto da mitmproxy | [python.org](https://www.python.org/downloads/) |
| **mitmproxy** | Intercetta il traffico HTTPS | `pip install mitmproxy` |
| **Android Studio** | Emulatore Android | [developer.android.com/studio](https://developer.android.com/studio) |
| **APK Vimar View** | App da installare nell'emulatore | APKPure o APKMirror |

---

### Fase 1 — Installazione di mitmproxy

**1. Installa Python** scaricandolo da [python.org](https://www.python.org/downloads/).  
Su Windows spunta obbligatoriamente **"Add Python to PATH"** durante l'installazione.

**2. Installa mitmproxy:**
```bash
pip install mitmproxy
```

**3. Verifica l'installazione:**
```bash
mitmproxy --version
```

**4. Avvia mitmweb** (interfaccia grafica nel browser):
```bash
mitmweb --listen-port 8080
```
Si aprirà automaticamente `http://127.0.0.1:8081` nel browser. **Lascia questo terminale aperto.**

**5. Trova l'IP del tuo PC:**
```bash
# Windows
ipconfig
# Mac/Linux
ip addr
```
Cerca "Indirizzo IPv4" — sarà qualcosa come `192.168.1.100`. Annotalo.

---

### Fase 2 — Creazione dell'emulatore Android

**1. Installa Android Studio** da [developer.android.com/studio](https://developer.android.com/studio).

**2. Crea un emulatore con API 33 e Google APIs** (senza Play Store):
- Apri Android Studio → **Tools → Device Manager**
- Clicca **+** → scegli **Pixel 3a**
- Nella selezione immagine: filtra per **API 33 "Tiramisu"** con **Services: Google APIs** (NON Google Play Store)
- Scarica l'immagine se necessario e clicca **Finish**
- Avvia l'emulatore con ▶

> ⚠️ **Importante**: scegli "Google APIs" e NON "Google Play Store". La versione senza Play Store permette di installare il certificato mitmproxy come certificato di sistema.

**3. Configura il proxy nell'emulatore:**
- Clicca i tre puntini `⋮` nel pannello laterale dell'emulatore
- Vai in **Settings → Proxy → Manual proxy configuration**
- Inserisci:
  - **Host**: IP del tuo PC (es. `192.168.1.100`)
  - **Port**: `8080`
- Clicca **Apply**

---

### Fase 3 — Installazione del certificato mitmproxy

**1. Scarica il certificato:**  
Nell'emulatore, apri Chrome e vai su `http://mitm.it` → clicca **Get mitmproxy-ca-cert.pem** (Android).

**2. Installa il certificato come certificato di sistema tramite ADB:**

Apri un terminale sul PC e individua ADB:
```
# Windows
C:\Users\<utente>\AppData\Local\Android\Sdk\platform-tools\adb.exe

# Mac/Linux
~/Android/Sdk/platform-tools/adb
```

Esegui questi comandi (sostituisci il percorso di adb se necessario):
```bash
# Verifica che l'emulatore sia connesso
adb devices

# Ottieni i permessi root
adb root
adb remount

# Calcola l'hash del certificato
python3 -c "
from cryptography import x509
from cryptography.hazmat.primitives import hashes
import struct, hashlib
with open('/percorso/.mitmproxy/mitmproxy-ca-cert.pem', 'rb') as f:
    cert = x509.load_pem_x509_certificate(f.read())
subject_der = cert.subject.public_bytes()
md5 = hashlib.md5(subject_der).digest()
hash_val = struct.unpack('<I', md5[:4])[0] & 0x7fffffff
print(format(hash_val, '08x'))
"
```
> Su Windows il file `.mitmproxy` si trova in `C:\Users\<utente>\.mitmproxy\`

Il comando stampa un hash tipo `c8750f0d`. Usalo nel comando successivo:

```bash
# Copia il certificato come certificato di sistema (sostituisci HASH con il valore ottenuto)
adb push ~/.mitmproxy/mitmproxy-ca-cert.pem /system/etc/security/cacerts/HASH.0
adb shell chmod 644 /system/etc/security/cacerts/HASH.0
adb reboot
```

**3. Installa la libreria cryptography se mancante:**
```bash
pip install cryptography
```

**4. Verifica:** dopo il riavvio, apri Chrome nell'emulatore e vai su `https://example.com`. Se la pagina carica E in mitmweb compaiono richieste, il certificato è installato correttamente.

---

### Fase 4 — Installazione dell'app Vimar View

**1. Scarica l'APK** da [APKMirror](https://www.apkmirror.com) o [APKPure](https://apkpure.com) cercando "Vimar View". Scarica la versione più recente in formato **APK** (non XAPK).

**2. Installa l'APK nell'emulatore:**
```bash
adb install /percorso/vimar-view.apk
```

Se compare l'errore `INSTALL_FAILED_MISSING_SPLIT`, l'APK è uno split APK. In questo caso scarica tutti i file e installa con:
```bash
adb install-multiple base.apk split_config.arm64_v8a.apk split_config.xxhdpi.apk
```

---

### Fase 5 — Cattura del traffico

**1. Assicurati che mitmweb sia attivo** (`http://127.0.0.1:8081` aperto nel browser).

**2. Apri Vimar View nell'emulatore** e fai il login con le tue credenziali MyVimar.

**3. Naviga nei dispositivi che vuoi supportare:**
- Apri ogni tipo di dispositivo (tapparella, climatizzatore, ecc.)
- Esegui le azioni principali: apri/chiudi, imposta temperatura, ecc.
- Ogni azione genera chiamate API che mitmweb cattura

**4. In mitmweb** cerca le richieste verso `prod.vimar.cloud` e clicca su quelle interessanti.

**5. Salva la cattura:**  
In mitmweb → **File → Save** → salva come `vimar_capture.flow`

---

### Fase 6 — Analisi e contribuzione

**1. Apri il file `.flow`** con mitmweb per analizzare le richieste:
```bash
mitmweb --rfile vimar_capture.flow
```

**2. Per ogni nuovo tipo di dispositivo, annota:**

| Campo | Dove trovarlo | Esempio |
|---|---|---|
| `sftype` | Risposta sfdiscovery | `SF_Shutter` |
| `sstype` | Risposta sfdiscovery | `SS_Shutter_UpDown` |
| `SFE_State_*` | Elementi del dispositivo | `SFE_State_Position` |
| `SFE_Cmd_*` | Elementi del dispositivo | `SFE_Cmd_Position` |
| Valori possibili | Messaggi changestatus | `"0"` ... `"100"` |

**3. Apri una Issue su GitHub** con il titolo `[NEW DEVICE] <tipo dispositivo>` e includi:
- Il log della discovery (messaggi `sfdiscovery` e `getstatus`)
- I messaggi `changestatus` catturati durante l'uso
- Il modello Vimar del dispositivo (codice commerciale)

**4. In alternativa, apri una Pull Request** con l'implementazione seguendo la struttura esistente dei file `light.py`, `sensor.py`, ecc.

---

### Risoluzione problemi comuni

**Il proxy non funziona (nessuna richiesta in mitmweb)**
- Verifica che IP e porta siano corretti nelle impostazioni proxy dell'emulatore
- Controlla che il firewall del PC non blocchi la porta 8080
- Riavvia mitmweb e riprova

**L'app mostra "Connessione non disponibile"**
- Il certificato mitmproxy non è installato correttamente come certificato di sistema
- Riprova la Fase 3 con `adb root` e `adb remount`

**`adb root` dà errore "adbd cannot run as root in production builds"**
- Stai usando un'immagine "Google Play Store" invece di "Google APIs"
- Crea un nuovo emulatore con l'immagine corretta (Fase 2)

**L'APK non si installa (`CPU_ABI_INCOMPATIBLE`)**
- Scarica la versione "universal" dell'APK che supporta tutte le architetture

---

## English

### How to contribute support for new devices

Thank you for wanting to contribute! This guide explains how to intercept Vimar View protocol traffic to add support for new devices (roller shutters, air conditioners, intercoms, etc.).

> ⚠️ **Prerequisites**: PC with Windows/Mac/Linux, WiFi connection, active MyVimar account.

---

### Required tools

| Tool | Use | Download |
|---|---|---|
| **Python 3.8+** | Required by mitmproxy | [python.org](https://www.python.org/downloads/) |
| **mitmproxy** | Intercepts HTTPS traffic | `pip install mitmproxy` |
| **Android Studio** | Android emulator | [developer.android.com/studio](https://developer.android.com/studio) |
| **Vimar View APK** | App to install in emulator | APKPure or APKMirror |

---

### Phase 1 — Install mitmproxy

**1. Install Python** from [python.org](https://www.python.org/downloads/).  
On Windows, check **"Add Python to PATH"** during installation.

**2. Install mitmproxy:**
```bash
pip install mitmproxy
```

**3. Verify installation:**
```bash
mitmproxy --version
```

**4. Start mitmweb** (browser-based GUI):
```bash
mitmweb --listen-port 8080
```
This will open `http://127.0.0.1:8081` in your browser. **Keep this terminal open.**

**5. Find your PC's IP address:**
```bash
# Windows
ipconfig
# Mac/Linux
ip addr
```
Look for "IPv4 Address" — it will be something like `192.168.1.100`. Note it down.

---

### Phase 2 — Create Android emulator

**1. Install Android Studio** from [developer.android.com/studio](https://developer.android.com/studio).

**2. Create an emulator with API 33 and Google APIs** (without Play Store):
- Open Android Studio → **Tools → Device Manager**
- Click **+** → choose **Pixel 3a**
- In the system image selection: filter for **API 33 "Tiramisu"** with **Services: Google APIs** (NOT Google Play Store)
- Download the image if needed and click **Finish**
- Start the emulator with ▶

> ⚠️ **Important**: choose "Google APIs" and NOT "Google Play Store". The version without Play Store allows installing the mitmproxy certificate as a system certificate.

**3. Configure proxy in emulator:**
- Click the three dots `⋮` in the emulator side panel
- Go to **Settings → Proxy → Manual proxy configuration**
- Enter:
  - **Host**: your PC's IP (e.g. `192.168.1.100`)
  - **Port**: `8080`
- Click **Apply**

---

### Phase 3 — Install mitmproxy certificate

**1. Download the certificate:**  
In the emulator, open Chrome and go to `http://mitm.it` → click **Get mitmproxy-ca-cert.pem** (Android).

**2. Install the certificate as a system certificate via ADB:**

Open a terminal on your PC and locate ADB:
```
# Windows
C:\Users\<user>\AppData\Local\Android\Sdk\platform-tools\adb.exe

# Mac/Linux
~/Android/Sdk/platform-tools/adb
```

Run these commands:
```bash
# Verify emulator is connected
adb devices

# Get root permissions
adb root
adb remount

# Calculate certificate hash
python3 -c "
from cryptography import x509
from cryptography.hazmat.primitives import hashes
import struct, hashlib
with open('/path/.mitmproxy/mitmproxy-ca-cert.pem', 'rb') as f:
    cert = x509.load_pem_x509_certificate(f.read())
subject_der = cert.subject.public_bytes()
md5 = hashlib.md5(subject_der).digest()
hash_val = struct.unpack('<I', md5[:4])[0] & 0x7fffffff
print(format(hash_val, '08x'))
"
```
> On Windows the `.mitmproxy` folder is in `C:\Users\<user>\.mitmproxy\`

The command prints a hash like `c8750f0d`. Use it in the next command:

```bash
# Copy certificate as system certificate (replace HASH with the value obtained)
adb push ~/.mitmproxy/mitmproxy-ca-cert.pem /system/etc/security/cacerts/HASH.0
adb shell chmod 644 /system/etc/security/cacerts/HASH.0
adb reboot
```

**3. Install cryptography library if missing:**
```bash
pip install cryptography
```

**4. Verify:** after reboot, open Chrome in the emulator and go to `https://example.com`. If the page loads AND requests appear in mitmweb, the certificate is correctly installed.

---

### Phase 4 — Install Vimar View app

**1. Download the APK** from [APKMirror](https://www.apkmirror.com) or [APKPure](https://apkpure.com) by searching "Vimar View". Download the latest version in **APK** format (not XAPK).

**2. Install the APK in the emulator:**
```bash
adb install /path/to/vimar-view.apk
```

If you get `INSTALL_FAILED_MISSING_SPLIT`, it's a split APK. In that case download all files and install with:
```bash
adb install-multiple base.apk split_config.arm64_v8a.apk split_config.xxhdpi.apk
```

---

### Phase 5 — Capture traffic

**1. Make sure mitmweb is running** (`http://127.0.0.1:8081` open in browser).

**2. Open Vimar View in the emulator** and log in with your MyVimar credentials.

**3. Navigate to the devices you want to support:**
- Open each device type (shutter, air conditioner, etc.)
- Perform the main actions: open/close, set temperature, etc.
- Each action generates API calls that mitmweb captures

**4. In mitmweb** look for requests to `prod.vimar.cloud` and click on the interesting ones.

**5. Save the capture:**  
In mitmweb → **File → Save** → save as `vimar_capture.flow`

---

### Phase 6 — Analysis and contribution

**1. Open the `.flow` file** with mitmweb to analyze requests:
```bash
mitmweb --rfile vimar_capture.flow
```

**2. For each new device type, note:**

| Field | Where to find it | Example |
|---|---|---|
| `sftype` | sfdiscovery response | `SF_Shutter` |
| `sstype` | sfdiscovery response | `SS_Shutter_UpDown` |
| `SFE_State_*` | Device elements | `SFE_State_Position` |
| `SFE_Cmd_*` | Device elements | `SFE_Cmd_Position` |
| Possible values | changestatus messages | `"0"` ... `"100"` |

**3. Open a GitHub Issue** with title `[NEW DEVICE] <device type>` and include:
- Discovery log (sfdiscovery and getstatus messages)
- changestatus messages captured during use
- Vimar device model (commercial code)

**4. Alternatively, open a Pull Request** with the implementation following the existing structure of `light.py`, `sensor.py`, etc.

---

### Common troubleshooting

**Proxy not working (no requests in mitmweb)**
- Verify IP and port are correct in emulator proxy settings
- Check that your PC firewall doesn't block port 8080
- Restart mitmweb and try again

**App shows "Connection not available"**
- The mitmproxy certificate is not correctly installed as a system certificate
- Redo Phase 3 with `adb root` and `adb remount`

**`adb root` gives error "adbd cannot run as root in production builds"**
- You are using a "Google Play Store" image instead of "Google APIs"
- Create a new emulator with the correct image (Phase 2)

**APK fails to install (`CPU_ABI_INCOMPATIBLE`)**
- Download the "universal" version of the APK that supports all architectures

---

*For questions or help, open an [Issue](https://github.com/ivhazu/ha-vimar-view/issues) on GitHub.*
