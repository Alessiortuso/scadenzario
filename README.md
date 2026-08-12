# Scadenzario

Gestione scadenze con avvisi automatici e **notifiche desktop**, distribuita come
**applicazione Windows** installata sulle postazioni, senza server da tenere acceso.

- **backend** — FastAPI + SQLAlchemy, scheduler integrato; gira come processo locale dentro l'app
- **frontend** — Angular 22 (standalone + signals), interfaccia in italiano, tema chiaro/scuro automatico
- **desktop** — Electron: finestra, icona nella tray, avvio automatico, notifiche native di Windows, aggiornamenti automatici

## Architettura

```
   PC 1                     PC 2                     PC 3
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Scadenzario  │        │ Scadenzario  │        │ Scadenzario  │
│ (Electron +  │        │ (Electron +  │        │ (Electron +  │
│  backend)    │        │  backend)    │        │  backend)    │
│              │        │              │        │              │
│ locale.db ───┼─ avvisi│ locale.db ───┼─ avvisi│ locale.db ───┼─ avvisi
└──────┬───────┘  mostrati└─────┬──────┘ mostrati└─────┬───────┘ mostrati
       └───────────────────────┬┴───────────────────────┘
                               │
                  PostgreSQL gestito (cloud, piano gratuito)
                  scadenze · categorie · impostazioni
```

Due database con due ruoli distinti:

- **condiviso** (PostgreSQL): le scadenze, uguali per tutti — chi ne aggiunge una la fa vedere agli altri;
- **locale** (SQLite su ogni PC): quali avvisi *questa* postazione ha già mostrato, così ognuno riceve le proprie notifiche senza pestarsi i piedi con gli altri.

**Conseguenza da conoscere**: non essendoci una macchina sempre accesa, se tutti i PC sono spenti nessun avviso parte in quel momento. Gli avvisi arretrati non si perdono: vengono mostrati all'accensione successiva.

## Cosa fa

- Anagrafica scadenze: titolo, data, categoria, priorità, importo, cliente/responsabile, riferimento, note
- **Preavvisi configurabili** (es. 30, 15, 7, 3, 1, 0 giorni prima) a livello globale, per categoria o per singola scadenza
- **Solleciti dopo la scadenza** ogni N giorni, con tetto massimo
- **Avviso di recupero**: una scadenza inserita quando è già scaduta (o già dentro la finestra di preavviso) genera comunque un avviso immediato
- **Ricorrenze**: mensile, trimestrale, semestrale, annuale — chiudendo una scadenza viene creata automaticamente l'occorrenza successiva
- **Canali di notifica** attivabili singolarmente: centro notifiche in-app, Web Push (desktop), email SMTP
- **Importazione CSV/Excel** con riconoscimento automatico delle colonne, anteprima con validazione riga per riga e reimport idempotente (aggiorna, non duplica)
- Dashboard con scadute / oggi / 7 / 30 giorni, ripartizione per categoria e totale importi aperti

## Notifiche desktop: cosa aspettarsi

| Situazione | Notifica |
|---|---|
| Applicazione aperta | Sì: toast di Windows + campanella nell'app |
| Finestra chiusa, applicazione nella tray | **Sì**: toast di Windows |
| Applicazione chiusa del tutto | No in quel momento; gli avvisi arretrati compaiono al riavvio |
| PC spento | Come sopra: si recuperano all'accensione |

Con l'app desktop le notifiche sono quelle native di Windows, quindi **non servono HTTPS, certificati o dominio**. Il canale Web Push resta nel codice e si attiva da solo se si vuole usare lo scadenzario da browser (vedi `VAPID_*`).

Il canale email è disponibile come rete di sicurezza: va acceso su **una sola** postazione (`EMAIL_SENDER_DEVICE=true`), altrimenti ogni PC acceso invia la sua copia.

## Configurazione al primo avvio

**Le credenziali del database non sono dentro l'installer.** Alla prima apertura ogni postazione mostra una schermata dove si incolla la stringa di connessione, che viene verificata e salvata in `%LOCALAPPDATA%\Scadenzario\config.json` **su quel solo computer**.

Perché è fatto così:

- l'installer resta un file neutro, pubblicabile fra le release senza esporre il database;
- cambiare la password di Neon non richiede di ricompilare e ridistribuire l'applicazione;
- lo stesso pacchetto serve per un altro cliente, con un database diverso.

