# 待确认：真实 SYSTEM SID 的 files/db 映射、setuid 与 NTFS 权限。
# 歧义：Server 2022 的结果不代表 Win7 SP1。
# 后续研究：smbd 回环协议和真实服务生命周期。
# 潜在优化：复用现有 Setup 研究根，不重新编译。
# 风险：仅 GitHub-hosted 临时 Runner；仅实际 SYSTEM 映射 UID0；不提升普通账户。
# 验证重点：SYSTEM SID、UID0、受限 smbshare、passdb、NTFS 写入及清理。
param([Parameter(Mandatory=$true)][string]$Root,
      [Parameter(Mandatory=$true)][string]$Report)
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'Only a disposable GitHub-hosted Windows runner is supported'
}
$rootPath = [IO.Path]::GetFullPath($Root)
$tempPath = [IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\') + '\'
if (-not $rootPath.StartsWith($tempPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Research root must be inside RUNNER_TEMP'
}
if (Get-LocalUser -Name smbshare -ErrorAction SilentlyContinue) {
    throw 'Refusing to alter an existing smbshare account'
}
$task = "SambaIdentity-$([Guid]::NewGuid().ToString('N'))"
$work = Join-Path $env:RUNNER_TEMP $task
$created = $false
$registered = $false
New-Item -ItemType Directory -Path $work | Out-Null
# Limit task script and result access to SYSTEM and administrators.
& icacls.exe $work /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot protect task directory' }
try {
    $secret = ConvertTo-SecureString ("aA1!" + [Guid]::NewGuid().ToString('N')) -AsPlainText -Force
    $account = New-LocalUser -Name smbshare -Password $secret -Description 'Disposable Samba CI identity'
    $created = $true
    $sid = $account.SID.Value
    $share = Join-Path $rootPath 'smb'
    & icacls.exe $share /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' ("*"+$sid+":(OI)(CI)M") | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot set isolated share ACL' }
    $private = Join-Path $rootPath 'var/lib/samba/private'
    & icacls.exe $private /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot protect passdb directory' }
    $shell = @'
set -euo pipefail
export PATH=/usr/bin:/bin
# Native wrapper verifies SYSTEM before invoking this script.
system=$(getent passwd 18)
[[ $(id -u) == 18 && "$system" == *S-1-5-18* ]]
account=$(getent passwd smbshare)
[[ -n "$account" && "$account" != *S-1-5-18* ]]
printf 'Native SYSTEM uid=%s; share account uid=%s\n' "$(id -u)" "$(cut -d: -f3 <<< "$account")"
# A fresh process tree is required to read the new files/db mapping.
# Only the genuine SYSTEM SID is mapped to uid/gid 0 in this isolated root.
group=$(getent group 18)
[[ "$group" == *S-1-5-18* ]]
printf '%s\n' "$system" | awk -F: 'BEGIN {OFS=":"} {$1="root";$3=0;$4=0;print}' > /etc/passwd
printf '%s\n' "$account" >> /etc/passwd
printf '%s\n' "$group" | awk -F: 'BEGIN {OFS=":"} {$1="root";$3=0;print}' > /etc/group
printf 'passwd: files db\ngroup: files db\n' > /etc/nsswitch.conf
'@
    $second = @'
set -euo pipefail
export PATH=/usr/bin:/bin
id
[[ $(id -u) == 0 && $(id -g) == 0 ]]
[[ $(getent passwd 0) == *S-1-5-18* ]]
entry=$(getent passwd smbshare)
uid=$(cut -d: -f3 <<< "$entry")
gid=$(cut -d: -f4 <<< "$entry")
[[ "$uid" =~ ^[0-9]+$ && "$uid" != 0 && "$uid" != 18 ]]
printf 'SYSTEM mapping PASS; smbshare uid=%s gid=%s\n' "$uid" "$gid"
secret=$(head -c 32 /dev/urandom | base64 -w0)
printf '%s\n%s\n' "$secret" "$secret" | smbpasswd -L -s -a -c /etc/samba/smb.conf smbshare
unset secret
test -s /var/lib/samba/private/passdb.tdb
printf 'Local passdb initialization PASS\n'
# A separate child permanently drops credentials before attempting local NTFS I/O.
perl -MPOSIX -e '
    my ($uid, $gid) = @ARGV;
    POSIX::setgid($gid) == 0 or die "setgid: $!";
    POSIX::setuid($uid) == 0 or die "setuid: $!";
    $< == $uid && $> == $uid or die "wrong UID";
    open(my $out, ">", "/smb/identity-probe.txt") or die "share write: $!";
    print $out "identity probe\n";
    close($out) or die "close: $!";
    rename("/smb/identity-probe.txt", "/smb/identity-probe-renamed.txt") or die "rename: $!";
    unlink("/smb/identity-probe-renamed.txt") or die "unlink: $!";
    if (open(my $db, "<", "/var/lib/samba/private/passdb.tdb")) {
        close($db);
        die "restricted account read protected passdb";
    }
    print "Restricted NTFS write/rename/delete and private deny PASS\n";
' "$uid" "$gid"
'@
    $firstPath = Join-Path $work 'map.sh'
    $secondPath = Join-Path $work 'probe.sh'
    [IO.File]::WriteAllText($firstPath, ($shell -replace "\x0d\x0a", "\x0a"), [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($secondPath, ($second -replace "\x0d\x0a", "\x0a"), [Text.UTF8Encoding]::new($false))
    $wrapper = @'
param($Root,$Work)
$ErrorActionPreference = 'Stop'
$rc = 1
try {
    if ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne 'S-1-5-18') {
        throw 'Not the real SYSTEM token'
    }
    $bash = Join-Path $Root 'bin/bash.exe'
    $env:PATH = "$Root\bin;$env:SystemRoot\System32;$env:SystemRoot"
    foreach ($file in @('map.sh','probe.sh')) {
        $script = (Join-Path $Work $file).Replace('\','/')
        & $bash --noprofile --norc $script *>> (Join-Path $Work 'result.txt')
        if ($LASTEXITCODE -ne 0) { throw "$file failed ($LASTEXITCODE)" }
    }
    $rc = 0
} catch {
    $_ | Out-String | Add-Content (Join-Path $Work 'result.txt')
} finally {
    Set-Content -LiteralPath (Join-Path $Work 'exit.txt') -Value $rc
}
exit $rc
'@
    $wrapperPath = Join-Path $work 'run.ps1'
    Set-Content -LiteralPath $wrapperPath -Value $wrapper -Encoding utf8
    $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -NonInteractive -File "{0}" -Root "{1}" -Work "{2}"' -f $wrapperPath,$rootPath,$work)
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
    Register-ScheduledTask -TaskName $task -Action $action -Principal $principal -Settings $settings | Out-Null
    $registered = $true
    Start-ScheduledTask -TaskName $task
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    $exitFile = Join-Path $work 'exit.txt'
    while (-not (Test-Path -LiteralPath $exitFile) -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 2
    }
    $result = Join-Path $work 'result.txt'
    if (Test-Path -LiteralPath $result) { Get-Content -LiteralPath $result | Tee-Object -FilePath $Report }
    if (-not (Test-Path -LiteralPath $exitFile)) { throw 'SYSTEM identity probe timed out' }
    if ((Get-Content -LiteralPath $exitFile -Raw).Trim() -ne '0') { throw 'SYSTEM identity probe failed' }
} finally {
    if ($registered) {
        Stop-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $task -Confirm:$false
    }
    if ($created) { Remove-LocalUser -Name smbshare }
}
