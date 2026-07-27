#!/data/data/com.termux/files/usr/bin/sh
pkg update -y
pkg install -y python git
chmod +x dominancia-buyer
chmod +x update-from-git.sh
echo
echo "Pronto. Para abrir:"
echo "./dominancia-buyer"
echo
echo "Para atualizar via Git:"
echo "sh update-from-git.sh https://github.com/USUARIO/REPO.git"
