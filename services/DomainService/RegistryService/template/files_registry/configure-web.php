<?php
// 根据容器地址和实例参数生成面板配置。 / Generate panel settings from the container address and instance parameters.
$path = '/opt/registry/cp/';
$ip = explode(' ', trim(shell_exec('hostname -I')))[0];
$env = file_get_contents($path . 'env-sample');
$settings = [
    'APP_URL' => 'http://' . $ip . ':8080',
    'APP_DOMAIN' => $ip,
    'APP_ROOT' => '/opt/registry/cp',
    'DB_HOST' => '127.0.0.1',
    'DB_USERNAME' => 'registry',
    'DB_PASSWORD' => '%s',
    'MAIL_DRIVER' => 'none',
    'TEST_TLDS' => '',
];
foreach ($settings as $key => $value) {
    // 使用带引号的 dotenv 值，保留密码中的特殊字符。
    // Quote the dotenv value to preserve special characters in the password.
    if ($key === 'DB_PASSWORD') {
        $value = json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $value = str_replace('$', '\\$', $value);
    }
    $env = preg_replace_callback('/^' . preg_quote($key, '/') . '=.*$/m',
        function () use ($key, $value) { return $key . '=' . $value; }, $env);
}
file_put_contents($path . '.env', $env);
// 本地示例通过端口映射提供 HTTP 管理面板。
// The local example exposes the HTTP panel through port forwarding.
$bootstrapPath = $path . 'bootstrap/app.php';
$bootstrap = file_get_contents($bootstrapPath);
$bootstrap = str_replace("ini_set('session.cookie_secure', '1');",
    "ini_set('session.cookie_secure', '0');", $bootstrap);
$bootstrap = str_replace("ini_set('session.use_strict_mode', '1');",
    "ini_set('session.name', 'NAMINGOSESSID');
ini_set('session.use_strict_mode', '1');", $bootstrap);
file_put_contents($bootstrapPath, $bootstrap);

