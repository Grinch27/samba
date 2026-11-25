#!/usr/bin/env bash
# 待确认的关键需求：Win7 上是否需要同时支持 SMB3 加密和共享枚举。
# 歧义：Linux 对照签名与认证通过仍不代表 Win7 上的 NTFS 权限和服务已验证。
# 后续研究：在 Cygwin 验证同一共享的访问路径和 NTFS 权限。
# 潜在优化：端口及测试数据稳定后再扩展并发和锁测试。
# 风险：测试需要 sudo，用于回环监听、身份切换及测试目录清理。
# 验证重点：强制 SMB 2.1 签名，核对正确密码、错误密码及文件内容。
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]] || (( EUID == 0 )); then
  printf 'Usage as a non-root user with sudo: %s <samba-bin> <evidence-directory> [SMB2_10|SMB3_11]\n' "$0" >&2
  exit 2
fi

dialect=${3:-SMB2_10}
case "$dialect" in SMB2_10|SMB3_11) ;; *) exit 2 ;; esac
export LC_ALL=C.UTF-8
bin=$(realpath -e -- "$1")
evidence=$(realpath -e -- "$2")
for tool in smbd smbpasswd smbclient testparm; do
  test -x "$bin/$tool"
done
sudo -n true

scratch=$(mktemp -d)
server_pid=
relay_pid=
relay6_pid=
ipv6_added=false
ipv6_source=fd00:5a6b:25::2
cleanup() {
  if [[ -n $relay6_pid ]]; then
    kill -TERM "$relay6_pid" 2>/dev/null || true
    wait "$relay6_pid" 2>/dev/null || true
  fi
  if [[ -n $relay_pid ]]; then
    kill -TERM "$relay_pid" 2>/dev/null || true
    wait "$relay_pid" 2>/dev/null || true
  fi
  if [[ -n $server_pid ]]; then
    kill -TERM "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  if [[ $ipv6_added == true ]]; then
    sudo -n ip -6 addr del "$ipv6_source/128" dev lo
  fi
  sudo -n rm -rf -- "$scratch"
}
trap cleanup EXIT
cd -- "$scratch"
umask 077
mkdir share private state cache lock pid rpc
# Allow traversal of the test-only share by a distinct existing unprivileged user.
chmod 0711 "$scratch"
chmod 0755 "$scratch/share"
export SAMBA_PORTABLE_ROOT="$scratch"
reader=nobody
id "$reader" >/dev/null
test "$reader" != "$(id -un)"
config="$scratch/smb.conf"
user=$(id -un)
port=14456
[[ $dialect == SMB3_11 ]] && port=14457
cat > "$config" <<EOF
[global]
server role = standalone server
netbios name = SAMBACONTROL
workgroup = WORKGROUP
security = user
passdb backend = tdbsam
map to guest = Never
null passwords = no
hosts allow = 127.0.0.1 ::1
hosts deny = ALL
hostname lookups = no
ntlm auth = ntlmv2-only
server smb encrypt = if_required
interfaces = 127.0.0.1/8 ::1
bind interfaces only = yes
smb ports = $port
disable netbios = yes
server min protocol = $dialect
server max protocol = $dialect
server signing = mandatory
server multi channel support = no
rpc start on demand helpers = no
load printers = no
disable spoolss = yes
private dir = %\$(SAMBA_PORTABLE_ROOT)/private
state directory = $scratch/state
cache directory = $scratch/cache
lock directory = $scratch/lock
pid directory = $scratch/pid
ncalrpc dir = $scratch/rpc

[data]
path = $scratch/share
valid users = $user $reader
read only = yes
write list = $user
guest ok = no

[blocked]
path = $scratch/share
valid users = SAMBA_NO_SUCH_ACCOUNT
read only = yes
guest ok = no
EOF

