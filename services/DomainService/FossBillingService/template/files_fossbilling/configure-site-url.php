<?php
// 配置站点 URL。 / Configure the site URL.

$path = '/var/www/fossbilling/config.php';
$url = URL_PLACEHOLDER;
$browserHosts = BROWSER_HOSTS_PLACEHOLDER;
// 仅明确允许的浏览器入口可覆盖内部地址。 / Only explicitly allowed browser origins may override the simulation URL.
// CLI、cron 和其他 Host 保留内部地址。 / CLI, cron, and other Hosts retain the internal canonical origin.
$expression = "/* SEED_LOCAL_URL_BEGIN */ (PHP_SAPI !== 'cli' && "
    . "in_array(strtolower(\$_SERVER['HTTP_HOST'] ?? ''), "
    . var_export($browserHosts, true) . ", true) "
    . "? strtolower(\$_SERVER['HTTP_HOST']) . '/' : " . var_export($url, true)
    . ") /* SEED_LOCAL_URL_END */";
$text = file_get_contents($path);
$prefix = '([\'"]url[\'"]\s*=>\s*)';
$pattern = '~' . $prefix . '/\* SEED_LOCAL_URL_BEGIN \*/.*?/\* SEED_LOCAL_URL_END \*/~s';
if (!str_contains($text, '/* SEED_LOCAL_URL_BEGIN */')) {
    $pattern = '~' . $prefix . '([\'"])(.*?)\2~s';
}
$updated = preg_replace_callback($pattern, static fn($m) => $m[1] . $expression, $text, -1, $count);
if ($count !== 1 || $updated === null) {
    throw new RuntimeException('Expected exactly one url entry in config.php');
}
if ($updated === $text) {
    echo "PASS FOSSBilling internal and localhost URLs already configured\n";
    exit(0);
}
// Nginx 禁止访问 data/，临时配置不可下载。 / Nginx denies data/ so temporary configuration cannot be downloaded.
$temp = tempnam(dirname($path) . '/data', 'site-url-');
try {
    if (file_put_contents($temp, $updated, LOCK_EX) === false) {
        throw new RuntimeException('Failed to write FOSSBilling site URL');
    }
    exec(escapeshellarg(PHP_BINARY) . ' -l ' . escapeshellarg($temp) . ' 2>&1', $output, $status);
    if ($status !== 0) {
        throw new RuntimeException('Updated config failed PHP syntax validation');
    }
    chmod($temp, fileperms($path) & 0777);
    chown($temp, fileowner($path));
    chgrp($temp, filegroup($path));
    if (!rename($temp, $path)) {
        throw new RuntimeException('Failed to replace FOSSBilling config');
    }
} finally {
    if (is_file($temp)) { unlink($temp); }
}
echo "PASS FOSSBilling internal and localhost URLs configured\n";
