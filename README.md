# Promemoria

Scadenze, appuntamenti e note con avvisi automatici e **notifiche desktop**, distribuiti come
**applicazione Windows** installata sulle postazioni, senza server da tenere acceso.

- **backend** — FastAPI + SQLAlchemy, scheduler integrato; gira come processo locale dentro l'app
- **frontend** — Angular 22 (standalone + signals), interfaccia in italiano, tema chiaro/scuro automatico
- **desktop** — Electron: finestra, icona nella tray, avvio automatico, notifiche native di Windows, aggiornamenti automatici

## Architettura

```
   PC 1                     PC 2                     PC 3
┌──────────────┐        ┌──────────────┐        ┌──────────────┐
│ Promemoria   │        │ Promemoria   │        │ Promemoria   │
│ (Electron +  │        │ (Electron +  │        │ (Electron +  │
│  backend)    │        │  backend)    │        │  backend)    │
│              │        │              │        │              │
│ locale.db ───┼─ avvisi│ locale.db ───┼─ avvisi│ locale.db ───┼─ avvisi
└──────┬───────┘  mostrati└─────┬──────┘ mostrati└─────┬───────┘ mostrati
       └───────────────────────┬┴───────────────────────┘
                               │
                  PostgreSQL gestito (cloud, piano gratuito)
                  promemoria · impostazioni
```

Due database con due ruoli distinti:

- **condiviso** (PostgreSQL): i promemoria, uguali per tutti — chi ne aggiunge uno lo fa vedere agli altri;
- **locale** (SQLite su ogni PC): quali avvisi *questa* postazione ha già mostrato, così ognuno riceve le proprie notifiche senza pestarsi i piedi con gli altri.

**Conseguenza da conoscere**: non essendoci una macchina sempre accesa, se tutti i PC sono spenti nessun avviso parte in quel momento. Gli avvisi arretrati non si perdono: vengono mostrati all'accensione successiva.

## Cosa fa