"$bin/smbd" --version | tee "$evidence/version.txt"
"$bin/testparm" -s "$config" > "$evidence/testparm.txt" 2>&1
secret=$(openssl rand -hex 20)
printf '%s\n%s\n' "$secret" "$secret" | sudo -n --preserve-env=SAMBA_PORTABLE_ROOT "$bin/smbpasswd" -s -a -c "$config" "$user"
printf 'username = %s\npassword = %s\n' "$user" "$secret" > auth-good
printf 'username = %s\npassword = wrong-%s\n' "$user" "$secret" > auth-bad
reader_secret=$(openssl rand -hex 20)
printf '%s\n%s\n' "$reader_secret" "$reader_secret" | sudo -n --preserve-env=SAMBA_PORTABLE_ROOT "$bin/smbpasswd" -s -a -c "$config" "$reader"
printf 'username = %s\npassword = %s\n' "$reader" "$reader_secret" > auth-reader
printf 'username = %s\npassword = %s\n' "$reader" "$secret" > auth-reader-wrong
unset secret reader_secret
sudo -n test -f "$scratch/private/passdb.tdb"

sudo -n --preserve-env=SAMBA_PORTABLE_ROOT timeout --kill-after=5s 85s "$bin/smbd" --foreground --no-process-group \
  --debug-stdout --configfile="$config" > "$evidence/server.log" 2>&1 &
server_pid=$!

client() {
  "$bin/smbclient" //127.0.0.1/data --configfile="$config" --port="$port" \
    --timeout=3 --client-protection=sign --max-protocol="$dialect" "$@"
}

connected=false
for attempt in {1..15}; do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    cat "$evidence/server.log" >&2
    exit 1
  fi
  if client -A auth-good -c ls > "$evidence/connect.txt" 2>&1; then
    connected=true
    break
  fi
  sleep 1
done
if [[ $connected != true ]]; then
  cat "$evidence/connect.txt" "$evidence/server.log" >&2
  exit 1
fi
printf 'Direct share connection with mandatory %s signing: PASS\n' "$dialect" | tee "$evidence/results.txt"

head -c 1048576 /dev/urandom > upload.bin
client -A auth-good -c 'put upload.bin "共享.bin"' > "$evidence/upload.txt" 2>&1
cmp upload.bin share/共享.bin
client -A auth-good -c 'get "共享.bin" download.bin' > "$evidence/download.txt" 2>&1
cmp upload.bin download.bin
client -A auth-good -c 'rename "共享.bin" changed.bin' > "$evidence/rename.txt" 2>&1
test ! -e share/共享.bin
cmp upload.bin share/changed.bin
client -A auth-good -c 'del changed.bin' > "$evidence/delete.txt" 2>&1
test ! -e share/changed.bin
printf 'Upload, download, byte comparison, rename and delete: PASS\n' | tee -a "$evidence/results.txt"

if client -A auth-bad -c ls > "$evidence/deny.txt" 2>&1; then
  printf 'The server accepted the wrong password.\n' >&2
  exit 1
fi
grep -Fq NT_STATUS_LOGON_FAILURE "$evidence/deny.txt"
printf 'Wrong password rejected with NT_STATUS_LOGON_FAILURE: PASS\n' | tee -a "$evidence/results.txt"

# The relay opens its upstream connection from 127.0.0.2, not the allowed
# 127.0.0.1. Its listener is loopback-only; credentials are not logged.
relay_port=$((port + 10))
socat "TCP-LISTEN:$relay_port,bind=127.0.0.1,reuseaddr,fork" \
  "TCP:127.0.0.1:$port,bind=127.0.0.2" > "$evidence/relay.log" 2>&1 &
relay_pid=$!
for attempt in {1..10}; do
  if ss -H -ltn "sport = :$relay_port" | grep -q .; then
    break
  fi
  kill -0 "$relay_pid"
  sleep 1
done
ss -H -ltn "sport = :$relay_port" | grep -q .
if "$bin/smbclient" //127.0.0.1/data --configfile="$config" --port="$relay_port" \
    --timeout=3 --client-protection=sign --max-protocol="$dialect" \
    -A auth-good -c ls > "$evidence/ip-deny.txt" 2>&1; then
  echo "Non-whitelisted source accepted" >&2
  exit 1
fi
grep -Ei 'denied connection from.*127\.0\.0\.2|connection denied.*127\.0\.0\.2|127\.0\.0\.2.*(denied|not allowed)' "$evidence/server.log"
printf 'Non-whitelisted source 127.0.0.2 rejected: PASS\n' | tee -a "$evidence/results.txt"

