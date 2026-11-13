<p align="center">
  <img src="custom_components/vimar_cloud/brand/logo.png" alt="Vimar View Cloud" width="320">
</p>

<h1 align="center">Vimar View Cloud for Home Assistant</h1>

<p align="center">
  Control and monitor your <b>Vimar View Wireless</b> smart home from Home Assistant:<br>
  lights, shutters, thermostats, load management, energy, routines and gateway events.
</p>

<p align="center">
  <a href="https://github.com/ivhazu/ha-vimar-view/releases"><img src="https://img.shields.io/github/v/release/ivhazu/ha-vimar-view?style=for-the-badge&label=release" alt="Release"></a>
  <a href="#installation"><img src="https://img.shields.io/badge/Marketplace%20%7C%20HACS-Custom-41BDF5?style=for-the-badge" alt="Marketplace / HACS custom repository"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2024.1%2B-03A9F4?style=for-the-badge&logo=home-assistant&logoColor=white" alt="Home Assistant 2024.1+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/ivhazu/ha-vimar-view?style=for-the-badge" alt="License"></a>
  <a href="https://github.com/ivhazu/ha-vimar-view/issues"><img src="https://img.shields.io/github/issues/ivhazu/ha-vimar-view?style=for-the-badge" alt="Issues"></a>
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=ivhazu&repository=ha-vimar-view&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Open your Home Assistant instance and open this repository in the Marketplace"></a>
  &nbsp;
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=vimar_cloud"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up Vimar View Cloud"></a>
</p>

<p align="center">
  🇬🇧 English · <a href="README.it.md">🇮🇹 Italiano</a>
</p>

> [!IMPORTANT]
> This is an **unofficial** integration, not affiliated with or endorsed by Vimar S.p.A. It talks to the same cloud used by the official **Vimar VIEW** app, whose protocol was studied for interoperability purposes.

---

## Contents