Limite noto e non eliminabile in questa architettura: chi ha accesso a una postazione può leggere quel file di configurazione. Eliminarlo richiederebbe un server intermedio che custodisce le credenziali, cioè la macchina sempre accesa che si è scelto di non avere.

Finché la configurazione manca, il backend parte lo stesso (serve la schermata di setup) ma ogni chiamata ai dati condivisi risponde `503 not_configured`, e l'interfaccia rimanda alla configurazione. Non viene creato nessun database locale di ripiego: sarebbe il modo più rapido per ritrovarsi tre archivi diversi senza accorgersene.

In sviluppo si può saltare la schermata valorizzando `DATABASE_URL` in `backend/.env`: ha precedenza minore del file di configurazione, quindi non interferisce con le postazioni reali.

## Database condiviso (Neon)

Progetto Neon: **Scadenzario**, PostgreSQL 18, regione `eu-central-1` (Francoforte), piano gratuito.

```
DATABASE_URL=postgresql+psycopg://<utente>:<password>@<host>.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

Il prefisso `+psycopg` è obbligatorio: indica a SQLAlchemy quale driver usare.

Due avvertenze operative:

- Il piano gratuito **va in standby dopo qualche minuto di inattività**: la prima richiesta della giornata impiega qualche secondo in più per risvegliare il database. Nessun impatto sul funzionamento.
- La connection string contiene la password del database ed è replicata sul `.env` di ogni postazione: chi ha accesso a quei PC ha accesso ai dati. Per rigenerarla: dashboard Neon → *Reset password*, poi aggiornare i `.env`.

Sul database condiviso vivono solo tre tabelle — `deadlines`, `categories`, `settings`. Le notifiche stanno nel database locale di ciascuna postazione.

## Evoluzione dello schema

Lo schema è gestito con **Alembic** e si aggiorna da sé: a ogni avvio il backend porta il database locale all'ultima revisione, e fa lo stesso con quello condiviso appena la postazione è configurata. Un aggiornamento dell'applicazione porta quindi con sé il proprio adeguamento del database, senza interventi manuali sulle postazioni.

I due database hanno storie separate — tabelle di versione distinte, `alembic_version` e `alembic_version_local` — perché uno è condiviso da tutti e l'altro appartiene alla singola postazione.

Le installazioni nate prima delle migrazioni (la 1.0.0, che creava le tabelle con `create_all`) non vengono ricreate: al primo avvio lo schema esistente viene *marcato* alla revisione iniziale, e da lì in poi segue le migrazioni normalmente.

Per aggiungere una modifica dopo aver cambiato i modelli:

```powershell
cd backend
.\.venv\Scripts\python.exe -m alembic revision -m "aggiunge il campo allegato"
```

Il file generato in `alembic/versions/` ha una funzione per database: riempi `upgrade_shared` per le tabelle condivise, `upgrade_local` per quelle delle notifiche. Sul database locale le modifiche di colonna richiedono la modalità *batch* di SQLite, già attiva in `alembic/env.py`.

Le migrazioni non si applicano da riga di comando (`alembic upgrade` non ha una connessione: le credenziali stanno nel `config.json` della postazione, non nell'ini). Le applica il backend all'avvio; per forzarle a mano basta `python -c "from app.db import init_db; init_db()"`.

## Requisiti

- Python 3.11+ (testato su 3.14)
- Node.js 20+ (testato su 24)

## Avvio — backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 1) genera le chiavi VAPID (una tantum) e copiale nel .env
.\.venv\Scripts\python.exe -m app.tools.vapid_keys

# 2) crea il file di configurazione
Copy-Item .env.example .env   # poi incolla le chiavi VAPID

# 3) (facoltativo) dati di esempio
.\.venv\Scripts\python.exe -m app.tools.seed

# 4) avvia
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010 --reload
```

API su <http://127.0.0.1:8010>, documentazione interattiva su <http://127.0.0.1:8010/docs>.

> Le porte 8000 e 4200 risultavano già occupate da altri servizi su questa macchina, quindi il progetto è configurato su **8010** (backend) e **4300** (frontend). Per cambiarle: `--port` di uvicorn, `proxy.conf.json` e lo script `start` in `frontend/package.json`.

## Test

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

I test coprono la parte del sistema in cui un errore non si vede, perché non solleva eccezioni ma manda un avviso di troppo o — peggio — nessuno: calcolo dei preavvisi, avvisi di recupero, solleciti, idempotenza della generazione, ricorrenze, consegna multicanale e comportamento quando il database condiviso non risponde.

