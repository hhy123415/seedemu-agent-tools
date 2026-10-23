<?php
/** Initialize the local API account; retain passwords across restarts and expose credentials only to host setup. */
declare(strict_types=1);
$path = '/opt/dns-hosting/bind-api-credentials.json';
if (!is_file($path)) {
    $old = umask(0077);
    file_put_contents($path, json_encode(['username' => 'fossbilling', 'password' => bin2hex(random_bytes(32))], JSON_THROW_ON_ERROR));
    umask($old);
}
chmod($path, 0600);
$credentials = json_decode(file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
$db = new PDO('sqlite:/var/lib/bind9-api/bind9_api.sqlite', null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]);
$db->exec(file_get_contents('/opt/bind9-api/database/sqlite.sql'));
$query = $db->prepare('SELECT password FROM users WHERE username = ?');
$query->execute([$credentials['username']]);
$existing = $query->fetchColumn();
if ($existing === false) {
    $db->prepare('INSERT INTO users (username, password) VALUES (?, ?)')->execute([
        $credentials['username'], password_hash($credentials['password'], PASSWORD_ARGON2ID),
    ]);
} elseif (!password_verify($credentials['password'], $existing)) {
    throw new RuntimeException('API 凭据与已有账号不一致，拒绝覆盖');
}
// Exempt internal setup requests from rate limits; API authentication remains required.
$db->exec("INSERT OR IGNORE INTO whitelist (ip_address) VALUES ('__REGISTRAR_IP__')");
foreach (glob('/var/lib/bind9-api/bind9_api.sqlite*') as $file) {
    chown($file, 'bind9-api');
    chgrp($file, 'bind9-api');
    chmod($file, 0600);
}
