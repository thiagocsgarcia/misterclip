#!/usr/bin/env bash
# Particiona o 2º SSD da andes: metade para o Windows (preservado, redimensionado)
# e metade para espaço de apoio (ext4, /mnt/apoio). Só altera o disco após "SIM".
# Uso (na andes):  sudo bash ~/particionar-ssd2.sh
set -euo pipefail

DISK=/dev/nvme1n1
WIN=${DISK}p2
APOIO=${DISK}p3
USR=${SUDO_USER:-aries}

[ "$(id -u)" = 0 ] || { echo "Rode com sudo."; exit 1; }
MODEL=$(lsblk -dno MODEL "$DISK" | xargs)
[[ "$MODEL" == WDC* ]] || { echo "Disco inesperado ($MODEL). Abortando."; exit 1; }
if lsblk -no MOUNTPOINT "$DISK" | grep -q .; then echo "Há partição montada em $DISK. Abortando."; exit 1; fi
[ ! -e "$APOIO" ] || { echo "$APOIO já existe. Abortando."; exit 1; }

echo "== Tabela de partições atual"; sgdisk -p "$DISK"
echo; echo "== Conteúdo do Windows (somente leitura)"
mkdir -p /mnt/ssd2-ro
if mount -t ntfs3 -o ro "$WIN" /mnt/ssd2-ro 2>/dev/null || mount -t ntfs-3g -o ro "$WIN" /mnt/ssd2-ro 2>/dev/null; then
  ls /mnt/ssd2-ro | head -n 25; df -h /mnt/ssd2-ro | tail -n1
  [ -d /mnt/ssd2-ro/Windows ] && echo ">> Há uma instalação do Windows nesta partição." || echo ">> NÃO há pasta Windows: pode ser só dados."
  umount /mnt/ssd2-ro
else echo "(não consegui montar somente leitura: NTFS pode estar sujo/hibernado)"; fi

echo; echo "== Verificação do NTFS"
INFO=$(ntfsresize --info "$WIN" 2>&1) || { echo "$INFO"; echo "NTFS não está limpo (provável hibernação/inicialização rápida do Windows). Abortando sem alterar nada."; exit 1; }
echo "$INFO" | tail -n 8
MIN_BYTES=$(echo "$INFO" | grep -oP 'You might resize at \K[0-9]+')
MIN_MIB=$(( MIN_BYTES / 1048576 ))

TOTAL_MIB=$(( $(blockdev --getsize64 "$DISK") / 1048576 ))
HALF_MIB=$(( TOTAL_MIB / 2 ))
START_MIB=$(( $(cat /sys/class/block/nvme1n1p2/start) * 512 / 1048576 ))
FS_MIB=$(( HALF_MIB - START_MIB - 16 ))
NEED_MIB=$(( MIN_MIB * 105 / 100 + 1024 ))
echo; echo "Disco: ${TOTAL_MIB} MiB | Windows ficará com ~${FS_MIB} MiB | mínimo seguro necessário: ${NEED_MIB} MiB"
if [ "$FS_MIB" -lt "$NEED_MIB" ]; then
  echo "O Windows ocupa mais que a metade do disco. NÃO redimensionei. Para continuar seria preciso formatar: decida com o Thiago."
  exit 2
fi

echo; read -r -p "Redimensionar o NTFS (preservando o Windows) e criar a partição de apoio? Digite SIM: " R
[ "$R" = "SIM" ] || { echo "Cancelado. Nada foi alterado."; exit 0; }

BK=/root/nvme1n1-gpt-$(date +%F-%H%M).bak
sgdisk --backup="$BK" "$DISK" && echo "Backup da tabela GPT: $BK"

echo "== 1/5 Teste a seco do redimensionamento"
ntfsresize --no-action --size $(( FS_MIB * 1048576 )) "$WIN" | tail -n 3
echo "== 2/5 Redimensionando o sistema de arquivos NTFS"
echo y | ntfsresize --size $(( FS_MIB * 1048576 )) "$WIN"

echo "== 3/5 Ajustando a partição do Windows (mantém GUID e tipo)"
UGUID=$(sgdisk -i 2 "$DISK" | awk '/Partition unique GUID/ {print $4}')
TGUID=$(sgdisk -i 2 "$DISK" | awk '/Partition GUID code/ {print $4}')
PNAME=$(sgdisk -i 2 "$DISK" | sed -n "s/^Partition name: '\(.*\)'/\1/p")
FIRST=$(sgdisk -i 2 "$DISK" | awk '/First sector/ {print $3}')
LAST=$(( HALF_MIB * 2048 - 1 ))
sgdisk -d 2 -n 2:${FIRST}:${LAST} -t 2:${TGUID} -u 2:${UGUID} -c 2:"${PNAME}" "$DISK"

echo "== 4/5 Criando partição de apoio (ext4)"
sgdisk -n 3:$(( HALF_MIB * 2048 )):0 -t 3:8300 -c 3:apoio "$DISK"
partprobe "$DISK"; udevadm settle; sleep 2
mkfs.ext4 -F -m 0 -L apoio "$APOIO"
UUID=$(blkid -s UUID -o value "$APOIO")
mkdir -p /mnt/apoio
grep -q "$UUID" /etc/fstab || echo "UUID=$UUID /mnt/apoio ext4 defaults,noatime,nofail 0 2" >> /etc/fstab
systemctl daemon-reload; mount /mnt/apoio
mkdir -p /mnt/apoio/misterclip /mnt/apoio/audioglifo
chown -R "$USR":"$USR" /mnt/apoio
df -h /mnt/apoio | tail -n1

echo "== 5/5 Windows no menu de boot (GRUB)"
cp /etc/default/grub /etc/default/grub.bak-$(date +%F)
sed -i '/^#\?GRUB_DISABLE_OS_PROBER/d; /^GRUB_TIMEOUT_STYLE=/d; /^GRUB_TIMEOUT=/d' /etc/default/grub
printf 'GRUB_DISABLE_OS_PROBER=false\nGRUB_TIMEOUT_STYLE=menu\nGRUB_TIMEOUT=5\n' >> /etc/default/grub
update-grub 2>&1 | tail -n 8
grep -i -m3 "windows" /boot/grub/grub.cfg || echo "(Windows não apareceu no GRUB: verifique)"

echo; echo "== Conferência final"
ntfsresize --info "$WIN" | tail -n 3
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT "$DISK"
echo "Pronto. Reinicie para ver o menu com Ubuntu e Windows."