- [Highlights](#highlights)
- [Supported devices](#supported-devices)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [What you get in Home Assistant](#what-you-get-in-home-assistant)
- [Routines](#routines)
- [Gateway events](#gateway-events)
- [Energy](#energy)
- [Services](#services)
- [Events reference](#events-reference)
- [Automation examples](#automation-examples)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [How it works](#how-it-works)
- [Privacy and security](#privacy-and-security)
- [Contributing](#contributing)
- [Credits](#credits)

---

## Highlights

- ⚡ **Real time** — state changes are pushed by the Vimar cloud over a WebSocket (`cloud_push`), no polling.
- 🔌 **Easy setup** — just your MyVimar email and password: gateways and thermostats are read from your account, no DUID to look up.
- 💡 **Lights, dimmers, shutters, thermostats, sockets** — with the same features as the app.
- 🔋 **Load management** — power, energy, mode, thresholds and restore, for each actuator and for the whole home.
- ☀️ **Photovoltaics** — grid exchange and production power and the daily **kWh measured by Vimar**, when your plan provides them.
- 📊 **Energy dashboard ready** — every kWh sensor works with the native Home Assistant Energy dashboard.
- 🤖 **Routines** — run them, enable or suspend them, and get notified when they run.
- 🔔 **Gateway events** — load cut-off and restore, forced loads, internet and cloud connection lost or restored, as Home Assistant events.
- 🛟 **Robust** — automatic reconnection, retry on cloud errors without extra logins, energy history repair service.

## Supported devices

| Device | Vimar code | Home Assistant | Features |
|---|---|---|---|
| IoT gateway | **14597**, **30807** | device | Root device: firmware, MAC, routines, event log |
| Connected switch | **14592** | `light` | On/off |
| Relay module | **03981** | `light` | On/off |
| Connected dimmer | **14595** | `light` | On/off, brightness |
| Load actuator (load management mode) | **14593** | `sensor` · `select` · `button` | Power, energy, state, mode, restore |
| Load actuator (socket / automation mode) | **14593** | `switch` · `sensor` | On/off, power, energy |
| Energy meter | **02963** | `sensor` · `number` · `button` | Total power and energy, thresholds, restore all loads; grid exchange and PV production when installed that way |
| Connected roller shutter | **30804** | `cover` | Open, close, stop, position (also while moving) |
| Wi-Fi thermostat | **02912** | `climate` · `number` | On/off, heating/cooling, target temperature, all operating modes as presets, advanced setpoints |
| Scenes | — | `button` | Activate the scene (still being tested) |

> [!NOTE]
> The **14593** actuator can be set up in the Vimar app either as **load management** (with protection) or as a **socket/automation** (plain on/off): the entities depend on that choice. Switches **14592** and relay modules **03981** look the same to the cloud, so both appear as lights.

Have a device that is not listed? See [Contributing](#contributing): a short traffic capture is usually enough to add it.

## Requirements

- Home Assistant **2024.1** or newer
- A **MyVimar** account (the one you use in the VIEW app) and a **Vimar View Wireless** system online
- The **free** MyVimar plan is enough for everything; some Vimar-measured kWh series (PV production, grid import and export) seem to need a paid plan

## Installation

### Marketplace (Home Assistant 2026.11 and later, recommended)

[![Open your Home Assistant instance and open this repository in the Marketplace.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ivhazu&repository=ha-vimar-view&category=integration)

1. Click the button above, or go to **Settings → Marketplace → Add from link** and enter `ivhazu/ha-vimar-view`. If you have not connected GitHub yet, the Marketplace asks you to do it (device sign-in on GitHub, read-only access to public data).
2. Open **Vimar View Cloud** and download it.
3. Restart Home Assistant.

> [!TIP]
> Want to try beta versions? On the repository page in the Marketplace turn on the **Pre-release** switch.

### HACS (Home Assistant before 2026.11)

1. In HACS open the menu `⋮` → **Custom repositories** and add `https://github.com/ivhazu/ha-vimar-view` with type **Integration**.
2. Search for **Vimar View Cloud** and download it.
3. Restart Home Assistant.

### Manual

1. Download the latest release from [Releases](https://github.com/ivhazu/ha-vimar-view/releases).
2. Copy the `custom_components/vimar_cloud` folder into `/config/custom_components/`.
3. Restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up Vimar View Cloud.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vimar_cloud)

1. Click the button above, or go to **Settings → Devices & services → Add integration** and search for **Vimar View Cloud**.
2. Enter your **MyVimar email and password**.
3. The integration reads the gateways and thermostats linked to your account:
   - if there is only one, it is added right away;
   - if there are more (for example a gateway and some 02912 thermostats), choose which one to add; run the setup again to add the others.

The login is kept with a refresh token, so Home Assistant restarts do not trigger new logins (and new "new access" emails from Vimar).

<details>
<summary><b>Only if asked: how to find the DUID manually</b></summary>

If the device list cannot be read from the cloud, the setup asks for the gateway **DUID**. In the Vimar VIEW app go to **Settings ⚙️ → System info**: the DUID is the **BLEG** code, in the format `000000AAA00000`.
</details>

## What you get in Home Assistant

Entity names follow the names you gave to devices in the Vimar app, and entity IDs start with the device name (for example the energy meter sensors are on the *Gestione Carichi* device, so `sensor.consumo_totale` may be `sensor.gestione_carichi_consumo_totale` on your system). The tables show the part that identifies each entity.

<details open>
<summary><b>💡 Lights and dimmers</b></summary>

| Entity | Description |
|---|---|
| `light.<name>` | On/off; brightness for dimmers |
</details>

<details>
<summary><b>🪟 Roller shutters</b></summary>

| Entity | Description |
|---|---|
| `cover.<name>` | Open, close, stop and position (0 = closed, 100 = open). The position is also updated while the shutter is moving |
</details>

<details>
<summary><b>🌡️ Thermostats (02912)</b></summary>

| Entity | Description |
|---|---|
| `climate.<name>` | Off / Heat / Cool, target temperature, current temperature, presets |
| `number.<name>_riscaldamento_riduzione` | Heating reduction setpoint (5–25 °C) |
| `number.<name>_riscaldamento_assenza` | Heating absence setpoint (5–20 °C) |
| `number.<name>_riscaldamento_protezione_antigelo` | Frost protection threshold (3–10 °C) |
| `number.<name>_raffreddamento_riduzione` | Cooling reduction setpoint (20–35 °C) |
| `number.<name>_raffreddamento_assenza` | Cooling absence setpoint (25–35 °C) |

**Presets** (they map to the thermostat operating modes):

| Preset | Thermostat mode | Behaviour |
|---|---|---|
| Programma | Automatic | Follows the weekly program set in the Vimar app |
| Manuale | Timed manual | Temporary override (duration set on the thermostat) |
| Permanente | Manual | Fixed temperature until you change it |
| Riduzione | Reduction | Holds the reduction setpoint |
| Assenza | Absence (*Modalità Economy* in the app) | Holds the absence setpoint |
| Protezione | Protection | Frost protection only |

> [!TIP]
> **Off** switches the thermostat completely off, frost protection included. To leave home safely use the **Protezione** preset. Changing the target temperature while *Riduzione*, *Assenza* or *Protezione* is active updates that mode's setpoint, so it is kept after the next mode change. Weekly programs are edited in the Vimar app.
</details>

<details>
<summary><b>🔋 Load actuators (14593)</b></summary>

**Load management mode**

| Entity | Description |
|---|---|
| `sensor.<name>_potenza` | Instant power (W) |
| `sensor.<name>_energia` | Energy (kWh), kept across restarts |
| `sensor.<name>_stato` | Load state (Auto on, Auto off, Forced on, Forced off) |
| `select.<name>_modalita` | **Auto** or **Forced on**. *Forced off* is shown only while the gateway has cut the load off after a threshold overrun: it cannot be selected |
| `button.<name>_ripristina` | Restores the load to Auto |

**Socket / automation mode**

| Entity | Description |
|---|---|
| `switch.<name>` | On/off |
| `sensor.<name>_potenza` | Instant power (W) |
| `sensor.<name>_energia` | Energy (kWh), kept across restarts |
</details>

<details>
<summary><b>🏠 Load management / energy meter (02963)</b></summary>

| Entity | Description |
|---|---|
| `sensor.consumo_totale` | Total instant power (W) |
| `sensor.consumo_totale_kwh` | Total energy (kWh) |
| `sensor.scambio_rete` | **PV systems only**: power exchanged with the grid (W, positive = import, negative = export) |
| `sensor.produzione_fotovoltaica` | **PV systems only**: production power (W) |
| `sensor.consumo_oggi`, `sensor.prelievo_rete_oggi` and others | Today's, this week's, month's and year's kWh **measured by Vimar**, when available, see [Energy](#energy) |
| `sensor.soglia_alert`, `sensor.soglia_distacco` | Current alert and cut-off thresholds (W) |
| `number.imposta_soglia_alert`, `number.imposta_soglia_distacco` | Change the thresholds |
| `button.ripristina_tutti_i_carichi` | Restores all loads to Auto |

The PV and telemetry sensors are created only when your system actually provides those values.
</details>

<details>
<summary><b>🎬 Scenes</b></summary>

| Entity | Description |
|---|---|
| `button.<scene>` | Activates the Vimar scene |

Scenes are still **being tested**: if a button has no effect, please open an [issue](https://github.com/ivhazu/ha-vimar-view/issues).
</details>

<details>
<summary><b>📡 Gateway (plant device)</b></summary>

| Entity | Description |
|---|---|
| `button.<plant>_<routine>` | Runs the routine now |
| `switch.<plant>_<routine>_abilitata` | Enables or suspends the routine |
| `sensor.<plant>_<routine>_ultima_esecuzione` | Date and time of the last run |
| `sensor.<plant>_ultimo_evento` | Latest entry of the gateway event log |
</details>

## Routines

The routines you created in the Vimar VIEW app appear on the plant device, one set of entities each:

- a **button** to run the routine now;
- a **switch** to enable or suspend it (exactly like the toggle in the app);
- a **last run** sensor, kept across restarts;
- the **`vimar_cloud_routine_executed`** event every time it runs.

> [!WARNING]
> **Runs of scheduled routines are inferred.** The Vimar cloud does not report when a routine starts on its own: it only reports the device changes. The integration knows each routine's schedule (fixed time, or sunrise/sunset with an offset, computed from your Home Assistant location) and its actions, and recognises a run when, around the scheduled time, the routine's devices reach the expected states. A run is **not** detected if the devices were already in that state, and switching the same devices by hand in those minutes is taken for a run. Runs started from the Home Assistant button are always exact (`source: home_assistant`).

Routines, schedules and enabled state are refreshed every **15 minutes**. A **new** routine created in the app appears after reloading the integration. Creating and editing routines stays in the Vimar app.

## Gateway events

The gateway keeps an event log (the **Events** section of the app). The integration reads it every 2 minutes, and right after any load state change, and:

- shows the latest entry in the **`sensor.<plant>_ultimo_evento`** sensor (for example *"Carico Ferro staccato"*), with the details as attributes;
- fires a **`vimar_cloud_gateway_event`** event for every new entry.

| `key` | Meaning |
|---|---|
| `BLEG_LOG_LOAD_CUT_OFF` | A load was cut off by load management |
| `BLEG_LOG_LOAD_RESTORE` | A load was restored |
| `BLEG_LOG_LOAD_ON_FORCED` | A load was forced on |
| `BLEG_LOG_LOAD_FORCED_SETTING_DELETED` | A load forcing was cleared |
| `GW_LOG_INTERNET_CONNECTION_DOWN` / `_UP` | The gateway lost / got back its internet connection |
| `GW_LOG_CLOUD_CONNECTION_DOWN` / `_UP` | The gateway lost / got back the Vimar cloud connection |

No events are fired for entries already in the log at startup. "Connection lost" entries are stored by the gateway and read once it is back online, so they arrive together with the "restored" one.

## Energy

### How kWh are computed

Vimar reports the **instant power** of actuators and meters. The integration turns it into **kWh** locally (trapezoidal integration), keeps the total across restarts and never invents consumption during cloud outages: gaps longer than 5 minutes are not integrated. Corrupted saved values (not finite or above 1,000,000 kWh) are discarded on startup.

### kWh measured by Vimar

Vimar stores hourly energy data (the daily, weekly and monthly charts of the app). The integration reads it every 10 minutes and creates a sensor **only for the series that actually contain data on your system**:

| Sensor | Meaning |
|---|---|
| `sensor.prelievo_rete_oggi` | Energy drawn from the grid today |
| `sensor.immissione_rete_oggi` | Energy fed into the grid today |
| `sensor.produzione_fotovoltaica_oggi` | PV production today |
| `sensor.autoconsumo_oggi` | Self-consumption today |
| `sensor.consumo_oggi` | Home consumption today |

These are the same values shown in the Vimar app; they reset at midnight.

For each series there are also **week**, **month** and **year** totals, again as measured by Vimar (e.g. `sensor.consumo_settimana`, `sensor.consumo_mese`, `sensor.consumo_anno`, `sensor.produzione_fotovoltaica_anno`). Weeks start on Monday; month and year are calendar periods to date. They are created only when Vimar provides the daily history for that series. *Consumo oggi* is available also on the free plan; the PV series (production, grid import and export, self-consumption) need PV metering and, as far as we know, a paid plan.

### Energy dashboard

All kWh sensors work with the native **Energy dashboard** (**Settings → Dashboards → Energy**):

| Dashboard section | Without PV | With PV and paid plan |
|---|---|---|
| Grid consumption | `sensor.consumo_oggi` (Vimar-measured) or `sensor.consumo_totale_kwh` | `sensor.prelievo_rete_oggi` |
| Return to grid | — | `sensor.immissione_rete_oggi` |
| Solar production | — | `sensor.produzione_fotovoltaica_oggi` |
| Individual devices | `sensor.<name>_energia` | `sensor.<name>_energia` |

### Repairing the energy history

If the long-term history of a kWh sensor got corrupted (for example by a bug) while the power history is fine, the [`vimar_cloud.rebuild_energy_history`](#services) service rebuilds it from the power.

## Services

### `vimar_cloud.rebuild_energy_history`

Rebuilds the **long-term statistics** (the hourly data used by the Energy dashboard and the statistics graphs) of an integration kWh sensor from the long-term statistics of the matching power sensor: for each hour, *kWh = mean power of the hour (W) / 1000*. Hours after the rebuilt range are shifted so the graph has no jumps.

| Field | Required | Description |
|---|---|---|
| `entity_id` | yes | The kWh sensor, e.g. `sensor.forno_energia` |
| `start` | yes | First time to rebuild (rounded down to the hour) |
| `end` | no | Rebuild up to this time (excluded). Default: the last full hour |

```yaml
action: vimar_cloud.rebuild_energy_history
data:
  entity_id: sensor.forno_energia
  start: "2026-10-01 00:00:00"
response_variable: result
```

The response tells how many hours and kWh were rebuilt and how many hours had no power data (counted as 0).

> [!CAUTION]
> The service **overwrites** the energy statistics in the chosen range. Make a backup first. Power statistics are kept by Home Assistant as hourly means, so the result is a very good approximation, not a bit-exact copy of the original values. The sensor's current total is not changed.

## Events reference

| Event | Data |
|---|---|
| `vimar_cloud_routine_executed` | `name`, `ruid`, `source` (`schedule` = inferred, `home_assistant` = started from HA), `time`, `scheduled` (scheduled time, inferred runs only) |
| `vimar_cloud_gateway_event` | `key`, `message`, `level`, `category`, `time`, `params`; for loads also `load` (name) and `load_id` |

You can watch them live in **Developer tools → Events**.

## Automation examples

**Notify when the gateway cuts off a load**

```yaml
triggers:
  - trigger: event
    event_type: vimar_cloud_gateway_event
    event_data:
      key: BLEG_LOG_LOAD_CUT_OFF
actions:
  - action: notify.mobile_app_phone
    data:
      title: Load management
      message: "{{ trigger.event.data.message }}"
```

**Notify when a Vimar routine runs**

```yaml
triggers:
  - trigger: event
    event_type: vimar_cloud_routine_executed
    event_data:
      name: Accensioni Luci Tramonto
actions:
  - action: notify.mobile_app_phone
    data:
      message: "Vimar ran the routine {{ trigger.event.data.name }}"
```

**Put the thermostat in frost protection when everybody leaves**

```yaml
triggers:
  - trigger: state
    entity_id: zone.home
    to: "0"
actions:
  - action: climate.set_preset_mode
    target:
      entity_id: climate.zona_giorno
    data:
      preset_mode: Protezione
```

## Troubleshooting

<details>
<summary><b>Enable debug logging</b></summary>

**Settings → Devices & services → Vimar View Cloud → ⋮ → Enable debug logging**, reproduce the problem, then disable it to download the log. Debug logs show every value received from the gateway (`Vimar: status idsf=…`), which is what we need to support new devices. Access tokens and DUIDs are masked in connection errors, but please check the log before posting it publicly.
</details>

<details>
<summary><b>"Setup failed, will retry: Vimar cloud did not complete device discovery"</b></summary>

The Vimar cloud or the gateway did not answer within 30 seconds. Home Assistant retries by itself; check that the VIEW app works and that the gateway is online.
</details>

<details>
<summary><b>I keep getting "new access" emails from Vimar</b></summary>

They are sent on a full login. The integration logs in only during setup and when the refresh token is really rejected; temporary cloud errors do not trigger a new login.
</details>

<details>
<summary><b>An entity shows "unknown" or a device is missing</b></summary>

Some values arrive only after the first change. If a device type is not supported yet, open an [issue](https://github.com/ivhazu/ha-vimar-view/issues) with a debug log.
</details>

## FAQ

**Does it work without internet, locally?**
No. Vimar View Wireless gateways expose locally only HomeKit, with lights only; everything else (energy, load management, routines…) is available only through the Vimar cloud.

**Do I need a paid MyVimar plan?**
No. The free plan covers everything; only some Vimar-measured kWh series for PV systems seem to need a paid plan.

**Can I create or edit routines from Home Assistant?**
No: you can run, enable and suspend them. Creation and editing stay in the Vimar app.

**Can I use it together with the HomeKit integration?**
You can, but devices will appear twice. This integration covers everything HomeKit offers and more.

## How it works

```
Home Assistant ──OAuth2 (PKCE)──▶ Vimar Keycloak (prod.vimar.cloud)
      │
      ├── WebSocket wss://prod.vimar.cloud/wssmqtt/deviceproxy ◀──▶ Gateway
      │      attach · sfdiscovery · register · getstatus · doaction · changestatus · getlog
      │
      └── REST https://prod.vimar.cloud  (gateway list, routines)
```

- **Authentication**: OAuth2 with PKCE, the same flow as the app. Only the refresh token is stored; access tokens last 5 minutes and are renewed automatically.
- **Real time**: the gateway pushes `changestatus` messages; a keepalive runs every 25 seconds and a watchdog reconnects broken sessions with back-off.
- **Commands** are sent as `doaction`; routines and the gateway list use the Vimar REST API.

## Privacy and security

- Credentials and the refresh token are stored only in your Home Assistant configuration entry.
- The integration talks only to `prod.vimar.cloud`, like the official app.
- Access tokens and DUIDs are masked in connection error logs.

## Contributing

Contributions are very welcome: bug reports, new device support, translations and pull requests.

- **New devices**: [CONTRIBUTING.md](CONTRIBUTING.md) explains, step by step, how to capture the app traffic: with Frida on an Android emulator (recommended, sees everything) or with mitmproxy, plus a script to mask your personal data before sharing.
- **Bugs**: open an [issue](https://github.com/ivhazu/ha-vimar-view/issues) with the integration version and a debug log.
- **Code**: read the pull request guidelines in [CONTRIBUTING.md](CONTRIBUTING.md#pull-requests); unit tests live in `tests/` and run with `pytest`.

## Credits

Thanks to everyone who helped with captures, tests and code:
[@astorelli](https://github.com/astorelli) (thermostats),
[@redfelix](https://github.com/redfelix) (14593 in automation mode),
[@mirks80](https://github.com/mirks80) (WebSocket reconnection),
[@vincferr](https://github.com/vincferr) (energy bug report),
[@andreausu](https://github.com/andreausu) (thermostat presets),
[@afazio82-sudo](https://github.com/afazio82-sudo) (photovoltaics and telemetry).

Developed with the help of [Claude](https://claude.ai) (Anthropic).

---

<sub>Vimar, View and View Wireless are trademarks of Vimar S.p.A. This project is not affiliated with Vimar S.p.A. Released under the [MIT license](LICENSE).</sub>
