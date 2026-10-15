# Roda os scrapers do SofaScore (Argentina e Reino Unido) NO PC e publica.
#
# Por que no PC: o SofaScore devolve 403 para tudo que sai do GitHub Actions
# (ver diag_sofascore_ci.py); de um IP residencial funciona. Os workflows
# atualizar-argentina-sofascore.yml / atualizar-reino-unido-sofascore.yml
# ficaram so com workflow_dispatch.
#
# Roda num clone SO desta automacao (padrao D:\scrapper\jogos-chile-scraper-auto),
# porque faz "git reset --hard origin/main" para mesclar contra o estado atual
# do main - exatamente como os workflows fazem. Nunca apontar para a copia de
# trabalho.
#
# Agendado pela tarefa "jogos-chile SofaScore diario" do Agendador de Tarefas
# do Windows. Log: <clone>\logs\sofascore_local_AAAA-MM-DD.log
#
# Uso manual:
#   powershell -ExecutionPolicy Bypass -File rodar_sofascore_local.ps1
#   powershell -ExecutionPolicy Bypass -File rodar_sofascore_local.ps1 -SemPush   # teste

param(
    [string]$Clone = "D:\scrapper\jogos-chile-scraper-auto",
    [string]$Python = "C:\Users\galha\AppData\Local\Python\pythoncore-3.14-64\python.exe",
    [switch]$SemPush
)

$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Set-Location $Clone
New-Item -ItemType Directory -Force "$Clone\logs" | Out-Null
$log = "$Clone\logs\sofascore_local_$(Get-Date -Format yyyy-MM-dd).log"
Start-Transcript -Path $log -Append | Out-Null

function Rodar([string]$descricao, [string[]]$argumentos) {
    Write-Output "=== $descricao"
    & $Python @argumentos 2>&1 | ForEach-Object { "$_" }
    if ($LASTEXITCODE -ne 0) { Write-Output "[ERRO] $descricao terminou com codigo $LASTEXITCODE" }
    return ($LASTEXITCODE -eq 0)
}

try {
    git fetch -q origin main
    git reset -q --hard origin/main

    # Caches de venue ficam fora do git reset (sao versionados, mas a rodada
    # pode ter acrescentado times): guardados junto com os raw.
    $tmp = Join-Path $env:TEMP "jogos_sofascore_local"
    New-Item -ItemType Directory -Force $tmp | Out-Null
    Get-ChildItem $tmp -File | Remove-Item -Force -Confirm:$false

    $okAr = Rodar "SofaScore Argentina" @("scrap_argentina_sofascore.py", "--dias", "60", "--dias-atras", "7")
    $okUk = Rodar "SofaScore Reino Unido" @("scrap_reino_unido_sofascore.py", "--dias", "270", "--dias-atras", "15")

    $arquivos = @(
        "data\debug_argentina_sofascore_raw.json", "data\debug_argentina_sofascore_hist_raw.json",
        "data\debug_argentina_sofascore_eventos.json", "data\argentina\cache_venues_sofascore.json",
        "data\debug_uk_sofascore_raw.json", "data\debug_uk_sofascore_hist_raw.json",
        "data\debug_uk_sofascore_eventos.json", "data\reino_unido\cache_venues_sofascore.json"
    )
    foreach ($a in $arquivos) {
        if (Test-Path $a) { Copy-Item $a (Join-Path $tmp ($a -replace '[\\/]', '__')) -Force }
    }

    for ($tentativa = 1; $tentativa -le 5; $tentativa++) {
        git fetch -q origin main
        git reset -q --hard origin/main
        foreach ($a in $arquivos) {
            $salvo = Join-Path $tmp ($a -replace '[\\/]', '__')
            if (Test-Path $salvo) { Copy-Item $salvo $a -Force }
        }

        if ($okAr) {
            Rodar "merge Argentina" @("merge_apos_reset.py", "--raw", "data/debug_argentina_sofascore_raw.json", "--raw-historico", "data/debug_argentina_sofascore_hist_raw.json") | Out-Null
            Rodar "dedupe Argentina" @("argentina_comum.py", "--dedupe") | Out-Null
            git add data/jogos_programados.csv data/jogos_programados.json data/historico_jogos.csv data/argentina/ data/debug_argentina_sofascore_raw.json data/debug_argentina_sofascore_hist_raw.json data/debug_argentina_sofascore_eventos.json
        }
        if ($okUk) {
            Rodar "merge Reino Unido" @("reino_unido_comum.py", "--raw", "data/debug_uk_sofascore_raw.json", "--raw-historico", "data/debug_uk_sofascore_hist_raw.json") | Out-Null
            git add data/reino_unido/ data/debug_uk_sofascore_raw.json data/debug_uk_sofascore_hist_raw.json data/debug_uk_sofascore_eventos.json
        }

        git diff --cached --quiet
        if ($LASTEXITCODE -eq 0) { Write-Output "Sem mudancas para commitar"; break }

        git commit -q -m "Atualiza jogos SofaScore (Argentina + Reino Unido) - rodada local"
        if ($SemPush) { Write-Output "[-SemPush] commit local feito, sem push"; break }

        git push -q origin HEAD:main
        if ($LASTEXITCODE -eq 0) { Write-Output "Push OK na tentativa $tentativa"; break }
        Write-Output "Push falhou (tentativa $tentativa), tentando de novo..."
        Start-Sleep -Seconds (Get-Random -Minimum 5 -Maximum 15)
    }
}
finally {
    Stop-Transcript | Out-Null
}
