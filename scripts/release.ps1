<#
.SYNOPSIS
    Pubblica una nuova versione dello Scadenzario, e verifica che sia davvero pubblicabile.

.DESCRIPTION
    Il giro completo: test, numero di versione, compilazione, tag, release, verifica.

    Nasce da due pubblicazioni andate storte, con cause diverse ma lo stesso
    effetto — una release a metà, che su GitHub sembra riuscita:

      1. GitHub rifiuta una release definitiva se il tag non esiste ancora.
         Qui il tag si crea e si spinge PRIMA di pubblicare.
      2. electron-builder avvia due pubblicazioni in parallelo (installer e
         blockmap); se la release non esiste, entrambe provano a crearla e
         quella che perde la corsa muore, spesso portandosi dietro il
         caricamento dell'installer. Qui la release vuota si crea prima, così
         non c'è niente da contendersi.

    Alla fine il controllo che conta davvero: lo sha512 scritto in `latest.yml`
    viene confrontato con quello calcolato sull'installer. Se non coincidono, le
    postazioni scaricherebbero l'aggiornamento per poi rifiutarlo, ed è meglio
    accorgersene qui.

.PARAMETER Version
    Numero della nuova versione, es. 1.0.3.

.PARAMETER SkipTests
    Salta la suite del backend. Da usare solo se l'hai appena eseguita.

.PARAMETER VerifyOnly
    Non pubblica niente: controlla soltanto che la release indicata sia
    completa e coerente. Utile per riesaminare una pubblicazione passata.

.EXAMPLE
    $env:GH_TOKEN = "<token>"
    .\scripts\release.ps1 -Version 1.0.3

.EXAMPLE
    .\scripts\release.ps1 -Version 1.0.2 -VerifyOnly
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version,

    [switch]$SkipTests,

    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $RepoRoot "backend"
$Frontend = Join-Path $RepoRoot "frontend"
$Desktop = Join-Path $RepoRoot "desktop"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$Tag = "v$Version"
$Installer = Join-Path $Desktop "release\Scadenzario Setup $Version.exe"

# ------------------------------------------------------------------- utilità

$script:Passo = 0
function Write-Passo([string]$testo) {
    $script:Passo++
    Write-Host ""
    Write-Host "[$script:Passo] $testo" -ForegroundColor Cyan
}

function Stop-Con([string]$messaggio) {
    Write-Host ""
    Write-Host "INTERROTTO: $messaggio" -ForegroundColor Red
    exit 1
}

<# Esegue un comando esterno e si ferma se esce con errore.
   Serve perché PowerShell non considera un exit code diverso da zero un
   errore terminante: senza questo, uno script "riuscito" può avere dentro
   una compilazione fallita. #>
function Invoke-Comando([string]$descrizione, [scriptblock]$comando) {
    & $comando
    if ($LASTEXITCODE -ne 0) {
        Stop-Con "$descrizione (codice $LASTEXITCODE)"
    }
}

<# Lettura e scrittura di file di testo del progetto.

   Non si usano Get-Content/Set-Content: su PowerShell 5.1 `Get-Content -Raw`
   legge un file UTF-8 privo di BOM come se fosse ANSI — accenti e trattini
   lunghi diventano illeggibili — e `Set-Content -Encoding utf8` riscrive
   aggiungendo un BOM, che in testa a package.json basta a rendere il file
   JSON invalido per Node. .NET invece riconosce la codifica da sé e sa
   scrivere UTF-8 pulito. #>
function Read-TestoUtf8([string]$percorso) {
    return [System.IO.File]::ReadAllText($percorso)
}

function Write-TestoUtf8([string]$percorso, [string]$testo) {
    $senzaBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($percorso, $testo, $senzaBom)
}

