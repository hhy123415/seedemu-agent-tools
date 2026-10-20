# 生成面板配置并设置凭据文件权限，然后启动 PHP 和 Nginx。 / Generate panel settings, restrict credential file permissions, then start PHP and Nginx.

php8.5 /opt/b02a-registry/configure-web.php
chown root:www-data /opt/registry/cp/.env
chmod 640 /opt/registry/cp/.env
mkdir -p /run/php
service php8.5-fpm start
service nginx start
