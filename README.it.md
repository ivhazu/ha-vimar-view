<p align="center">
  <img src="custom_components/vimar_cloud/brand/logo.png" alt="Vimar View Cloud" width="320">
</p>

<h1 align="center">Vimar View Cloud per Home Assistant</h1>

<p align="center">
  Controlla e monitora il tuo impianto <b>Vimar View Wireless</b> da Home Assistant:<br>
  luci, tapparelle, termostati, gestione carichi, energia, routine ed eventi del gateway.
</p>

<p align="center">
  <a href="https://github.com/ivhazu/ha-vimar-view/releases"><img src="https://img.shields.io/github/v/release/ivhazu/ha-vimar-view?style=for-the-badge&label=release" alt="Release"></a>
  <a href="#installazione"><img src="https://img.shields.io/badge/Marketplace%20%7C%20HACS-Custom-41BDF5?style=for-the-badge" alt="Marketplace / HACS repository personalizzato"></a>
  <a href="https://www.home-assistant.io"><img src="https://img.shields.io/badge/Home%20Assistant-2024.1%2B-03A9F4?style=for-the-badge&logo=home-assistant&logoColor=white" alt="Home Assistant 2024.1+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/ivhazu/ha-vimar-view?style=for-the-badge" alt="Licenza"></a>
  <a href="https://github.com/ivhazu/ha-vimar-view/issues"><img src="https://img.shields.io/github/issues/ivhazu/ha-vimar-view?style=for-the-badge" alt="Issues"></a>
</p>

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=ivhazu&repository=ha-vimar-view&category=integration"><img src="https://my.home-assistant.io/badges/hacs_repository.svg" alt="Apri il repository nel Marketplace del tuo Home Assistant"></a>
  &nbsp;
  <a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=vimar_cloud"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Configura Vimar View Cloud sul tuo Home Assistant"></a>
</p>

<p align="center">
  <a href="README.md">🇬🇧 English</a> · 🇮🇹 Italiano
</p>

> [!IMPORTANT]
> Questa è un'integrazione **non ufficiale**, non affiliata né approvata da Vimar S.p.A. Comunica con lo stesso cloud usato dall'app ufficiale **Vimar VIEW**, il cui protocollo è stato studiato a scopo di interoperabilità.

---

## Indice

