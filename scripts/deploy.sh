#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
. /home/kojima/work/aixec/.env
set +a

remote="/web/kurage_exbridge_jp"
curl --fail --ftp-create-dirs -T public/kfxbrain.php \
  "ftp://${FTP_USER}:${FTP_PASS}@${FTP_HOST}${remote}/kfxbrain.php"

if [[ -f public/kfxbrain_config.php ]]; then
  curl --fail --ftp-create-dirs -T public/kfxbrain_config.php \
    "ftp://${FTP_USER}:${FTP_PASS}@${FTP_HOST}${remote}/kfxbrain_config.php"
fi

echo "deployed: https://kurage.exbridge.jp/kfxbrain.php"
