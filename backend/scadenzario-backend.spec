# Pacchetto del backend, incluso nell'app desktop.
#
#   .venv\Scripts\python.exe -m PyInstaller scadenzario-backend.spec --noconfirm
#
# Il frontend compilato viene incluso in `app/static`, così l'eseguibile serve
# sia le API sia l'interfaccia.
#
# Modalità cartella (non file unico) di proposito: il file unico si estrae in
# una cartella temporanea a ogni avvio, che su questo pacchetto significa
# decine di secondi di attesa prima che la finestra si apra. In modalità
# cartella l'avvio è immediato, e il contenuto finisce comunque nascosto nelle
# risorse dell'applicazione.

from PyInstaller.utils.hooks import collect_submodules

hidden = [
    *collect_submodules("uvicorn"),
    *collect_submodules("psycopg"),
    "psycopg.pq",
    "psycopg_binary",
    "openpyxl",
    "email_validator",
    "pywebpush",
    "dateutil",
    "tzdata",
]

a = Analysis(
    ["run_backend.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("../frontend/dist/frontend/browser", "app/static"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="scadenzario-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Console attiva: uvicorn e il logging scrivono sui flussi standard, che in
    # modalità windowed non esistono e fanno terminare il processo all'avvio.
    # La finestra della console non si vede comunque: Electron avvia il
    # processo con `windowsHide`.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="scadenzario-backend",
)
