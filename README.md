# Vimar View Cloud — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.6.0-brightgreen.svg)](https://github.com/ivhazu/ha-vimar-view/releases)

> 🇮🇹 [Italiano](#italiano) | 🇬🇧 [English](#english)

---

## Italiano

### Descrizione

Integrazione non ufficiale per **Home Assistant** che permette di controllare e monitorare i dispositivi del sistema domotico **Vimar View Wireless** tramite cloud.

Utilizza il protocollo WebSocket proprietario Vimar (`prod.vimar.cloud`) con autenticazione OAuth2 PKCE — lo stesso utilizzato dall'app ufficiale Vimar View.

> ⚠️ **Nota**: questa è un'integrazione **non ufficiale** e non è affiliata a Vimar S.p.A. Sviluppata tramite reverse engineering del protocollo dell'app View.

---

### Dispositivi supportati e testati

| Dispositivo | Codice Vimar | Tipo HA | Funzioni |
|---|---|---|---|
| Gateway IoT | **14597** | — | Dispositivo radice, firmware, MAC |
| Gateway IoT | **30807** | — | Dispositivo radice, firmware, MAC |
| Deviatore connesso | **14592** | `light` | On/Off |
| Modulo relè | **03981** | `light` | On/Off |
| Dimmer connesso | **14595** | `light` | On/Off, Luminosità |
| Attuatore di carico | **14593** | `sensor` + `select` + `button` | Potenza W, kWh, Stato, Modalità, Ripristina |
| Energy Meter | **02963** | `sensor` + `number` | Consumo totale W/kWh, Soglia alert/distacco |
| Tapparella connessa | **30804** | `cover` | Apri, Chiudi, Stop, Posizione % |

---

### Entità create

#### Per ogni luce / dimmer
| Entità | Tipo | Descrizione |
|---|---|---|
| `light.<nome>` | Light | Controllo on/off e dimmer |

#### Per ogni attuatore di carico
| Entità | Tipo | Descrizione |
|---|---|---|
| `sensor.<nome>_potenza` | Sensor (W) | Potenza istantanea |
| `sensor.<nome>_energia` | Sensor (kWh) | Energia accumulata (persiste ai riavvii) |
| `sensor.<nome>_stato` | Sensor | Stato testuale (Auto on / Forced on / ecc.) |
| `select.<nome>_modalita` | Select | Controllo modalità: Auto / Forced on / Forced off |
| `button.<nome>_ripristina` | Button | Ripristina il carico in modalità Auto |

#### Per ogni tapparella
| Entità | Tipo | Descrizione |
|---|---|---|
| `cover.<nome>` | Cover | Apri, Chiudi, Stop, Posizione % (0=chiusa, 100=aperta) |

#### Per ogni Scenario
| Entità | Tipo | Descrizione |
|---|---|---|
| `button.<nome>` | Button | Attiva lo scenario Vimar associato |

> ⚠️ **Nota**: gli scenari sono ancora **in fase di test** — se il pulsante non sembra avere effetto, apri una [Issue](https://github.com/ivhazu/ha-vimar-view/issues) con i dettagli (vedi [CONTRIBUTING](CONTRIBUTING.md)).

#### Per l'Energy Manager
| Entità | Tipo | Descrizione |
|---|---|---|
| `sensor.consumo_totale` | Sensor (W) | Potenza totale istantanea |
| `sensor.consumo_totale_kwh` | Sensor (kWh) | Energia totale accumulata |
| `sensor.soglia_alert` | Sensor (W) | Soglia di allerta attuale |
| `sensor.soglia_distacco` | Sensor (W) | Soglia di distacco attuale |
| `number.imposta_soglia_alert` | Number | Modifica soglia alert |
| `number.imposta_soglia_distacco` | Number | Modifica soglia distacco |
| `button.ripristina_tutti_i_carichi` | Button | Ripristina tutti i carichi in Auto |

---

### Requisiti

- Home Assistant **2024.1.0** o superiore
- Account **MyVimar** attivo
- Sistema domotico **Vimar View Wireless** connesso e raggiungibile
- Piano **gratuito** MyVimar (sufficiente per tutte le funzioni implementate)

---

### Installazione

#### Tramite HACS (consigliato)

1. Apri HACS in Home Assistant
2. Vai su **Integrazioni** → menu `⋮` → **Repository personalizzati**
3. Aggiungi: `https://github.com/ivhazu/ha-vimar-view`
4. Cerca "Vimar View Cloud" e installa
5. Riavvia Home Assistant

#### Installazione manuale

1. Scarica l'ultima release da [Releases](https://github.com/ivhazu/ha-vimar-view/releases)
2. Copia la cartella `vimar_cloud` in `/config/custom_components/`
3. Riavvia Home Assistant

---

### Configurazione

1. Vai in **Impostazioni → Dispositivi e servizi → Aggiungi integrazione**
2. Cerca **"Vimar View Cloud"**
3. Inserisci:
   - **Email MyVimar** — la stessa usata nell'app View
   - **Password MyVimar**
   - **DUID Gateway** — vedi sezione dedicata qui sotto

---

### Come trovare il DUID del gateway

Il DUID è l'identificatore univoco del tuo gateway Vimar. Puoi trovarlo in due modi:

#### Metodo 1 — App Vimar View
1. Apri l'app **Vimar View** sul telefono
2. Vai in **Impostazioni** (icona ⚙️ in basso a destra)
3. Vai in **Info di sistema**
4. Il DUID è mostrato come **BLEG** nel formato `000000AAA00000`

#### Metodo 2 — Da mitmproxy (avanzato)
Se non riesci a trovarlo nell'app, puoi catturarlo intercettando il traffico dell'app con mitmproxy. Il DUID appare nell'URL della connessione WebSocket:
```
wss://prod.vimar.cloud/wssmqtt/deviceproxy?duid=000000AAA00000&access_token=...
```

---

### Dashboard Energia di Home Assistant

I sensori kWh dell'integrazione sono compatibili con la **dashboard Energia** nativa di HA:

1. Vai in **Impostazioni → Dashboard Energia**
2. In **Consumo di rete** aggiungi `sensor.consumo_totale_kwh`
3. Per ogni elettrodomestico aggiungi il relativo `sensor.<nome>_energia`

---

### Funzionamento tecnico

L'integrazione si connette al cloud Vimar tramite **WebSocket** (`wss://prod.vimar.cloud/wssmqtt/deviceproxy`) usando il protocollo proprietario Vimar con autenticazione **OAuth2 PKCE** (tramite Keycloak su `prod.vimar.cloud`).

Il calcolo dei **kWh** avviene tramite integrazione trapezoidale della potenza W nel tempo, con persistenza del valore accumulato attraverso i riavvii di HA grazie a `RestoreEntity`.

La connessione è **cloud_push**: gli aggiornamenti di stato arrivano in tempo reale tramite messaggi `changestatus` dal gateway, senza polling.

---

### Limitazioni note

- Le **automazioni** (Routine) dell'app View non sono ancora supportate
- I **dati storici** (kWh giornalieri/mensili) richiedono un piano MyVimar a pagamento e non sono disponibili con il piano gratuito
- Il **DUID** deve essere inserito manualmente (auto-discovery in sviluppo)
- Questa integrazione è stata sviluppata con il supporto di **[Claude](https://claude.ai)**, l'assistente AI di Anthropic

---

### Contribuire

Pull request benvenute! Per bug o richieste di funzioni usa le [Issues](https://github.com/ivhazu/ha-vimar-view/issues).

---

## English

### Description

Unofficial **Home Assistant** integration to control and monitor **Vimar View Wireless** smart home devices via cloud.

Uses Vimar's proprietary WebSocket protocol (`prod.vimar.cloud`) with OAuth2 PKCE authentication — the same protocol used by the official Vimar View app.

> ⚠️ **Note**: this is an **unofficial** integration, not affiliated with Vimar S.p.A. Developed through reverse engineering of the View app protocol.

---

### Supported and tested devices

| Device | Vimar Code | HA Type | Features |
|---|---|---|---|
| IoT Gateway | **14597** | — | Root device, firmware, MAC |
| IoT Gateway | **30807** | — | Root device, firmware, MAC |
| Connected switch | **14592** | `light` | On/Off |
| Relay module | **03981** | `light` | On/Off |
| Connected dimmer | **14595** | `light` | On/Off, Brightness |
| Load actuator | **14593** | `sensor` + `select` + `button` | Power W, kWh, State, Mode, Restore |
| Energy Meter | **02963** | `sensor` + `number` | Total power W/kWh, Alert/disconnect thresholds |
| Connected shutter | **30804** | `cover` | Open, Close, Stop, Position % |

---

### Created entities

#### For each light / dimmer
| Entity | Type | Description |
|---|---|---|
| `light.<name>` | Light | On/off and brightness control |

#### For each load actuator
| Entity | Type | Description |
|---|---|---|
| `sensor.<name>_power` | Sensor (W) | Instantaneous power |
| `sensor.<name>_energy` | Sensor (kWh) | Accumulated energy (persists across restarts) |
| `sensor.<name>_state` | Sensor | Text state (Auto on / Forced on / etc.) |
| `select.<name>_mode` | Select | Mode control: Auto / Forced on / Forced off |
| `button.<name>_restore` | Button | Restore load to Auto mode |

#### For each shutter
| Entity | Type | Description |
|---|---|---|
| `cover.<name>` | Cover | Open, Close, Stop, Position % (0=closed, 100=open) |

#### For each Scene Activator
| Entity | Type | Description |
|---|---|---|
| `button.<name>` | Button | Triggers the associated Vimar scene |

> ⚠️ **Note**: scenes are still **being tested** — if the button seems to have no effect, open an [Issue](https://github.com/ivhazu/ha-vimar-view/issues) with details (see [CONTRIBUTING](CONTRIBUTING.md)).

#### For the Energy Manager
| Entity | Type | Description |
|---|---|---|
| `sensor.total_consumption` | Sensor (W) | Total instantaneous power |
| `sensor.total_consumption_kwh` | Sensor (kWh) | Total accumulated energy |
| `sensor.alert_threshold` | Sensor (W) | Current alert threshold |
| `sensor.disconnect_threshold` | Sensor (W) | Current disconnect threshold |
| `number.set_alert_threshold` | Number | Edit alert threshold |
| `number.set_disconnect_threshold` | Number | Edit disconnect threshold |
| `button.restore_all_loads` | Button | Restore all loads to Auto |

---

### Requirements

- Home Assistant **2024.1.0** or higher
- Active **MyVimar** account
- **Vimar View Wireless** smart home devices connected and reachable
- **Free** MyVimar plan (sufficient for all implemented features)

---

### Installation

#### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → `⋮` menu → **Custom repositories**
3. Add: `https://github.com/ivhazu/ha-vimar-view`
4. Search "Vimar View Cloud" and install
5. Restart Home Assistant

#### Manual installation

1. Download the latest release from [Releases](https://github.com/ivhazu/ha-vimar-view/releases)
2. Copy the `vimar_cloud` folder to `/config/custom_components/`
3. Restart Home Assistant

---

### Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search **"Vimar View Cloud"**
3. Enter:
   - **MyVimar Email** — same as used in the View app
   - **MyVimar Password**
   - **Gateway DUID** — see dedicated section below

---

### How to find the gateway DUID

The DUID is the unique identifier of your Vimar gateway. You can find it in two ways:

#### Method 1 — Vimar View App
1. Open the **Vimar View** app on your phone
2. Go to **Settings** (⚙️ icon bottom right)
3. Go to **System info**
4. The DUID is shown as **BLEG** in format `000000AAA00000`

#### Method 2 — Via mitmproxy (advanced)
If you can't find it in the app, you can capture it by intercepting the app's traffic with mitmproxy. The DUID appears in the WebSocket connection URL:
```
wss://prod.vimar.cloud/wssmqtt/deviceproxy?duid=000000AAA00000&access_token=...
```

---

### HA Energy Dashboard

The integration's kWh sensors are compatible with HA's native **Energy Dashboard**:

1. Go to **Settings → Energy Dashboard**
2. Under **Grid consumption** add `sensor.total_consumption_kwh`
3. For each appliance add the relevant `sensor.<name>_energy`

---

### Technical details

The integration connects to the Vimar cloud via **WebSocket** (`wss://prod.vimar.cloud/wssmqtt/deviceproxy`) using Vimar's proprietary protocol with **OAuth2 PKCE** authentication (via Keycloak on `prod.vimar.cloud`).

**kWh** calculation uses trapezoidal integration of power W over time, with accumulated value persisted across HA restarts via `RestoreEntity`.

The connection is **cloud_push**: state updates arrive in real-time via `changestatus` messages from the gateway, no polling.

---

### Known limitations

- App **Routines** (automations) are not yet supported
- **Historical data** (daily/monthly kWh) requires a paid MyVimar plan
- **DUID** must be entered manually (auto-discovery in development)
- This integration was developed with the support of **[Claude](https://claude.ai)**, Anthropic's AI assistant

---

### Contributing

Pull requests are welcome! For bugs or feature requests, use [Issues](https://github.com/ivhazu/ha-vimar-view/issues).

---

### License

MIT License — see [LICENSE](LICENSE) for details.

*This integration is not affiliated with or endorsed by Vimar S.p.A.*
