#!/bin/sh
# 启动 PHP、Nginx 和定时任务服务。 / Start PHP, Nginx, and cron.
set -e
mkdir -p /run/php
service php8.5-fpm start
service nginx start
service cron start
