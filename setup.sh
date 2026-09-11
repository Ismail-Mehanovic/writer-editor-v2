#!/bin/sh
# One-time setup of the Pi for the writing device. Run it on the Pi, from
# your normal account, inside this repo:
#
#     sudo sh setup.sh
#
# Safe to run again (for example after moving the repo): it replaces what
# it installed before instead of adding duplicates.
set -eu

USER_NAME=${SUDO_USER:?run this with sudo from your normal account}
USER_HOME=$(getent passwd "$USER_NAME" | cut -d: -f6)
REPO=$(cd "$(dirname "$0")" && pwd)
WRITING_DIR="$USER_HOME/writing"  # also where Ctrl+Space's shell starts
DOCUMENT=document.txt

# 1. Log in automatically on the screen (tty1) at boot, no password.
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $USER_NAME --noclear %I \$TERM
EOF
systemctl daemon-reload

# 2. That login opens the editor. Ctrl+Q (or a crash) leaves you in a
#    normal shell; typing exit there logs out, autologin logs straight
#    back in, and the editor opens again.
PROFILE="$USER_HOME/.profile"
[ -f "$USER_HOME/.bash_profile" ] && PROFILE="$USER_HOME/.bash_profile"
touch "$PROFILE"
chown "$USER_NAME:" "$PROFILE"
sed -i '/^# >>> writer >>>$/,/^# <<< writer <<<$/d' "$PROFILE"
cat >> "$PROFILE" <<EOF
# >>> writer >>>
# Added by $REPO/setup.sh: the screen's login (tty1) opens the editor.
if [ "\$(tty)" = /dev/tty1 ]; then
    cd '$WRITING_DIR' && python3 '$REPO/main.py' '$DOCUMENT'
    echo 'Editor closed. Type exit to go back to it.'
fi
# <<< writer <<<
EOF
sudo -u "$USER_NAME" mkdir -p "$WRITING_DIR"

# 3. Let this user shut down, power off and reboot without a password
#    (nothing else). visudo checks the rule first, because a broken file
#    in /etc/sudoers.d would stop sudo from working at all.
RULE_TMP=$(mktemp)
trap 'rm -f "$RULE_TMP"' EXIT
echo "$USER_NAME ALL=(root) NOPASSWD: $(command -v shutdown), $(command -v poweroff), $(command -v reboot)" > "$RULE_TMP"
visudo -cqf "$RULE_TMP"
install -m 0440 "$RULE_TMP" /etc/sudoers.d/writer-power

# 4. Let the video group set the backlight, so sleep can turn it off.
cat > /etc/udev/rules.d/90-writer-backlight.rules <<'EOF'
ACTION=="add", SUBSYSTEM=="backlight", RUN+="/bin/chgrp video $sys$devpath/brightness", RUN+="/bin/chmod g+w $sys$devpath/brightness"
EOF
udevadm control --reload
udevadm trigger --subsystem-match=backlight --action=add
usermod -aG video "$USER_NAME"

echo "Done. The editor will open $WRITING_DIR/$DOCUMENT at boot."
echo "Reboot now to try it:  sudo reboot"
