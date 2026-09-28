<#
Deploy the last commit on a branch to the shared VM and check /health.

Run from anywhere: .\scripts\deploy.ps1
The VM's address and the SSH key come from scripts\deploy.local.psd1, which is not in git:
copy deploy.local.example.psd1 to it and fill it in (README, "Deploy").
Uncommitted changes are not deployed; commit first. Two people deploying overwrite each
other's code on the VM, so pull before you deploy.
If the SSH key has a passphrase you are asked for it twice (upload, then restart),
unless the key is loaded in ssh-agent.
Only ~/taskly on the VM changes. Caddy (~/proxy), Reels and any other app keep running,
and ~/taskly/data (the SQLite file) and ~/taskly/.env are never touched.
#>
param(
    [string]$Branch = "main",
    [string]$Config = (Join-Path $PSScriptRoot "deploy.local.psd1")
)

$ErrorActionPreference = "Stop"

function Invoke-Native([string]$What, [scriptblock]$Command) {
    Write-Host "==> $What"
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$What failed (exit code $LASTEXITCODE)" }
}

if (-not (Test-Path $Config)) {
    throw "No $Config. Copy scripts\deploy.local.example.psd1 to it and fill it in."
}
$settings = Import-PowerShellDataFile $Config
foreach ($name in "VmHost", "Site", "KeyFile", "User") {
    if (-not $settings[$name]) { throw "$name is missing in $Config" }
}
$keyFile = $settings.KeyFile -replace '^~', $HOME
if (-not (Test-Path $keyFile)) { throw "SSH key not found: $keyFile" }
$site = $settings.Site
$target = "$($settings.User)@$($settings.VmHost)"

$repo = Split-Path -Parent $PSScriptRoot
$archive = Join-Path $env:TEMP "taskly.tar.gz"

Push-Location $repo
try {
    if (git status --porcelain) {
        Write-Warning "You have uncommitted changes. They will NOT be deployed; only the last commit on '$Branch' is."
    }
    $commit = git log -1 --format="%h %s" $Branch
    if ($LASTEXITCODE -ne 0) { throw "No branch '$Branch' with a commit to deploy." }
    Write-Host "Deploying $Branch ($commit) to $site"

    Invoke-Native "Packing $Branch" { git archive --format=tar.gz -o $archive $Branch }
    Invoke-Native "Uploading to $($settings.VmHost)" { scp -i $keyFile $archive "${target}:~/taskly.tar.gz" }
    # The "web" network is shared with Caddy and the other apps; it's created if missing,
    # since compose won't start without it. --remove-orphans deletes containers of services
    # no longer in docker-compose.yml. The prune, in the same ssh call so there's no second
    # passphrase prompt, removes only untagged images nothing uses: the one this build replaced.
    Invoke-Native "Rebuilding and restarting on the VM, then removing the old image" {
        ssh -i $keyFile $target "mkdir -p ~/taskly && cd ~/taskly && tar -xzf ~/taskly.tar.gz && rm ~/taskly.tar.gz && (docker network inspect web >/dev/null 2>&1 || docker network create web) && docker compose up -d --build --remove-orphans && docker image prune -f"
    }
}
finally {
    Remove-Item $archive -ErrorAction SilentlyContinue
    Pop-Location
}

# Windows PowerShell 5.1 does not offer TLS 1.2 by default.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Write-Host "==> Waiting for https://$site/health"
for ($i = 1; $i -le 12; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "https://$site/health" -TimeoutSec 10
        if ($health.status -eq "ok") {
            Write-Host "Deployed. status=$($health.status)" -ForegroundColor Green
            exit 0
        }
    }
    catch { }
    Start-Sleep -Seconds 5
}
Write-Error ("https://$site/health did not answer ok within a minute. On the VM, 'curl localhost:8001/health' " +
    "checks the app itself: if that works, the site's block in ~/proxy/Caddyfile is missing or wrong (README, 'First deploy'). " +
    "App logs: ssh -i $keyFile $target 'cd ~/taskly && docker compose logs --tail 50 app'")
exit 1