- **Tre tipi di promemoria**: scadenza, appuntamento e «altro». Cambia il modo di leggerli — una scadenza «scade», un appuntamento no — e il testo degli avvisi segue di conseguenza
- Anagrafica essenziale: titolo, data, **orario facoltativo** (solo appuntamenti e «altro»), importo, cliente/responsabile, riferimento, note
- **Vista calendario mensile** in stile agenda: griglia lunedì → domenica, promemoria dentro ai giorni ordinati per ora e colorati per tipo, filtro per tipo, pannello del giorno e inserimento con la data già compilata
- **Vista annuale**: dodici mesi in miniatura con un pallino sui giorni che hanno qualcosa; si clicca un giorno per aprirlo nel mese
- **Preavvisi configurabili** (es. 30, 15, 7, 3, 1, 0 giorni prima) a livello globale o per singolo promemoria
- **Solleciti dopo la data** ogni N giorni, con tetto massimo
- **Avviso di recupero**: un promemoria inserito quando è già passato (o già dentro la finestra di preavviso) genera comunque un avviso immediato
- **Ricorrenze**: giornaliera, settimanale, ogni due settimane, mensile, bimestrale, trimestrale, quadrimestrale, semestrale, annuale, biennale, triennale, quinquennale, oppure **personalizzata** — «ogni 45 giorni», «ogni 18 mesi», qualsiasi intervallo fino a 999 giorni, settimane, mesi o anni. Senza data di fine l'occorrenza successiva nasce alla chiusura di quella corrente; indicando **fino a quando**, le occorrenze vengono create tutte insieme e ognuna può avere il proprio importo — le rate di un finanziamento raramente sono uguali. Le occorrenze di una serie si eliminano anche tutte in un colpo
- **Canali di notifica** attivabili singolarmente: centro notifiche in-app, Web Push (desktop), email SMTP
- **Segnalazione insistente**: un avviso ignorato per un promemoria imminente continua a farsi notare sulla barra delle applicazioni (lampeggio, bollino sul pulsante, bollino sull'icona nella tray) finché non si apre il promemoria o l'elenco. La soglia in giorni è impostabile, 0 la disattiva
- **Importazione CSV/Excel** con riconoscimento automatico delle colonne, anteprima con validazione riga per riga e reimport idempotente (aggiorna, non duplica)
- Dashboard con scaduti / oggi / 7 / 30 giorni, ripartizione per tipo, totale importi aperti

## Notifiche desktop: cosa aspettarsi

| Situazione | Notifica |
|---|---|
| Applicazione aperta | Sì: toast di Windows + campanella nell'app |
| Finestra chiusa, applicazione nella tray | **Sì**: toast di Windows |
| Applicazione chiusa del tutto | No in quel momento; gli avvisi arretrati compaiono al riavvio |
| PC spento | Come sopra: si recuperano all'accensione |

Con l'app desktop le notifiche sono quelle native di Windows, quindi **non servono HTTPS, certificati o dominio**. Il canale Web Push resta nel codice e si attiva da solo se si vuole usare l'applicazione da browser (vedi `VAPID_*`).

Il canale email è disponibile come rete di sicurezza: va acceso su **una sola** postazione (`EMAIL_SENDER_DEVICE=true`), altrimenti ogni PC acceso invia la sua copia.

## Configurazione al primo avvio

**Le credenziali del database non sono dentro l'installer.** Alla prima apertura ogni postazione mostra una schermata dove si incolla la stringa di connessione, che viene verificata e salvata in `%LOCALAPPDATA%\Promemoria\config.json` **su quel solo computer**.

Perché è fatto così:

- l'installer resta un file neutro, pubblicabile fra le release senza esporre il database;
- cambiare la password di Neon non richiede di ricompilare e ridistribuire l'applicazione;
- lo stesso pacchetto serve per un altro cliente, con un database diverso.

Limite noto e non eliminabile in questa architettura: chi ha accesso a una postazione può leggere quel file di configurazione. Eliminarlo richiederebbe un server intermedio che custodisce le credenziali, cioè la macchina sempre accesa che si è scelto di non avere.

Finché la configurazione manca, il backend parte lo stesso (serve la schermata di setup) ma ogni chiamata ai dati condivisi risponde `503 not_configured`, e l'interfaccia rimanda alla configurazione. Non viene creato nessun database locale di ripiego: sarebbe il modo più rapido per ritrovarsi tre archivi diversi senza accorgersene.

In sviluppo si può saltare la schermata valorizzando `DATABASE_URL` in `backend/.env`: ha precedenza minore del file di configurazione, quindi non interferisce con le postazioni reali.

## Database condiviso (Neon)

Progetto Neon: **Scadenzario** (nome storico, invariato), PostgreSQL 18, regione `eu-central-1` (Francoforte), piano gratuito.

```
DATABASE_URL=postgresql+psycopg://<utente>:<password>@<host>.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

Il prefisso `+psycopg` è obbligatorio: indica a SQLAlchemy quale driver usare.

Due avvertenze operative:

- Il piano gratuito **va in standby dopo qualche minuto di inattività**: la prima richiesta della giornata impiega qualche secondo in più per risvegliare il database. Nessun impatto sul funzionamento.
- La connection string contiene la password del database ed è replicata sul `.env` di ogni postazione: chi ha accesso a quei PC ha accesso ai dati. Per rigenerarla: dashboard Neon → *Reset password*, poi aggiornare i `.env`.

Sul database condiviso vivono solo due tabelle — `reminders` e `settings`. Le notifiche stanno nel database locale di ciascuna postazione.

## Evoluzione dello schema

Lo schema è gestito con **Alembic** e si aggiorna da sé: a ogni avvio il backend porta il database locale all'ultima revisione, e fa lo stesso con quello condiviso appena la postazione è configurata. Un aggiornamento dell'applicazione porta quindi con sé il proprio adeguamento del database, senza interventi manuali sulle postazioni.

I due database hanno storie separate — tabelle di versione distinte, `alembic_version` e `alembic_version_local` — perché uno è condiviso da tutti e l'altro appartiene alla singola postazione.

### Quando una postazione resta indietro

Le postazioni non si aggiornano tutte nello stesso istante. La prima che lo fa applica la migrazione al database condiviso, e da quel momento chi è rimasto alla versione precedente trova nel database una revisione che non conosce: non si collega più, e la schermata di configurazione prende il posto dell'applicazione. È voluto — lavorare su uno schema che il codice non si aspetta farebbe danni peggiori — ma **non deve richiedere che qualcuno vada a scaricare l'installer a mano**.

Tre meccanismi lo evitano, dal più visibile al più silenzioso:

- **Il pulsante «Aggiorna adesso»**, sulla schermata di configurazione, compare *solo* per questo guasto: `SchemaPiuRecente` porta il codice `schema_piu_recente`, che arriva all'interfaccia in `last_error_code`. Scarica e riavvia sul posto, mostrando la percentuale. Con un database irraggiungibile o una password sbagliata il pulsante non compare, perché aggiornare non servirebbe.
- **L'installazione a finestra nascosta**: un aggiornamento già scaricato non aspetta più una chiusura che su un'app che vive nella tray non arriva mai. Dopo dieci minuti di finestra nascosta si applica da sé — un minuto solo, se la postazione è già bloccata, dove non c'è nessun lavoro da interrompere.
- **Il controllo ogni ora** invece che ogni giorno, e subito all'avvio: quando l'utente arriva sulla schermata, il pacchetto è spesso già pronto e il pulsante riavvia e basta.

`/api/health` espone `schema_ahead` perché il processo Electron possa saperlo: l'interfaccia non la legge, e quella rotta la interroga già all'avvio.

Resta un limite che nessuna versione futura può togliere: **il comportamento di una postazione bloccata lo decide il codice già installato lì**. Una postazione ferma a una versione precedente a questa manutenzione va aggiornata a mano quell'ultima volta.

Le installazioni nate prima delle migrazioni (la 1.0.0, che creava le tabelle con `create_all`) non vengono ricreate: al primo avvio lo schema esistente viene *marcato* alla revisione iniziale, e da lì in poi segue le migrazioni normalmente.

### Aggiornamento alla 1.1.0 — da Scadenzario a Promemoria

La 1.1.0 rinomina le tabelle (`deadlines` → `reminders`, `notifications.deadline_id` → `reminder_id`) e aggiunge il tipo e l'orario. **I dati non si perdono**: la migrazione `0002` rinomina, non ricrea, e tutti i promemoria esistenti diventano di tipo «scadenza», che è quello che erano.

La migrazione `0003` **elimina categoria e priorità**, per snellire una schermata di inserimento diventata troppo lunga. Qui invece qualcosa si perde, ed è voluto: la tabella `categories` viene cancellata insieme ai preavvisi che si portava dietro. I promemoria restano tutti; i preavvisi continuano a funzionare a due livelli (quelli scritti sul singolo promemoria, e in mancanza quelli generali delle impostazioni) invece dei tre di prima.

Due conseguenze operative, entrambe volute:

- **L'aggiornamento va fatto su tutte le postazioni.** Una postazione ferma alla 1.0.x non riconosce più lo schema del database condiviso e smette di funzionare finché non aggiorna. Gli aggiornamenti sono automatici e una postazione bloccata si sblocca da sé (vedi *Quando una postazione resta indietro*), ma un PC rimasto spento a lungo va acceso e lasciato aggiornare prima dell'uso.
- **La cartella dati cambia nome**, da `%LOCALAPPDATA%\Scadenzario` a `%LOCALAPPDATA%\Promemoria`. Lo spostamento è automatico e porta con sé `config.json` e il database locale degli avvisi, così non va rifatta la configurazione. Se la cartella risulta occupata si continua a usare la vecchia e si riprova al riavvio successivo.

Restano invariati di proposito, perché cambiarli farebbe danni senza portare vantaggi: l'`appId` di electron-builder (`it.scadenzario.desktop`) — cambiarlo installerebbe la 1.1.0 **accanto** alla vecchia invece che al suo posto — il repository GitHub degli aggiornamenti e il nome del progetto Neon. Sono identificatori interni che nessun utente legge. Restano validi anche i collegamenti `scadenzario://` dei toast già mostrati, e le vecchie rotte `/scadenze/...` rimandano alle nuove.

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

## Pubblicare una versione

```powershell
$env:GH_TOKEN = "<token GitHub con permesso contents: write>"
.\scripts\release.ps1 -Version 1.0.3
```

Lo script fa il giro completo — test, numero di versione, compilazione, commit, tag, release, verifica — e si ferma al primo passo che non torna, invece di lasciare a metà qualcosa che sembra riuscito.

Due accorgimenti nascono da altrettante pubblicazioni andate storte:

- **il tag si crea prima della release**: GitHub rifiuta una release definitiva se il tag non esiste ancora;
- **la release vuota si crea prima di electron-builder**: che avvia due pubblicazioni in parallelo (installer e blockmap), e se la release manca entrambe provano a crearla — quella che perde la corsa muore, spesso portandosi dietro il caricamento dell'installer.

L'ordine di compilazione non è negoziabile: il frontend finisce dentro l'eseguibile del backend, che finisce dentro il pacchetto Electron. Saltare un anello significa pubblicare codice vecchio con un numero di versione nuovo, senza che nulla lo segnali.

Alla fine viene confrontato lo **sha512 dichiarato in `latest.yml` con quello calcolato sull'installer**: se non coincidono le postazioni scaricherebbero l'aggiornamento per poi rifiutarlo. Se la release risulta incompleta, i file parziali vengono rimossi e si ritenta (fino a tre volte).

Per riesaminare una release già pubblicata, senza pubblicare niente:

```powershell
.\scripts\release.ps1 -Version 1.0.2 -VerifyOnly
```

### Se la compilazione si ferma con `spawn UNKNOWN`

Sintomo: electron-builder arriva a `building target=nsis`, stampa una riga `signing with signtool.exe`, e muore con `spawn UNKNOWN` dentro `NsisTarget.computeScriptAndSignUninstaller`.

La riga sulla firma è un depistaggio — gira in parallelo e non c'entra. La chiamata che fallisce **esegue l'installer appena costruito**, perché è l'installer stesso a generare il proprio disinstallatore. Windows si rifiuta di lanciarlo: un eseguibile NSIS appena scritto e non firmato è esattamente ciò che la protezione in tempo reale di Defender blocca. Il file c'è sul disco, e questo rende il sintomo ingannevole: sembra un percorso sbagliato, non un divieto.

Il rimedio è escludere la sola cartella di compilazione, da una finestra **con permessi di amministratore**:

```powershell
Add-MpPreference -ExclusionPath "<percorso del progetto>\desktop\release"
```

Si toglie con `Remove-MpPreference -ExclusionPath`. Vale la pena rifare il controllo dopo un aggiornamento di Windows, che le esclusioni le ha già azzerate.

Un secondo inciampo si presenta insieme al primo e va distinto, perché il messaggio è simile ma la causa no: l'archivio `winCodeSign` che electron-builder scarica contiene due link simbolici per macOS, e crearli su Windows richiede un privilegio che un utente normale non ha. L'estrazione si interrompe, la cartella resta a metà e `signtool.exe` non esiste davvero. Qui l'errore è genuinamente un file mancante. Per rimediare basta chiedere la stessa estrazione una seconda volta, che arriva in fondo tollerando i due link:

```powershell
cd desktop
node -e "require('./node_modules/app-builder-lib/out/toolsets/windows.js').getSignToolPath(undefined,true).then(r=>console.log(r.path, require('fs').existsSync(r.path)))"
```

Deve stampare un percorso e `true`.

Ultima avvertenza, sul metodo più che sullo strumento: **non incanalare l'output dello script con `2>&1`**. PowerShell 5.1 avvolge in un errore ogni riga che un eseguibile scrive su stderr, e PyInstaller ci scrive il suo normale avanzamento: lo script sembra fallito al passo 5 quando non è successo niente.

## Avvio — applicazione desktop (sviluppo)

```powershell
cd frontend; npm install; npx ng build      # l'app carica il frontend compilato
cd ..\desktop; npm install
$env:PROMEMORIA_DEV = '1'; npm start
```

L'app avvia da sé il backend dal venv, apre la finestra, resta nella tray alla chiusura e mostra i toast di Windows.
Per lavorare sul frontend con ricaricamento a caldo: avvia `npm start` nel frontend e aggiungi `$env:PROMEMORIA_UI = 'http://localhost:4300'`.

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
| `LOCAL_DATABASE_URL` | Database locale della postazione (vuoto = `%LOCALAPPDATA%\Promemoria\locale.db`) |
| `EMAIL_SENDER_DEVICE` | `true` su **una sola** postazione, per non moltiplicare le email |
| `DEFAULT_ALERT_OFFSETS` | Preavvisi predefiniti in giorni |
| `OVERDUE_REPEAT_DAYS` / `OVERDUE_MAX_REMINDERS` | Solleciti dopo la data |
| `DAILY_SEND_TIME` | Orario di invio degli avvisi del giorno |
| `SCHEDULER_INTERVAL_SECONDS` | Frequenza del ciclo interno (default 300s) |
| `VAPID_*` | Chiavi Web Push — senza queste il canale desktop resta disattivo |
| `SMTP_*` | Invio email — con `SMTP_HOST` vuoto il canale resta disattivo |

Preavvisi, orari, canali e destinatari sono modificabili anche a runtime dalla pagina **Impostazioni**, senza riavviare il backend.

## Come funziona lo scheduler

Ogni `SCHEDULER_INTERVAL_SECONDS` il backend:

1. ricalcola gli avvisi pendenti di tutti i promemoria aperti (`alerts.sync_all`);
2. spedisce quelli la cui ora di invio è arrivata, su tutti i canali attivi (`dispatcher.dispatch_due`).

Ogni avviso ha una `dedupe_key`, quindi non viene mai inviato due volte. Il ciclo è richiamabile anche manualmente con `POST /api/scheduler/run` (o dal pulsante "Esegui ciclo avvisi adesso"): utile se in produzione preferisci un cron esterno o più repliche del backend.

## Struttura

```
backend/
  alembic/          migrazioni dello schema (condiviso e locale)
  tests/            test del motore avvisi, delle ricorrenze e degli endpoint
  app/
    api/            endpoint REST (promemoria, notifiche, push, import, impostazioni)
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
    pages/          dashboard, calendario, promemoria, import, impostazioni
    shared/         campanella notifiche, badge scadenza, icone dei tipi
```

## Quando il cliente indicherà dove sono registrati i dati di partenza

Il sistema nasce con un database proprio e un livello di import isolato, quindi l'integrazione è additiva:

- **file periodico (CSV/Excel)** — già supportato, anche schedulabile
- **database o API del gestionale** — implementare un `SourceAdapter` in `backend/app/services/importers/` che restituisca una `SourceTable`; la pipeline di mappatura, l'upsert per `(source, external_id)` e la generazione degli avvisi restano invariati

## Non incluso (da decidere con il cliente)

- **Autenticazione**: l'API è aperta, pensata per rete interna. Prima di esporla su Internet va aggiunto un livello di login (OAuth2/JWT o SSO aziendale) e la separazione per utente.
- Allegati sui promemoria, log di audit, export PDF/Excel, invito degli appuntamenti in Outlook/Google Calendar.
