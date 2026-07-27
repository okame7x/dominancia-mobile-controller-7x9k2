#!/data/data/com.termux/files/usr/bin/sh
set -eu

REPO_URL="${1:-${REPO_URL:-}}"
BRANCH="${BRANCH:-main}"
TARGET_DIR="${TARGET_DIR:-$HOME/dominancia-controller-mobile}"
OLD_DIRS="${OLD_DIRS:-$HOME/dominancia-cloud-phone $HOME/dominancia-buyer}"

if [ -z "$REPO_URL" ]; then
  echo "Uso:"
  echo "  sh update-from-git.sh https://github.com/USUARIO/REPO.git"
  echo
  echo "Ou:"
  echo "  REPO_URL=https://github.com/USUARIO/REPO.git sh update-from-git.sh"
  exit 1
fi

pkg update -y
pkg install -y git python

BACKUP_DIR="$HOME/.dominancia-update-backup"
LOCAL_STATE_DIR="$HOME/.dominancia"
mkdir -p "$BACKUP_DIR"
mkdir -p "$LOCAL_STATE_DIR"

backup_local_files() {
  SRC="$1"
  [ -f "$SRC/config.json" ] && cp "$SRC/config.json" "$BACKUP_DIR/config.json" && cp "$SRC/config.json" "$LOCAL_STATE_DIR/config.local.json"
  [ -f "$SRC/config.local.json" ] && cp "$SRC/config.local.json" "$LOCAL_STATE_DIR/config.local.json"
  [ -f "$SRC/.tamblox_device" ] && cp "$SRC/.tamblox_device" "$BACKUP_DIR/.tamblox_device" && cp "$SRC/.tamblox_device" "$LOCAL_STATE_DIR/.tamblox_device"
  [ -f "$SRC/.env" ] && cp "$SRC/.env" "$BACKUP_DIR/.env"
  [ -f "$LOCAL_STATE_DIR/config.local.json" ] && cp "$LOCAL_STATE_DIR/config.local.json" "$BACKUP_DIR/config.local.json"
  [ -f "$LOCAL_STATE_DIR/.tamblox_device" ] && cp "$LOCAL_STATE_DIR/.tamblox_device" "$BACKUP_DIR/.tamblox_device"
}

restore_local_files() {
  DST="$1"
  mkdir -p "$LOCAL_STATE_DIR"
  [ -f "$BACKUP_DIR/config.local.json" ] && cp "$BACKUP_DIR/config.local.json" "$LOCAL_STATE_DIR/config.local.json"
  [ -f "$BACKUP_DIR/.tamblox_device" ] && cp "$BACKUP_DIR/.tamblox_device" "$LOCAL_STATE_DIR/.tamblox_device"
  [ -f "$BACKUP_DIR/.env" ] && cp "$BACKUP_DIR/.env" "$DST/.env"
}

replace_old_dir() {
  OLD="$1"
  [ "$OLD" = "$TARGET_DIR" ] && return 0
  [ -d "$OLD" ] || return 0
  echo "Versao antiga encontrada em $OLD. Salvando backup e removendo/substituindo."
  backup_local_files "$OLD"
  rm -rf "$OLD"
}

for OLD in $OLD_DIRS; do
  replace_old_dir "$OLD"
done

if [ -d "$TARGET_DIR/.git" ]; then
  echo "Atualizando repositorio existente em $TARGET_DIR"
  backup_local_files "$TARGET_DIR"
  cd "$TARGET_DIR"
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"
  restore_local_files "$TARGET_DIR"
else
  if [ -d "$TARGET_DIR" ]; then
    echo "Pasta antiga encontrada. Salvando backup e substituindo por clone novo."
    backup_local_files "$TARGET_DIR"
    mv "$TARGET_DIR" "$TARGET_DIR.backup.$(date +%Y%m%d%H%M%S)"
  fi
  git clone --branch "$BRANCH" "$REPO_URL" "$TARGET_DIR"
  restore_local_files "$TARGET_DIR"
fi

cd "$TARGET_DIR"
chmod +x dominancia-buyer update-from-git.sh instalar-termux.sh 2>/dev/null || true

echo
echo "Atualizado em: $TARGET_DIR"
echo "Para abrir:"
echo "  cd $TARGET_DIR"
echo "  ./dominancia-buyer"
echo
echo "Para atualizar de novo:"
echo "  cd $TARGET_DIR"
echo "  sh update-from-git.sh $REPO_URL"
