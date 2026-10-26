#!/bin/sh
# Instala o Baixador só para o seu usuário (não precisa de sudo).
#   ./install.sh            instala ou atualiza
#   ./install.sh --remover  desinstala
set -e

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/opt/baixador"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/256x256/apps"

if [ "$1" = "--remover" ]; then
    rm -rf "$DEST" "$BIN/baixador" "$APPS/baixador.desktop" "$ICONS/baixador.png"
    echo "Baixador removido. Os componentes baixados ficam em ~/.local/share/baixador (pode apagar)."
    exit 0
fi

mkdir -p "$DEST" "$BIN" "$APPS" "$ICONS"
rm -rf "$DEST"
cp -a "$HERE" "$DEST"
ln -sf "$DEST/Baixador" "$BIN/baixador"
cp "$HERE/baixador.png" "$ICONS/baixador.png"
sed "s|^Exec=.*|Exec=$DEST/Baixador|" "$HERE/baixador.desktop" > "$APPS/baixador.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" >/dev/null 2>&1 || true

echo "Pronto! Procure \"Baixador de Vídeos\" no menu de aplicativos ou rode: baixador"