I due database di prova vengono ricreati in memoria **passando dalle migrazioni**, così ogni esecuzione verifica anche che le migrazioni producano lo schema che il codice si aspetta.

## Avvio — applicazione desktop (sviluppo)

```powershell
cd frontend; npm install; npx ng build      # l'app carica il frontend compilato
cd ..\desktop; npm install
$env:SCADENZARIO_DEV = '1'; npm start
```

L'app avvia da sé il backend dal venv, apre la finestra, resta nella tray alla chiusura e mostra i toast di Windows.
Per lavorare sul frontend con ricaricamento a caldo: avvia `npm start` nel frontend e aggiungi `$env:SCADENZARIO_UI = 'http://localhost:4300'`.

## Avvio — frontend (solo sviluppo interfaccia)

```powershell
cd frontend
npm install
npm start          # http://localhost:4300
```

Il dev server inoltra `/api` al backend tramite `proxy.conf.json`.

## Configurazione (`backend/.env`)

| Variabile | Effetto |
|---|---|
| `DATABASE_URL` | Database condiviso: `postgresql+psycopg://utente:pwd@host/db?sslmode=require` |
| `LOCAL_DATABASE_URL` | Database locale della postazione (vuoto = `%LOCALAPPDATA%\Scadenzario\locale.db`) |
| `EMAIL_SENDER_DEVICE` | `true` su **una sola** postazione, per non moltiplicare le email |
| `DEFAULT_ALERT_OFFSETS` | Preavvisi predefiniti in giorni |
| `OVERDUE_REPEAT_DAYS` / `OVERDUE_MAX_REMINDERS` | Solleciti dopo la scadenza |
| `DAILY_SEND_TIME` | Orario di invio degli avvisi del giorno |
| `SCHEDULER_INTERVAL_SECONDS` | Frequenza del ciclo interno (default 300s) |
| `VAPID_*` | Chiavi Web Push — senza queste il canale desktop resta disattivo |
| `SMTP_*` | Invio email — con `SMTP_HOST` vuoto il canale resta disattivo |

Preavvisi, orari, canali e destinatari sono modificabili anche a runtime dalla pagina **Impostazioni**, senza riavviare il backend.

## Come funziona lo scheduler

Ogni `SCHEDULER_INTERVAL_SECONDS` il backend:

1. ricalcola gli avvisi pendenti di tutte le scadenze aperte (`alerts.sync_all`);
2. spedisce quelli la cui ora di invio è arrivata, su tutti i canali attivi (`dispatcher.dispatch_due`).

Ogni avviso ha una `dedupe_key`, quindi non viene mai inviato due volte. Il ciclo è richiamabile anche manualmente con `POST /api/scheduler/run` (o dal pulsante "Esegui ciclo avvisi adesso"): utile se in produzione preferisci un cron esterno o più repliche del backend.

## Struttura

```
backend/
  alembic/          migrazioni dello schema (condiviso e locale)
  tests/            test del motore avvisi, delle ricorrenze e degli endpoint
  app/
    api/            endpoint REST (scadenze, categorie, notifiche, push, import, impostazioni)
    migrations.py   applicazione delle migrazioni all'avvio
    services/
      alerts.py     calcolo dei preavvisi e generazione notifiche
      dispatcher.py invio multicanale
      scheduler.py  loop asincrono
      notifiers/    canali: in-app, web push, email  <- estendibile
      importers/    adapter CSV/Excel + pipeline di mappatura  <- estendibile
    tools/          generazione chiavi VAPID, dati di esempio
frontend/
  public/sw.js      service worker delle notifiche desktop
  src/app/
    core/           servizi API, store notifiche, push, toast
    pages/          dashboard, scadenze, import, impostazioni
    shared/         campanella notifiche, badge scadenza
```

## Quando il cliente indicherà dove sono registrate le scadenze

Il sistema nasce con un database proprio e un livello di import isolato, quindi l'integrazione è additiva:

- **file periodico (CSV/Excel)** — già supportato, anche schedulabile
- **database o API del gestionale** — implementare un `SourceAdapter` in `backend/app/services/importers/` che restituisca una `SourceTable`; la pipeline di mappatura, l'upsert per `(source, external_id)` e la generazione degli avvisi restano invariati

## Non incluso (da decidere con il cliente)

- **Autenticazione**: l'API è aperta, pensata per rete interna. Prima di esporla su Internet va aggiunto un livello di login (OAuth2/JWT o SSO aziendale) e la separazione per utente.
- Allegati sulle scadenze, log di audit, export PDF/Excel.
