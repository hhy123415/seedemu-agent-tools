#!/bin/sh
set -eu

# 固定版本使用镜像内预下载的 Paper 和原版依赖，冷启动不再访问下载服务。
if [ "${TYPE:-PAPER}" = PAPER ] && [ "${VERSION:-1.21.6}" = 1.21.6 ] && [ "${PAPER_BUILD:-48}" = 48 ]; then
    for directory in cache libraries versions; do
        if [ -d "/opt/paper-runtime/$directory" ]; then
            mkdir -p "/data/$directory"
            cp -a "/opt/paper-runtime/$directory/." "/data/$directory/"
            if [ "$(id -u)" = 0 ]; then
                chown -R "${UID:-1000}:${GID:-1000}" "/data/$directory"
            fi
        fi
    done
    # E17 的启动补丁需要 commands 节点；其他配置由 Paper 自行生成默认值。
    if [ ! -f /data/spigot.yml ]; then
        printf 'commands: {}\n' > /data/spigot.yml
        if [ "$(id -u)" = 0 ]; then
            chown "${UID:-1000}:${GID:-1000}" /data/spigot.yml
        fi
    fi
    export TYPE=CUSTOM CUSTOM_SERVER=/opt/paper-runtime/paper-1.21.6-48.jar
    export SKIP_DOWNLOAD_DEFAULTS=true
    echo '[semantic-start] Using bundled Paper 1.21.6 build 48 and cached dependencies'
fi

# 嵌套 bind mount 会让 Docker 在数据卷中创建 root 所有的父目录。
# 上游只在 /data 本身属主不匹配时递归 chown，因此这里修正插件父目录。
if [ "$(id -u)" = 0 ]; then
    mkdir -p /data/plugins/SemanticRegions
    chown "${UID:-1000}:${GID:-1000}" /data/plugins /data/plugins/SemanticRegions
fi
exec /start "$@"