if client -N -U '%' -c ls > "$evidence/guest-deny.txt" 2>&1; then
  echo "Anonymous connection accepted" >&2
  exit 1
fi
printf 'Anonymous access rejected: PASS\n' | tee -a "$evidence/results.txt"

if "$bin/smbclient" //127.0.0.1/blocked --configfile="$config" --port="$port" \
    --timeout=3 --client-protection=sign --max-protocol="$dialect" \
    -A auth-good -c ls > "$evidence/user-deny.txt" 2>&1; then
  echo "Account not in valid users accepted" >&2
  exit 1
fi
grep -Fq NT_STATUS_ACCESS_DENIED "$evidence/user-deny.txt"
printf 'Authenticated but unauthorized account rejected: PASS\n' | tee -a "$evidence/results.txt"

# Read-only account: distinct valid credentials, actual successful read, denied write.
printf 'read-only proof\n' > "$scratch/share/read-proof.txt"
chmod 0644 "$scratch/share/read-proof.txt"
client -A auth-reader -c 'get read-proof.txt reader-copy.txt' > "$evidence/reader-read.txt" 2>&1
cmp "$scratch/share/read-proof.txt" reader-copy.txt
if client -A auth-reader -c 'put upload.bin reader-write.bin' > "$evidence/reader-write.txt" 2>&1; then
  echo "Read-only account unexpectedly wrote a file" >&2
  exit 1
fi
grep -Fq NT_STATUS_ACCESS_DENIED "$evidence/reader-write.txt"
test ! -e "$scratch/share/reader-write.bin"
if client -A auth-reader-wrong -c ls > "$evidence/reader-wrong.txt" 2>&1; then
  echo "Writer password accepted for distinct reader account" >&2
  exit 1
fi
grep -Fq NT_STATUS_LOGON_FAILURE "$evidence/reader-wrong.txt"
printf 'Distinct reader password and read-only share authorization: PASS\n' | tee -a "$evidence/results.txt"

"$bin/smbclient" //localhost/data -I ::1 --configfile="$config" --port="$port" \
  --timeout=3 --client-protection=sign --max-protocol="$dialect" \
  -A auth-good -c ls > "$evidence/ipv6-allow.txt" 2>&1
"$bin/testparm" -s "$config" outside 2001:db8::123 > "$evidence/ipv6-deny-config.txt" 2>&1
grep -Fq 'Deny connection from outside (2001:db8::123) to data' "$evidence/ipv6-deny-config.txt"
printf 'IPv6 loopback connection and non-allowlisted IPv6 configuration decision: PASS\n' | tee -a "$evidence/results.txt"

# Runner-local IPv6 address: no external listener or route is introduced.
sudo -n ip -6 addr add "$ipv6_source/128" dev lo nodad
ipv6_added=true
relay6_port=$((port + 20))
socat "TCP4-LISTEN:$relay6_port,bind=127.0.0.1,reuseaddr,fork" \
  "TCP6:[::1]:$port,bind=[$ipv6_source]" > "$evidence/relay6.log" 2>&1 &
relay6_pid=$!
for attempt in {1..10}; do
  if ss -H -ltn "sport = :$relay6_port" | grep -q .; then
    break
  fi
  kill -0 "$relay6_pid"
  sleep 1
done
ss -H -ltn "sport = :$relay6_port" | grep -q .
if "$bin/smbclient" //127.0.0.1/data --configfile="$config" --port="$relay6_port" \
    --timeout=3 --client-protection=sign --max-protocol="$dialect" \
    -A auth-good -c ls > "$evidence/ipv6-deny.txt" 2>&1; then
  echo "Non-whitelisted IPv6 source accepted" >&2
  exit 1
fi
grep -Ei "denied connection from.*$ipv6_source|connection denied.*$ipv6_source|$ipv6_source.*(denied|not allowed)" "$evidence/server.log"
printf 'Non-whitelisted IPv6 source rejected by server: PASS\n' | tee -a "$evidence/results.txt"