- [In breve](#in-breve)
- [Dispositivi supportati](#dispositivi-supportati)
- [Requisiti](#requisiti)
- [Installazione](#installazione)
- [Configurazione](#configurazione)
- [Cosa trovi in Home Assistant](#cosa-trovi-in-home-assistant)
- [Routine](#routine)
- [Eventi del gateway](#eventi-del-gateway)
- [Energia](#energia)
- [Servizi](#servizi)
- [Riferimento eventi](#riferimento-eventi)
- [Esempi di automazioni](#esempi-di-automazioni)
- [Risoluzione problemi](#risoluzione-problemi)
- [Domande frequenti](#domande-frequenti)
- [Come funziona](#come-funziona)
- [Privacy e sicurezza](#privacy-e-sicurezza)
- [Contribuire](#contribuire)
- [Ringraziamenti](#ringraziamenti)

---

## In breve

- ⚡ **In tempo reale** — i cambi di stato arrivano dal cloud Vimar via WebSocket (`cloud_push`), senza polling.
- 🔌 **Configurazione semplice** — bastano email e password MyVimar: gateway e termostati vengono letti dal tuo account, senza cercare il DUID.
- 💡 **Luci, dimmer, tapparelle, termostati, prese** — con le stesse funzioni dell'app.
- 🔋 **Gestione carichi** — potenza, energia, modalità, soglie e ripristino, per ogni attuatore e per tutta la casa.
- ☀️ **Fotovoltaico** — potenza scambiata con la rete e prodotta e i **kWh giornalieri misurati da Vimar**, quando il tuo piano li fornisce.
- 📊 **Pronta per la dashboard Energia** — tutti i sensori kWh funzionano con la dashboard Energia di Home Assistant.
- 🤖 **Routine** — eseguile, abilitale o sospendile, e ricevi una notifica quando partono.
- 🔔 **Eventi del gateway** — distacco e ripristino dei carichi, forzature, connessione a internet o al cloud persa o ripristinata, come eventi di Home Assistant.
- 🛟 **Affidabile** — riconnessione automatica, nuovi tentativi sugli errori del cloud senza login aggiuntivi, servizio per riparare lo storico dell'energia.

## Dispositivi supportati

| Dispositivo | Codice Vimar | Home Assistant | Funzioni |
|---|---|---|---|
| Gateway IoT | **14597**, **30807** | dispositivo | Dispositivo radice: firmware, MAC, routine, registro eventi |
| Deviatore connesso | **14592** | `light` | On/off |
| Modulo relè | **03981** | `light` | On/off |
| Dimmer connesso | **14595** | `light` | On/off, luminosità |
| Attuatore di carico (modalità gestione carico) | **14593** | `sensor` · `select` · `button` | Potenza, energia, stato, modalità, ripristino |
| Attuatore di carico (modalità presa / automazione) | **14593** | `switch` · `sensor` | On/off, potenza, energia |
| Energy meter | **02963** | `sensor` · `number` · `button` | Potenza ed energia totali, soglie, ripristino di tutti i carichi; scambio con la rete e produzione fotovoltaica se installato così |
| Tapparella connessa | **30804** | `cover` | Apri, chiudi, stop, posizione (anche durante il movimento) |
| Termostato Wi-Fi | **02912** | `climate` · `number` | On/off, riscaldamento/raffreddamento, temperatura, tutti i modi come preset, setpoint avanzati |
| Scenari | — | `button` | Attivazione dello scenario (ancora in fase di test) |

> [!NOTE]
> L'attuatore **14593** si può configurare nell'app Vimar come **gestione carico** (con protezione) oppure come **presa/automazione** (semplice on/off): le entità dipendono da questa scelta. Deviatori **14592** e moduli relè **03981** sono indistinguibili per il cloud, quindi compaiono entrambi come luci.

Hai un dispositivo che non è in elenco? Vedi [Contribuire](#contribuire): di solito basta una breve cattura del traffico per aggiungerlo.

## Requisiti

- Home Assistant **2024.1** o successivo
- Un account **MyVimar** (quello dell'app VIEW) e un impianto **Vimar View Wireless** online
- Il piano MyVimar **gratuito** basta per tutto, comprese le serie di kWh misurati da Vimar

## Installazione

### Marketplace (Home Assistant 2026.11 e successivi, consigliato)

[![Apri il repository nel Marketplace del tuo Home Assistant.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ivhazu&repository=ha-vimar-view&category=integration)

1. Clicca il pulsante qui sopra, oppure vai in **Impostazioni → Marketplace → Aggiungi da link** e inserisci `ivhazu/ha-vimar-view`. Se non hai ancora collegato GitHub, il Marketplace te lo chiede (accesso da dispositivo su GitHub, sola lettura dei dati pubblici).
2. Apri **Vimar View Cloud** e scaricala.
3. Riavvia Home Assistant.

> [!TIP]
> Vuoi provare le versioni beta? Nella pagina del repository nel Marketplace attiva l'interruttore **Pre-release**.

### HACS (Home Assistant precedenti alla 2026.11)

1. In HACS apri il menu `⋮` → **Repository personalizzati** e aggiungi `https://github.com/ivhazu/ha-vimar-view` con tipo **Integrazione**.
2. Cerca **Vimar View Cloud** e scaricala.
3. Riavvia Home Assistant.

### Manuale

1. Scarica l'ultima versione da [Releases](https://github.com/ivhazu/ha-vimar-view/releases).
2. Copia la cartella `custom_components/vimar_cloud` in `/config/custom_components/`.
3. Riavvia Home Assistant.

## Configurazione

[![Configura Vimar View Cloud sul tuo Home Assistant.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=vimar_cloud)

1. Clicca il pulsante qui sopra, oppure vai in **Impostazioni → Dispositivi e servizi → Aggiungi integrazione** e cerca **Vimar View Cloud**.
2. Inserisci **email e password MyVimar**.
3. L'integrazione legge i gateway e i termostati collegati al tuo account:
   - se ce n'è uno solo viene aggiunto subito;
   - se ce ne sono più di uno (per esempio un gateway e alcuni termostati 02912) scegli quale aggiungere; ripeti la configurazione per aggiungere gli altri.

L'accesso viene mantenuto con un refresh token: i riavvii di Home Assistant non fanno nuovi login (e quindi niente email di "nuovo accesso" da Vimar).

<details>
<summary><b>Solo se richiesto: come trovare il DUID a mano</b></summary>

Se l'elenco dei dispositivi non si può leggere dal cloud, la configurazione chiede il **DUID** del gateway. Nell'app Vimar VIEW vai in **Impostazioni ⚙️ → Info di sistema**: il DUID è il codice **BLEG**, nel formato `000000AAA00000`.
</details>

## Cosa trovi in Home Assistant

I nomi delle entità seguono i nomi che hai dato ai dispositivi nell'app Vimar, e gli ID delle entità iniziano con il nome del dispositivo (per esempio i sensori dell'energy meter stanno sul dispositivo *Gestione Carichi*, quindi `sensor.consumo_totale` sul tuo impianto può essere `sensor.gestione_carichi_consumo_totale`). Le tabelle mostrano la parte che identifica ogni entità.

<details open>
<summary><b>💡 Luci e dimmer</b></summary>

| Entità | Descrizione |
|---|---|
| `light.<nome>` | On/off; luminosità per i dimmer |
</details>

<details>
<summary><b>🪟 Tapparelle</b></summary>

| Entità | Descrizione |
|---|---|
| `cover.<nome>` | Apri, chiudi, stop e posizione (0 = chiusa, 100 = aperta). La posizione si aggiorna anche durante il movimento |
</details>

<details>
<summary><b>🌡️ Termostati (02912)</b></summary>

| Entità | Descrizione |
|---|---|
| `climate.<nome>` | Spento / Riscaldamento / Raffreddamento, temperatura target e attuale, preset |
| `number.<nome>_riscaldamento_riduzione` | Setpoint di riduzione in riscaldamento (5–25 °C) |
| `number.<nome>_riscaldamento_assenza` | Setpoint di assenza in riscaldamento (5–20 °C) |
| `number.<nome>_riscaldamento_protezione_antigelo` | Soglia di protezione antigelo (3–10 °C) |
| `number.<nome>_raffreddamento_riduzione` | Setpoint di riduzione in raffreddamento (20–35 °C) |
| `number.<nome>_raffreddamento_assenza` | Setpoint di assenza in raffreddamento (25–35 °C) |

**Preset** (corrispondono ai modi di funzionamento del termostato):

| Preset | Modo del termostato | Comportamento |
|---|---|---|
| Programma | Automatico | Segue il programma settimanale impostato nell'app Vimar |
| Manuale | Manuale a tempo | Override temporaneo (durata impostata sul termostato) |
| Permanente | Manuale | Temperatura fissa finché non la cambi |
| Riduzione | Riduzione | Mantiene il setpoint di riduzione |
| Assenza | Assenza (*Modalità Economy* nell'app) | Mantiene il setpoint di assenza |
| Protezione | Protezione | Solo protezione antigelo |

> [!TIP]
> **Spento** spegne del tutto il termostato, antigelo compreso. Per uscire di casa in sicurezza usa il preset **Protezione**. Se cambi la temperatura target mentre è attivo *Riduzione*, *Assenza* o *Protezione*, viene aggiornato il setpoint di quel modo, che resta anche dopo il prossimo cambio di modo. I programmi settimanali si modificano nell'app Vimar.
</details>

<details>
<summary><b>🔋 Attuatori di carico (14593)</b></summary>

**Modalità gestione carico**

| Entità | Descrizione |
|---|---|
| `sensor.<nome>_potenza` | Potenza istantanea (W) |
| `sensor.<nome>_energia` | Energia (kWh), conservata ai riavvii |
| `sensor.<nome>_stato` | Stato del carico (Auto on, Auto off, Forced on, Forced off) |
| `select.<nome>_modalita` | **Auto** o **Forced on**. *Forced off* compare solo mentre il gateway ha staccato il carico per superamento soglia: non si può selezionare |
| `button.<nome>_ripristina` | Riporta il carico in Auto |

**Modalità presa / automazione**

| Entità | Descrizione |
|---|---|
| `switch.<nome>` | On/off |
| `sensor.<nome>_potenza` | Potenza istantanea (W) |
| `sensor.<nome>_energia` | Energia (kWh), conservata ai riavvii |
</details>

<details>
<summary><b>🏠 Gestione carichi / energy meter (02963)</b></summary>

| Entità | Descrizione |
|---|---|
| `sensor.consumo_totale` | Potenza totale istantanea (W) |
| `sensor.consumo_totale_kwh` | Energia totale (kWh) |
| `sensor.scambio_rete` | **Solo con fotovoltaico**: potenza scambiata con la rete (W, positiva = prelievo, negativa = immissione) |
| `sensor.produzione_fotovoltaica` | **Solo con fotovoltaico**: potenza prodotta (W) |
| `sensor.consumo_oggi`, `sensor.prelievo_rete_oggi` e altri | kWh di oggi, della settimana, del mese e dell'anno **misurati da Vimar**, quando disponibili, vedi [Energia](#energia) |
| `sensor.soglia_alert`, `sensor.soglia_distacco` | Soglie attuali di allerta e di distacco (W) |
| `number.imposta_soglia_alert`, `number.imposta_soglia_distacco` | Modifica delle soglie |
| `button.ripristina_tutti_i_carichi` | Riporta tutti i carichi in Auto |

I sensori del fotovoltaico e della telemetria vengono creati solo se il tuo impianto fornisce davvero quei valori.
</details>

<details>
<summary><b>🎬 Scenari</b></summary>

| Entità | Descrizione |
|---|---|
| `button.<scenario>` | Attiva lo scenario Vimar |

Gli scenari sono ancora **in fase di test**: se un pulsante non ha effetto, apri una [issue](https://github.com/ivhazu/ha-vimar-view/issues).
</details>

<details>
<summary><b>📡 Gateway (dispositivo dell'impianto)</b></summary>

| Entità | Descrizione |
|---|---|
| `button.<impianto>_<routine>` | Esegue subito la routine |
| `switch.<impianto>_<routine>_abilitata` | Abilita o sospende la routine |
| `sensor.<impianto>_<routine>_ultima_esecuzione` | Data e ora dell'ultima esecuzione |
| `sensor.<impianto>_ultimo_evento` | Ultima voce del registro eventi del gateway |
</details>

## Routine

Le routine create nell'app Vimar VIEW compaiono sul dispositivo dell'impianto, ognuna con le sue entità:

- un **pulsante** per eseguirla subito;
- un **interruttore** per abilitarla o sospenderla (esattamente come nell'app);
- un sensore **ultima esecuzione**, conservato ai riavvii;
- l'evento **`vimar_cloud_routine_executed`** a ogni esecuzione.

> [!WARNING]
> **L'esecuzione delle routine programmate è dedotta.** Il cloud Vimar non segnala quando una routine parte da sola: segnala solo i cambi di stato dei dispositivi. L'integrazione conosce l'orario di ogni routine (ora fissa, oppure alba/tramonto con scarto, calcolati con la posizione del tuo Home Assistant) e le sue azioni, e riconosce un'esecuzione quando, intorno all'orario previsto, i dispositivi della routine raggiungono gli stati previsti. L'esecuzione **non** viene rilevata se i dispositivi erano già in quello stato, e un comando manuale sugli stessi dispositivi proprio in quei minuti viene scambiato per un'esecuzione. Le esecuzioni avviate dal pulsante in Home Assistant sono invece sempre esatte (`source: home_assistant`).

Routine, orari e abilitazione vengono riletti ogni **15 minuti**. Una routine **nuova** creata nell'app compare dopo aver ricaricato l'integrazione. La creazione e la modifica delle routine restano nell'app Vimar.

## Eventi del gateway

Il gateway tiene un registro degli eventi (la sezione **Eventi** dell'app). L'integrazione lo legge ogni 2 minuti, e subito dopo ogni cambio di stato di un carico, e:

- mostra l'ultima voce nel sensore **`sensor.<impianto>_ultimo_evento`** (per esempio *"Carico Ferro staccato"*), con i dettagli negli attributi;
- genera l'evento **`vimar_cloud_gateway_event`** per ogni voce nuova.

| `key` | Significato |
|---|---|
| `BLEG_LOG_LOAD_CUT_OFF` | Un carico è stato staccato dalla gestione carichi |
| `BLEG_LOG_LOAD_RESTORE` | Un carico è stato ripristinato |
| `BLEG_LOG_LOAD_ON_FORCED` | Un carico è stato forzato acceso |
| `BLEG_LOG_LOAD_FORCED_SETTING_DELETED` | Una forzatura è stata annullata |
| `GW_LOG_INTERNET_CONNECTION_DOWN` / `_UP` | Il gateway ha perso / recuperato la connessione a internet |
| `GW_LOG_CLOUD_CONNECTION_DOWN` / `_UP` | Il gateway ha perso / recuperato la connessione al cloud Vimar |

Al primo avvio non vengono generati eventi per le voci già presenti. Le voci di "connessione persa" vengono registrate dal gateway e lette quando torna online, quindi arrivano insieme a quella di ripristino.

## Energia

### Come vengono calcolati i kWh

Vimar fornisce la **potenza istantanea** di attuatori e misuratori. L'integrazione la trasforma in **kWh** localmente (integrazione trapezoidale), conserva il totale ai riavvii e non inventa consumi durante le interruzioni del cloud: i buchi più lunghi di 5 minuti non vengono integrati. I valori salvati corrotti (non finiti o oltre 1.000.000 kWh) vengono scartati all'avvio.

### kWh misurati da Vimar

Vimar registra i dati energetici ora per ora (i grafici giornalieri, settimanali e mensili dell'app). L'integrazione li legge ogni 10 minuti e crea un sensore **solo per le serie che sul tuo impianto contengono davvero dati**:

| Sensore | Significato |
|---|---|
| `sensor.prelievo_rete_oggi` | Energia prelevata dalla rete oggi |
| `sensor.immissione_rete_oggi` | Energia immessa in rete oggi |
| `sensor.produzione_fotovoltaica_oggi` | Produzione fotovoltaica di oggi |
| `sensor.autoconsumo_oggi` | Autoconsumo di oggi |
| `sensor.consumo_oggi` | Consumo della casa oggi |

Sono gli stessi valori dell'app Vimar; si azzerano a mezzanotte. Funzionano anche con il piano MyVimar gratuito; le serie del fotovoltaico (produzione, prelievo, immissione, autoconsumo) compaiono solo se l'impianto misura il fotovoltaico.

Per ogni serie ci sono anche i totali di **settimana**, **mese** e **anno**, sempre misurati da Vimar (es. `sensor.consumo_settimana`, `sensor.consumo_mese`, `sensor.consumo_anno`, `sensor.produzione_fotovoltaica_anno`). La settimana parte dal lunedì; mese e anno sono quelli di calendario fino a oggi. Vengono creati solo se Vimar fornisce lo storico giornaliero di quella serie.

### Dashboard Energia

Tutti i sensori kWh funzionano con la **dashboard Energia** (**Impostazioni → Plance → Energia**):

| Sezione della dashboard | Senza fotovoltaico | Con fotovoltaico |
|---|---|---|
| Consumo di rete | `sensor.consumo_oggi` (misurato da Vimar) oppure `sensor.consumo_totale_kwh` | `sensor.prelievo_rete_oggi` |
| Ritorno alla rete | — | `sensor.immissione_rete_oggi` |
| Produzione solare | — | `sensor.produzione_fotovoltaica_oggi` |
| Singoli dispositivi | `sensor.<nome>_energia` | `sensor.<nome>_energia` |

### Riparare lo storico dell'energia

Se lo storico a lungo termine di un sensore kWh si è rovinato (per esempio per un bug) mentre quello della potenza è corretto, il servizio [`vimar_cloud.rebuild_energy_history`](#servizi) lo ricostruisce partendo dalla potenza.

## Servizi

### `vimar_cloud.rebuild_energy_history`

Ricalcola le **statistiche a lungo termine** (i dati orari usati dalla dashboard Energia e dai grafici statistici) di un sensore kWh dell'integrazione partendo dalle statistiche del sensore di potenza corrispondente: per ogni ora, *kWh = potenza media dell'ora (W) / 1000*. Le ore successive all'intervallo ricalcolato vengono allineate, così il grafico non ha salti.

| Campo | Obbligatorio | Descrizione |
|---|---|---|
| `entity_id` | sì | Il sensore kWh, per esempio `sensor.forno_energia` |
| `start` | sì | Primo orario da ricalcolare (arrotondato all'ora) |
| `end` | no | Fino a quando ricalcolare (escluso). Predefinito: l'ultima ora completa |

```yaml
action: vimar_cloud.rebuild_energy_history
data:
  entity_id: sensor.forno_energia
  start: "2026-10-01 00:00:00"
response_variable: result
```

La risposta indica quante ore e quanti kWh sono stati ricalcolati e quante ore non avevano dati di potenza (contate come 0).

> [!CAUTION]
> Il servizio **sovrascrive** le statistiche dell'energia nell'intervallo scelto: fai prima un backup. Home Assistant conserva le statistiche della potenza come medie orarie, quindi il risultato è un'ottima approssimazione, non una copia esatta dei valori originali. Il totale attuale del sensore non viene modificato.

## Riferimento eventi

| Evento | Dati |
|---|---|
| `vimar_cloud_routine_executed` | `name`, `ruid`, `source` (`schedule` = dedotta, `home_assistant` = avviata da HA), `time`, `scheduled` (orario previsto, solo per quelle dedotte) |
| `vimar_cloud_gateway_event` | `key`, `message`, `level`, `category`, `time`, `params`; per i carichi anche `load` (nome) e `load_id` |

Puoi vederli in diretta in **Strumenti per sviluppatori → Eventi**.

## Esempi di automazioni

**Notifica quando il gateway stacca un carico**

```yaml
triggers:
  - trigger: event
    event_type: vimar_cloud_gateway_event
    event_data:
      key: BLEG_LOG_LOAD_CUT_OFF
actions:
  - action: notify.mobile_app_telefono
    data:
      title: Gestione carichi
      message: "{{ trigger.event.data.message }}"
```

**Notifica quando parte una routine Vimar**

```yaml
triggers:
  - trigger: event
    event_type: vimar_cloud_routine_executed
    event_data:
      name: Accensioni Luci Tramonto
actions:
  - action: notify.mobile_app_telefono
    data:
      message: "Vimar ha eseguito la routine {{ trigger.event.data.name }}"
```

**Termostato in protezione antigelo quando escono tutti**

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

## Risoluzione problemi

<details>
<summary><b>Attivare il log di debug</b></summary>

**Impostazioni → Dispositivi e servizi → Vimar View Cloud → ⋮ → Abilita la registrazione di debug**, riproduci il problema, poi disattivala per scaricare il log. Il log di debug mostra ogni valore ricevuto dal gateway (`Vimar: status idsf=…`), ed è proprio quello che serve per supportare nuovi dispositivi. Token di accesso e DUID sono mascherati negli errori di connessione, ma controlla comunque il log prima di pubblicarlo.
</details>

<details>
<summary><b>"Configurazione non riuscita, riproverà: Vimar cloud did not complete device discovery"</b></summary>

Il cloud Vimar o il gateway non hanno risposto entro 30 secondi. Home Assistant riprova da solo; controlla che l'app VIEW funzioni e che il gateway sia online.
</details>

<details>
<summary><b>Ricevo continuamente email di "nuovo accesso" da Vimar</b></summary>

Vengono inviate a ogni login completo. L'integrazione fa il login solo durante la configurazione e quando il refresh token viene davvero rifiutato; gli errori temporanei del cloud non provocano un nuovo login.
</details>

<details>
<summary><b>Un'entità è "sconosciuta" o manca un dispositivo</b></summary>

Alcuni valori arrivano solo al primo cambio. Se un tipo di dispositivo non è ancora supportato, apri una [issue](https://github.com/ivhazu/ha-vimar-view/issues) con un log di debug.
</details>

## Domande frequenti

**Funziona in locale, senza internet?**
No. I gateway Vimar View Wireless espongono in locale solo HomeKit, e solo per le luci; tutto il resto (energia, gestione carichi, routine…) è disponibile solo tramite il cloud Vimar.

**Serve un piano MyVimar a pagamento?**
No. Il piano gratuito copre tutto, comprese le serie di kWh misurati da Vimar (confermato da un utente con fotovoltaico e piano gratuito).

**Posso creare o modificare le routine da Home Assistant?**
No: puoi eseguirle, abilitarle e sospenderle. Creazione e modifica restano nell'app Vimar.

**Posso usarla insieme all'integrazione HomeKit?**
Sì, ma i dispositivi compariranno due volte. Questa integrazione copre tutto quello che offre HomeKit, e molto di più.

## Come funziona

```
Home Assistant ──OAuth2 (PKCE)──▶ Keycloak Vimar (prod.vimar.cloud)
      │
      ├── WebSocket wss://prod.vimar.cloud/wssmqtt/deviceproxy ◀──▶ Gateway
      │      attach · sfdiscovery · register · getstatus · doaction · changestatus · getlog
      │
      └── REST https://prod.vimar.cloud  (elenco gateway, routine)
```

- **Autenticazione**: OAuth2 con PKCE, lo stesso flusso dell'app. Viene salvato solo il refresh token; i token di accesso durano 5 minuti e vengono rinnovati automaticamente.
- **Tempo reale**: il gateway invia i messaggi `changestatus`; un keepalive parte ogni 25 secondi e un watchdog riconnette le sessioni interrotte, con attese crescenti.
- **Comandi** inviati come `doaction`; routine ed elenco dei gateway usano l'API REST di Vimar.

## Privacy e sicurezza

- Le credenziali e il refresh token restano solo nella configurazione dell'integrazione in Home Assistant.
- L'integrazione comunica solo con `prod.vimar.cloud`, come l'app ufficiale.
- Token di accesso e DUID sono mascherati nei log degli errori di connessione.

## Contribuire

I contributi sono benvenuti: segnalazioni di bug, supporto per nuovi dispositivi, traduzioni e pull request.

- **Nuovi dispositivi**: [CONTRIBUTING.it.md](CONTRIBUTING.it.md) spiega passo per passo come catturare il traffico dell'app: con Frida su un emulatore Android (consigliato, vede tutto) oppure con mitmproxy, più uno script per mascherare i tuoi dati personali prima di condividerli.
- **Bug**: apri una [issue](https://github.com/ivhazu/ha-vimar-view/issues) indicando la versione dell'integrazione e allegando un log di debug.
- **Codice**: leggi le regole per le pull request in [CONTRIBUTING.it.md](CONTRIBUTING.it.md#pull-request); i test sono in `tests/` e si eseguono con `pytest`.

## Ringraziamenti

Grazie a tutti quelli che hanno aiutato con catture, test e codice:
[@astorelli](https://github.com/astorelli) (termostati),
[@redfelix](https://github.com/redfelix) (14593 in modalità automazione),
[@mirks80](https://github.com/mirks80) (riconnessione WebSocket),
[@vincferr](https://github.com/vincferr) (segnalazione del bug sull'energia),
[@andreausu](https://github.com/andreausu) (preset del termostato),
[@afazio82-sudo](https://github.com/afazio82-sudo) (fotovoltaico e telemetria).

Sviluppata con l'aiuto di [Claude](https://claude.ai) (Anthropic).

---

<sub>Vimar, View e View Wireless sono marchi di Vimar S.p.A. Questo progetto non è affiliato a Vimar S.p.A. Distribuito con [licenza MIT](LICENSE).</sub>
