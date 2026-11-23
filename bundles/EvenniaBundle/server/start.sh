#!/bin/sh
set -eu
cd /data
if [ ! -f game/server/conf/settings.py ]; then
    evennia --init game
fi
python /opt/evennia/install_editor.py /data/game
cd game
evennia migrate --noinput
# 先清理重启后可能残留的进程编号文件，数据库和游戏内容保留。
rm -f server/server.pid server/portal.pid
stop_evennia() {
    evennia stop || true
    kill "$child" 2>/dev/null || true
    wait "$child" || true
    exit 0
}
trap stop_evennia TERM INT
evennia start -l &
child=$!
wait "$child"