function Get-Sha512Base64([string]$percorso) {
    $sha = [System.Security.Cryptography.SHA512]::Create()
    $stream = [System.IO.File]::OpenRead($percorso)
    try {
        return [Convert]::ToBase64String($sha.ComputeHash($stream))
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

function Get-IntestazioniGitHub() {
    return @{
        Authorization          = "Bearer $env:GH_TOKEN"
        Accept                 = "application/vnd.github+json"
        "X-GitHub-Api-Version" = "2022-11-28"
    }
}

function Get-Release([string]$slug, [string]$tag) {
    try {
        return Invoke-RestMethod -Uri "https://api.github.com/repos/$slug/releases/tags/$tag" -Headers (Get-IntestazioniGitHub)
    } catch {
        return $null
    }
}

function Test-Pubblicazione([string]$slug, [string]$tag, [string]$installer) {
    <# Ritorna $null se la release è pubblicabile, altrimenti il motivo. #>
    $r = Get-Release $slug $tag
    if (-not $r) { return "release non trovata" }

    $attesi = @("Scadenzario-Setup-$Version.exe", "Scadenzario-Setup-$Version.exe.blockmap", "latest.yml")
    $presenti = $r.assets | ForEach-Object { $_.name }
    $mancanti = $attesi | Where-Object { $presenti -notcontains $_ }
    if ($mancanti) { return "file mancanti: $($mancanti -join ', ')" }

    $nonCaricati = $r.assets | Where-Object { $_.state -ne "uploaded" }
    if ($nonCaricati) { return "file non caricati del tutto: $($nonCaricati.name -join ', ')" }

    if (-not (Test-Path $installer)) {
        return "installer non presente in locale ($installer): impossibile confrontare lo sha512"
    }

    # Il controllo che conta: se questi due non coincidono, le postazioni
    # scaricano l'aggiornamento e poi lo rifiutano per checksum errato.
    $yml = Invoke-RestMethod -Uri "https://github.com/$slug/releases/download/$tag/latest.yml"
    $dichiarato = ([regex]::Match($yml, 'sha512:\s*(\S+)')).Groups[1].Value
    $reale = Get-Sha512Base64 $installer
    if ($dichiarato -ne $reale) {
        return "sha512 diverso fra latest.yml e installer: le postazioni rifiuterebbero l'aggiornamento"
    }
    return $null
}

# ------------------------------------------------------- controlli preliminari

Write-Passo "Controlli preliminari"

if (-not $env:GH_TOKEN) {
    Stop-Con "GH_TOKEN non impostato. Serve un token GitHub con permesso 'contents: write'."
}

Set-Location $RepoRoot

# Il repository legge owner/repo dalla configurazione di electron-builder, così
# non c'è un secondo posto da aggiornare se il progetto cambia casa.
$pkg = Read-TestoUtf8 (Join-Path $Desktop "package.json") | ConvertFrom-Json
$pubblicazione = $pkg.build.publish[0]
$slug = "$($pubblicazione.owner)/$($pubblicazione.repo)"

if ($VerifyOnly) {
    Write-Passo "Verifica della release $Tag (nessuna pubblicazione)"
    $problema = Test-Pubblicazione $slug $Tag $Installer
    if ($problema) {
        Stop-Con "Release $Tag incompleta o incoerente: $problema"
    }
    Write-Host ""
    Write-Host "RELEASE $Tag COMPLETA E COERENTE" -ForegroundColor Green
    Write-Host "  installer, blockmap e latest.yml presenti; sha512 verificato sul file."
    exit 0
}

if (-not (Test-Path $Python)) {
    Stop-Con "Ambiente Python non trovato in $Python"
}

$ramo = (git rev-parse --abbrev-ref HEAD).Trim()
if ($ramo -ne "main") {
    Stop-Con "Sei sul ramo '$ramo'. Le release si fanno da main."
}

$sporco = git status --porcelain
if ($sporco) {
    Write-Host $sporco
    Stop-Con "Ci sono modifiche non committate. Committale o annullale prima di pubblicare."
}

if ($pkg.version -eq $Version) {
    Write-Host "  La versione e' gia' ${Version}: proseguo (utile per riprendere una pubblicazione interrotta)." -ForegroundColor Yellow
}

$esistente = Get-Release $slug $Tag
if ($esistente -and $esistente.assets.Count -ge 3) {
    Stop-Con "La release $Tag risulta gia' pubblicata e completa. Usa un numero di versione nuovo."
}

Write-Host "  Repository : $slug"
Write-Host "  Versione   : $($pkg.version) -> $Version"

# -------------------------------------------------------------------- test

if ($SkipTests) {
    Write-Passo "Test saltati su richiesta"
} else {
    Write-Passo "Test del backend"
    Push-Location $Backend
    try {
        Invoke-Comando "test falliti" { & $Python -m pytest }
    } finally {
        Pop-Location
    }
}

# --------------------------------------------------------- numero di versione

Write-Passo "Numero di versione"

$percorsoPkg = Join-Path $Desktop "package.json"
$testoPkg = Read-TestoUtf8 $percorsoPkg
Write-TestoUtf8 $percorsoPkg ([regex]::Replace($testoPkg, '("version"\s*:\s*)"\d+\.\d+\.\d+"', "`${1}`"$Version`"", 1))

$percorsoMain = Join-Path $Backend "app\main.py"
$testoMain = Read-TestoUtf8 $percorsoMain
Write-TestoUtf8 $percorsoMain ([regex]::Replace($testoMain, '(version=)"\d+\.\d+\.\d+"', "`${1}`"$Version`"", 1))

# Rileggere e ricontrollare non è pignoleria: un file rovinato qui si
# manifesta molto più avanti, quando electron-builder non riesce più a
# leggere package.json, e a quel punto il motivo non è più evidente.
$primiByte = [System.IO.File]::ReadAllBytes($percorsoPkg)
if ($primiByte.Length -ge 3 -and $primiByte[0] -eq 0xEF -and $primiByte[1] -eq 0xBB -and $primiByte[2] -eq 0xBF) {
    Stop-Con "package.json e' stato scritto con un BOM: Node non riuscirebbe a leggerlo."
}
try {
    $riletto = Read-TestoUtf8 $percorsoPkg | ConvertFrom-Json
} catch {
    Stop-Con "package.json non e' piu' JSON valido dopo il cambio di versione."
}
if ($riletto.version -ne $Version) {
    Stop-Con "package.json riporta ancora la versione $($riletto.version)."
}
if ((Read-TestoUtf8 $percorsoMain) -notmatch [regex]::Escape("version=`"$Version`"")) {
    Stop-Con "app/main.py non riporta la versione $Version."
}

Write-Host "  Aggiornati e riletti package.json e app/main.py"

# ------------------------------------------------------------- compilazione

# L'ordine non è negoziabile: il frontend compilato finisce dentro
# l'eseguibile del backend, che a sua volta finisce dentro il pacchetto
# Electron. Saltare un anello significa pubblicare codice vecchio con un
# numero di versione nuovo — e non se ne accorge nessuno.

Write-Passo "Compilazione frontend"
Push-Location $Frontend
try {
    Invoke-Comando "compilazione del frontend fallita" { npx ng build }
} finally {
    Pop-Location
}

Write-Passo "Compilazione backend impacchettato"
Push-Location $Backend
try {
    Invoke-Comando "PyInstaller fallito" { & $Python -m PyInstaller scadenzario-backend.spec --noconfirm }
} finally {
    Pop-Location
}

$migrazioni = Join-Path $Backend "dist\scadenzario-backend\_internal\alembic\versions"
if (-not (Test-Path $migrazioni)) {
    Stop-Con "Le migrazioni non sono finite nel pacchetto: l'app installata non partirebbe."
}
Write-Host "  Migrazioni incluse nel pacchetto"

# -------------------------------------------------------------- commit e tag

Write-Passo "Commit, push e tag"

git add -- (Join-Path $Desktop "package.json") (Join-Path $Backend "app\main.py")
$daCommittare = git diff --cached --name-only
if ($daCommittare) {
    Invoke-Comando "commit fallito" { git commit -m "Versione $Version" }
    Invoke-Comando "push fallito" { git push }
} else {
    Write-Host "  Nessuna modifica di versione da committare"
}

$tagLocale = git tag --list $Tag
if (-not $tagLocale) {
    Invoke-Comando "creazione del tag fallita" { git tag $Tag }
}
# Il tag deve stare su GitHub PRIMA della release: senza, la creazione di una
# release definitiva viene rifiutata con 422.
Invoke-Comando "push del tag fallito" { git push origin $Tag }
Write-Host "  Tag $Tag pubblicato"

# ----------------------------------------------------------------- release

Write-Passo "Preparazione della release"

$release = Get-Release $slug $Tag
if ($release) {
    Write-Host "  Release $Tag gia' presente (id $($release.id))"
} else {
    # Creandola adesso, le due pubblicazioni parallele di electron-builder la
    # trovano già fatta e non se la contendono.
    $corpo = @{ tag_name = $Tag; name = $Version; draft = $false; prerelease = $false } | ConvertTo-Json
    $release = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$slug/releases" `
        -Headers (Get-IntestazioniGitHub) -Body $corpo -ContentType "application/json"
    Write-Host "  Release $Tag creata (id $($release.id))"
}

# ------------------------------------------------- pubblicazione e verifica

$tentativi = 3
for ($i = 1; $i -le $tentativi; $i++) {
    Write-Passo "Pubblicazione su GitHub (tentativo $i di $tentativi)"

    Push-Location $Desktop
    try {
        & npx electron-builder --publish always
        $esito = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($esito -ne 0) {
        Write-Host "  electron-builder ha restituito $esito" -ForegroundColor Yellow
    }

    Write-Host "  Verifica di quanto è stato pubblicato..."
    $problema = Test-Pubblicazione $slug $Tag $Installer
    if (-not $problema) {
        Write-Host ""
        Write-Host "PUBBLICATA: $Tag" -ForegroundColor Green
        Write-Host "  https://github.com/$slug/releases/tag/$Tag"
        Write-Host "  installer, blockmap e latest.yml presenti; sha512 verificato sul file."
        Write-Host ""
        Write-Host "Le postazioni riceveranno l'aggiornamento al prossimo avvio."
        exit 0
    }

    Write-Host "  Release incompleta: $problema" -ForegroundColor Yellow
    if ($i -lt $tentativi) {
        # Si riparte puliti: file parziali di un tentativo andato male non
        # devono mescolarsi a quelli della compilazione successiva, che ha
        # firma e quindi hash diversi.
        Write-Host "  Rimuovo i file parziali e ritento..." -ForegroundColor Yellow
        $r = Get-Release $slug $Tag
        foreach ($asset in $r.assets) {
            Invoke-RestMethod -Method Delete -Headers (Get-IntestazioniGitHub) `
                -Uri "https://api.github.com/repos/$slug/releases/assets/$($asset.id)" | Out-Null
        }
    }
}

Stop-Con "Pubblicazione non riuscita dopo $tentativi tentativi. La release $Tag e' rimasta incompleta: controllala su https://github.com/$slug/releases/tag/$Tag"
