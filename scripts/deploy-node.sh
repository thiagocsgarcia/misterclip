#!/usr/bin/env bash
# Atualiza o nó MisterClip na andes (código + imagem + contêiner). Preserva dados, modelos e o token.
# Uso: scripts/deploy-node.sh aries@100.70.97.18 [--recreate-comfy]
set -euo pipefail
HOST=${1:?uso: scripts/deploy-node.sh usuario@host [--recreate-comfy]}
RECREATE=${2:-}
# flags do ComfyUI (medidas na andes: --cache-none dobrava o tempo de cada imagem)
COMFY_FLAGS=${COMFY_FLAGS:---disable-pinned-memory --mmap-torch-files}
cd "$(dirname "$0")/.."

# nunca enviar uma interface quebrada: um parêntese a mais deixa a tela em branco
if command -v node >/dev/null; then
  for f in web/app.js web/canal.js web/clipe.js web/plano.js web/prompts.js web/youtube.js web/agenda-mes.js; do
    node --input-type=module --check < "$f" || { echo "ERRO: $f tem erro de sintaxe; deploy cancelado"; exit 1; }
  done
fi

rsync -az --delete \
  --exclude .env --exclude data --exclude tests --exclude 'teste-*' --exclude scripts --exclude __pycache__ \
  --exclude .pytest_cache --exclude .git --exclude Dockerfile --exclude compose.yaml \
  ./ "$HOST:docker-projects/misterclip/"

ssh "$HOST" RECREATE="$RECREATE" COMFY_FLAGS="'$COMFY_FLAGS'" bash -s <<'REMOTE'
set -euo pipefail
cd ~/docker-projects/misterclip
APOIO=/mnt/apoio/misterclip
mkdir -p "$APOIO/data"

# token de acesso (gerado uma vez; nunca é impresso)
if [ ! -f .env ]; then
  ( umask 077; printf 'MC_TOKEN=%s\n' "$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 32)" > .env )
  echo ".env criado com um token novo (arquivo ~/docker-projects/misterclip/.env na andes)"
fi
chmod 600 .env

docker build -q -f Dockerfile.andes -t misterclip-node:latest . >/dev/null
echo "imagem misterclip-node construída"

# ComfyUI (imagens e clipes): só cria se não existir (ou com --recreate-comfy); não derruba jobs em andamento
[ "$RECREATE" = "--recreate-comfy" ] && docker rm -f mc-comfy >/dev/null 2>&1 || true
if ! docker ps -a --format '{{.Names}}' | grep -qx mc-comfy; then
  T=~/docker-projects/misterclip-test
  docker run -d --name mc-comfy --restart unless-stopped --device nvidia.com/gpu=all --network host \
    -u "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/work/pylibs \
    -v "$T":/work -v "$APOIO/models":/work/models -w /work/ComfyUI \
    --entrypoint python misterclip-comfy:test main.py --listen 127.0.0.1 --port 8188 \
    --extra-model-paths-config /work/extra.yaml \
    $(eval echo $COMFY_FLAGS) >/dev/null
  echo "mc-comfy criado"
elif ! docker ps --format '{{.Names}}' | grep -qx mc-comfy; then
  docker start mc-comfy >/dev/null; echo "mc-comfy iniciado"
fi

docker rm -f misterclip >/dev/null 2>&1 || true
docker run -d --name misterclip --restart unless-stopped --network host --device nvidia.com/gpu=all \
  -u "$(id -u):$(id -g)" --env-file .env \
  -e MC_MODE=real -e MC_DATA=/data -e MC_MODELS=/models -e HOME=/tmp -e HF_HUB_OFFLINE=1 \
  -e MC_COMFY_URL=http://127.0.0.1:8188 -e MC_OLLAMA_URL=http://127.0.0.1:11434 -e MC_LLM_MODEL=qwen3:14b \
  -e PYTHONPATH=/opt/pylibs-voz:/opt/pylibs-stub \
  -v "$APOIO/data":/data -v "$APOIO/models":/models:ro \
  -v "$APOIO/pylibs-voz":/opt/pylibs-voz:ro -v "$APOIO/pylibs-stub":/opt/pylibs-stub:ro \
  misterclip-node:latest >/dev/null
# proxy da porta 80 -> URL curta http://misterclip.nord (apelido da andes na Meshnet: nordvpn meshnet set nickname misterclip)
docker rm -f mc-proxy >/dev/null 2>&1 || true
docker run -d --name mc-proxy --restart unless-stopped --network host \
  -v "$PWD/deploy/nginx.conf":/etc/nginx/conf.d/default.conf:ro nginx:alpine >/dev/null
sleep 5
curl -fsS http://127.0.0.1:8490/api/health && echo
curl -fsS -o /dev/null http://127.0.0.1/api/health && echo "proxy da porta 80 ok"
REMOTE
echo "MisterClip no ar: http://misterclip.nord  (ou http://${HOST#*@}:8490)"
