# Contribuire a Vimar View Cloud

[🇬🇧 English](CONTRIBUTING.md) · 🇮🇹 Italiano

Grazie per l'aiuto! Questa integrazione esiste perché tante persone hanno condiviso catture, provato le beta e mandato codice. Ci sono diversi modi per contribuire:

| Voglio… | Come |
|---|---|
| Segnalare un bug | Apri una [issue](https://github.com/ivhazu/ha-vimar-view/issues) con la versione dell'integrazione, cosa è successo e un [log di debug](#1-log-di-debug-nessuno-strumento) |
| Far supportare un nuovo dispositivo | Manda una [cattura](#catturare-il-traffico-dellapp) dell'app Vimar VIEW mentre usi quel dispositivo |
| Correggere o aggiungere codice | Apri una [pull request](#pull-request) |
| Migliorare traduzioni o documentazione | Modifica `custom_components/vimar_cloud/translations/*.json`, i `README*.md` o questa guida e apri una pull request |

---

## Cosa serve per supportare un nuovo dispositivo

Il gateway descrive ogni dispositivo Vimar con un **tipo** (`sftype`, `sstype`) e un elenco di **elementi** (`SFE_State_…` da leggere, `SFE_Cmd_…` da inviare). Per supportarlo dobbiamo vedere:

1. come il dispositivo viene **descritto** (la risposta a `sfdiscovery`),
2. come arriva il suo **stato** (`getstatus` / `changestatus`),
3. quali **comandi** invia l'app quando lo usi (`doaction`), e cosa succede dopo.

Ci sono tre modi per ottenerlo, dal più semplice al più completo.

## Catturare il traffico dell'app

### 1. Log di debug (nessuno strumento)

Se il dispositivo compare già in Home Assistant, anche come sconosciuto, spesso basta un **log di debug**:

1. **Impostazioni → Dispositivi e servizi → Vimar View Cloud → ⋮ → Abilita la registrazione di debug**.
2. Usa il dispositivo dall'**app Vimar** (accendi e spegni, muovi, cambia modalità…), annotando cosa fai e quando.
3. Disattiva la registrazione di debug: Home Assistant scarica il log. Le righe `Vimar: status idsf=… SFE_…=…` mostrano ogni valore inviato dal gateway.

Così si vedono gli stati ma non i comandi: per i comandi nuovi è meglio uno dei metodi qui sotto.

### 2. Frida (consigliato)

[Frida](https://frida.re) legge i messaggi **dentro l'app**, già decifrati. Niente proxy e niente certificati: l'app funziona esattamente come sempre (con mitmproxy, per esempio, la sezione *Routine* sparisce). Cattura sia il WebSocket sia le chiamate REST.

**Ti serve:** un dispositivo Android con **root**, oppure l'**emulatore di Android Studio** con un'immagine *Google APIs* (che permette `adb root`).

**1. Prepara l'emulatore** (salta se usi un telefono con root)
- Installa [Android Studio](https://developer.android.com/studio), poi **Tools → Device Manager → +** → per esempio *Pixel 3a*.
- Immagine di sistema: **API 33 "Tiramisu" – Google APIs – x86_64** (*non* un'immagine "Google Play": quelle non possono andare in root).
- Avvia l'emulatore e controlla che la rete **AndroidWifi** sia connessa.
- Scarica l'APK di **Vimar VIEW** (per esempio da APKPure) e trascinalo sulla finestra dell'emulatore per installarlo. Aprilo e fai il login.

**2. Scarica gli strumenti**
- `frida-inject` **16.7.19** dalle [release di Frida](https://github.com/frida/frida/releases/tag/16.7.19):
  `frida-inject-16.7.19-android-x86_64.xz` per l'emulatore, `frida-inject-16.7.19-android-arm64.xz` per la maggior parte dei telefoni. Estrai il file `.xz` (per esempio con 7-Zip).
  Usa la serie **16.x**: dalla 17.0 il bridge Java che serve allo script non è più incluso in `frida-inject`.
- Lo script [`tools/vimar_logger.js`](tools/vimar_logger.js) di questo repository.

**3. Copiali sul dispositivo** (dalla cartella `platform-tools` dell'SDK Android)
```bash
adb root                      # solo emulatore; su un telefono con root usa "su" nella shell qui sotto
adb push frida-inject-16.7.19-android-x86_64 /data/local/tmp/frida-inject
adb push vimar_logger.js /data/local/tmp/vimar_logger.js
```

**4. Apri l'app Vimar, poi aggancia il logger**
```bash
adb shell
su                            # solo telefono con root
chmod 755 /data/local/tmp/frida-inject
/data/local/tmp/frida-inject -p $(pidof com.vimar.view) -s /data/local/tmp/vimar_logger.js 2>&1 | tee /data/local/tmp/vimar_log.txt
```
Dovresti vedere `[+] WebSocket OkHttp agganciato` e `[+] HTTP OkHttp agganciato`.

**5. Usa il dispositivo nell'app**, con calma, un'azione alla volta, e annota cosa fai.

**6. Ferma e recupera il log:** `Ctrl+C`, poi `exit` (due volte su un telefono), poi:
```bash
adb pull /data/local/tmp/vimar_log.txt
```

> [!TIP]
> Se Windows impedisce di avviare Frida sul PC ("Un criterio di controllo dell'applicazione ha bloccato il file"), è lo Smart App Control: `frida-inject` gira sul dispositivo, quindi non ne è influenzato.

### 3. mitmproxy (senza root)

[mitmproxy](https://mitmproxy.org) intercetta il traffico tra l'app e il cloud. Non serve il root, ma l'app usa il certificate pinning: l'APK va modificato, e alcune sezioni (come le *Routine*) spariscono quando il proxy è attivo. I messaggi dei dispositivi vengono comunque catturati.

<details>
<summary><b>Passo per passo</b></summary>

1. Crea e avvia un emulatore come nel metodo Frida (va bene qualsiasi immagine) e controlla che **AndroidWifi** sia **connessa**: senza, il traffico non passa dal proxy.
2. Installa [Node.js LTS](https://nodejs.org) e poi `npm install -g apk-mitm`. Su Windows, se PowerShell rifiuta gli script: `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`.
3. Installa mitmproxy (`pip install mitmproxy`) e avvia `mitmweb --listen-port 8080`; l'interfaccia si apre su `http://127.0.0.1:8081`.
4. Nell'emulatore: **Impostazioni → Wi-Fi → AndroidWifi → modifica → Proxy: manuale**, host `10.0.2.2`, porta `8080`.
5. Nel browser dell'emulatore apri `http://mitm.it` e installa il certificato **Android**.
6. Modifica l'APK di Vimar VIEW: `apk-mitm vimar-view.apk` (usa il `.xapk` se è un App Bundle), poi trascina il `*-patched.apk` sull'emulatore.
7. Apri l'app, fai il login e usa il dispositivo. In mitmweb, **File → Save** salva il file `flows`.

Se non vedi traffico, controlla AndroidWifi e il proxy; se l'app non si connette, installa il certificato prima di aprire l'app e riavvia l'emulatore.
</details>

## Inviare la cattura

> [!WARNING]
> Le catture contengono **dati personali**: la tua email, i token di accesso, il DUID del gateway, l'identificativo dell'impianto, codici segreti e perfino la posizione GPS dell'impianto. **Non pubblicarle mai così come sono.**

Mascherali con [`tools/sanitize_log.py`](tools/sanitize_log.py), poi **rileggi il risultato** prima di pubblicarlo:

```bash
python tools/sanitize_log.py vimar_log.txt     # crea vimar_log.sanitized.txt
```

Poi apri una [issue](https://github.com/ivhazu/ha-vimar-view/issues) con titolo `[NEW DEVICE] <dispositivo>` e indica:
- il **codice prodotto** Vimar del dispositivo (per esempio 30804);
- **cosa hai fatto** nell'app durante la cattura, in ordine (per esempio "ho aperto la tapparella al 50%, poi l'ho fermata");
- la cattura **mascherata** come allegato.

## Pull request

- Parti dall'**ultimo `main`** e mantieni la pull request mirata: niente modifiche, formattazioni o commenti rimossi in altre parti del codice.
- Le nuove entità vanno create **solo se il dispositivo le espone** (controlla gli elementi del dispositivo), così gli altri utenti non si ritrovano entità sempre "sconosciute".
- Riconosci i dispositivi dal **tipo** (`sstype`, `SFE_…`), mai da identificativi fissi: cambiano da un impianto all'altro.
- Non attendere mai una risposta del WebSocket dall'interno del gestore dei messaggi (blocca il ciclo di lettura): lì invia i comandi senza attendere.
- Aggiungi o aggiorna i **test** e il **README** (in entrambe le lingue). Lascia il numero di versione al maintainer.

### Ambiente di sviluppo

```bash
python -m venv .venv && source .venv/bin/activate
pip install homeassistant pytest pytest-asyncio
python -m pytest tests
```

| File | A cosa serve |
|---|---|
| `api.py` | Client del cloud: login OAuth2, WebSocket, discovery, comandi, API REST |
| `__init__.py` | Avvio, routine, registro eventi, telemetria |
| `light.py`, `cover.py`, `climate.py`, `switch.py`, `sensor.py`, `number.py`, `select.py`, `button.py` | Entità per piattaforma |
| `routines.py`, `gateway_log.py`, `telemetry.py`, `services.py` | Routine, registro eventi, telemetria energia, servizi |
| `config_flow.py` | Configurazione (elenco dei gateway dell'account) |
| `tools/` | Strumenti per catturare e mascherare il traffico |

Grazie! 🙏
