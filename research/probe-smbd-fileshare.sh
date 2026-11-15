#!/usr/bin/env bash
# 待确认的关键需求：Win7 上是否需要同时支持 SMB3 加密和共享枚举。
# 歧义：此流程测量 Linux 对照，Win7 上的进程及身份语义待单独检查。
# 后续研究：在 Cygwin 验证同一共享的访问路径和 NTFS 权限。
# 潜在优化：端口及测试数据稳定后再扩展并发和锁测试。
# 风险：测试需要 sudo，用于回环监听、身份切换及测试目录清理。
# 验证重点：强制 SMB 2.1 签名，核对正确密码、错误密码及文件内容。
set -euo pipefail

if [[ $# != 2 ]] || (( EUID == 0 )); then
  printf 'Usage as a non-root user with sudo: %s <samba-bin> <evidence-directory>\n' "$0" >&2
  exit 2
fi

export LC_ALL=C.UTF-8
bin=$(realpath -e -- "$1")
evidence=$(realpath -e -- "$2")
for tool in smbd smbpasswd smbclient testparm; do
  test -x "$bin/$tool"
done
sudo -n true

scratch=$(mktemp -d)
server_pid=
cleanup() {
  if [[ -n $server_pid ]]; then
    kill -TERM "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  sudo -n rm -rf -- "$scratch"
}
trap cleanup EXIT
cd -- "$scratch"
umask 077
mkdir share private state cache lock pid rpc
config="$scratch/smb.conf"
port=14456
cat > "$config" <<EOF
[global]
server role = standalone server
netbios name = SAMBACONTROL
workgroup = WORKGROUP
security = user
passdb backend = tdbsam
map to guest = Never
interfaces = 127.0.0.1/8
bind interfaces only = yes
smb ports = $port
disable netbios = yes
server min protocol = SMB2_10
server max protocol = SMB2_10
server signing = mandatory
server multi channel support = no
rpc start on demand helpers = no
load printers = no
disable spoolss = yes
private dir = $scratch/private
state directory = $scratch/state
cache directory = $scratch/cache
lock directory = $scratch/lock
pid directory = $scratch/pid
ncalrpc dir = $scratch/rpc

[data]
path = $scratch/share
read only = no
guest ok = no
EOF

"$bin/smbd" --version | tee "$evidence/version.txt"
"$bin/testparm" -s "$config" > "$evidence/testparm.txt" 2>&1
user=$(id -un)
secret=$(openssl rand -hex 20)
printf '%s\n%s\n' "$secret" "$secret" | sudo -n "$bin/smbpasswd" -s -a -c "$config" "$user"
printf 'username = %s\npassword = %s\n' "$user" "$secret" > auth-good
printf 'username = %s\npassword = wrong-%s\n' "$user" "$secret" > auth-bad
unset secret

sudo -n timeout --kill-after=5s 85s "$bin/smbd" --foreground --no-process-group \
  --debug-stdout --configfile="$config" > "$evidence/server.log" 2>&1 &
server_pid=$!

client() {
  "$bin/smbclient" //127.0.0.1/data --configfile="$config" --port="$port" \
    --timeout=3 --client-protection=sign "$@"
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
printf 'Direct share connection with mandatory SMB 2.1 signing: PASS\n' | tee "$evidence/results.txt"

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
