#!/bin/sh
# 在本地 FOSSBilling 初始化之后启用网关。 / Enable the gateway after local FOSSBilling initialization.
set -e
rm -f /run/fake-payment-initialized /run/fake-payment-initialization.failed
trap 'touch /run/fake-payment-initialization.failed' EXIT
[ -f /run/fossbilling-initialized ]
php8.5 /opt/b02d/setup-gateway.php
touch /run/fake-payment-initialized
trap - EXIT
