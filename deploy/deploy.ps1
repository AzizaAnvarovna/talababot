# Commit qilingan kodni serverga yuklaydi va deploy/setup.sh ni ishga tushiradi.
# .\deploy\deploy.ps1 -Server root@1.2.3.4 -Domain bot.example.uz -Email you@example.com
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [Parameter(Mandatory = $true)][string]$Domain,
    [Parameter(Mandatory = $true)][string]$Email
)
$ErrorActionPreference = 'Stop'

function Invoke-Checked {
    param([string]$File, [string[]]$Arguments)
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit code $LASTEXITCODE" }
}

if (git status --porcelain) { throw 'Commit qilinmagan o''zgarishlar bor. Avval commit qiling.' }

$archive = Join-Path $env:TEMP 'talababot-release.tar.gz'
$tokenFile = Join-Path $env:TEMP 'talababot.token'
try {
    Invoke-Checked git @('archive', '--format=tar.gz', '-o', $archive, 'HEAD')

    $tokenLine = Select-String -Path .env -Pattern '^TELEGRAM_BOT_TOKEN=(.+)$'
    if (-not $tokenLine) { throw '.env faylida TELEGRAM_BOT_TOKEN yo''q.' }
    [System.IO.File]::WriteAllText($tokenFile, $tokenLine.Matches[0].Groups[1].Value)

    Invoke-Checked scp @($archive, "${Server}:/root/talababot-release.tar.gz")
    Invoke-Checked scp @($tokenFile, "${Server}:/root/talababot.token")
    Invoke-Checked ssh @($Server, 'chmod 600 /root/talababot.token && mkdir -p /opt/talababot && tar -xzf /root/talababot-release.tar.gz -C /opt/talababot && rm /root/talababot-release.tar.gz')
    Invoke-Checked ssh @($Server, "bash /opt/talababot/deploy/setup.sh $Domain $Email")
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $archive, $tokenFile
}
