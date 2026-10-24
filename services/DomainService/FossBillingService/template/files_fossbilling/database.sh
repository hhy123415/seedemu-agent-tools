#!/bin/sh
# 先启动数据库，再创建安装所需账号。 / Start MariaDB before creating the installer account.
set -e
mkdir -p /run/mysqld
chown mysql:mysql /run/mysqld
service mariadb start
mariadb < /opt/b02b-fossbilling/database.sql
