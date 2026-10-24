<?php
/** 将 Registry 中的 所选 TLD 委派记录和域内 glue 地址发布到 对应主 DNS。 / Publish Registry delegation records and in-domain glue to the configured primary TLD server. */
declare(strict_types=1);

$tld = $argv[1] ?? '';
if (!preg_match('/^[a-z](?:[a-z0-9-]{0,29}[a-z0-9])?$/D', $tld)) {
    throw new RuntimeException('Invalid publication TLD');
}
$zone = $tld . '.';
define('PUBLICATION_CONFIG', '/opt/registry/dns-publication-' . $tld . '.json');
define('STATE_PATH', '/var/lib/namingo/' . $tld . '-publication.json');
if (!is_dir(dirname(STATE_PATH))) { mkdir(dirname(STATE_PATH), 0755, true); }
// 锁定单个 TLD，防止手动运行和定时循环同时更新状态。
// Lock each TLD to prevent concurrent manual and scheduled state updates.
$lock = fopen(STATE_PATH . '.lock', 'c');
if (!$lock || !flock($lock, LOCK_EX | LOCK_NB)) { exit(1); }

// TLD 发布地址和签名身份由 B02a 配置；配置缺失时拒绝发布，不回退到无签名更新。 / Use the authorized TLD endpoint and TSIG identity; never fall back to unsigned updates.
$publication = json_decode(file_get_contents(PUBLICATION_CONFIG), true, 512, JSON_THROW_ON_ERROR);
if (($publication['zone'] ?? null) !== $zone
    || !filter_var($publication['server'] ?? '', FILTER_VALIDATE_IP, FILTER_FLAG_IPV4)
    || !is_readable($publication['key_file'] ?? '')) {
    throw new RuntimeException('Invalid Registry DNS publication configuration or missing TSIG key');
}

// 从 Namingo Registry 读取可发布的 所选 TLD 域名及其名称服务器。 / Read publishable domains and their name servers from Namingo Registry.
$config = require '/opt/registry/epp/config.php';
$db = new PDO(
    'mysql:host=127.0.0.1;dbname=registry;charset=utf8mb4',
    'registry',
    $config['db_password'],
    [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
);

$domainsQuery = $db->prepare("SELECT d.id, d.name
    FROM domain d JOIN domain_tld t ON t.id = d.tldid
    WHERE LOWER(t.tld) IN (?, ?)
      AND (d.exdate > CURRENT_TIMESTAMP OR d.rgpstatus = 'pendingRestore')
      AND NOT EXISTS (SELECT 1 FROM domain_status s WHERE s.domain_id = d.id
          AND s.status IN ('clientHold', 'serverHold'))");
$domainsQuery->execute([$tld, '.' . $tld]);
$domains = $domainsQuery->fetchAll(PDO::FETCH_ASSOC);
$nsQuery = $db->prepare('SELECT DISTINCT h.name
    FROM domain_host_map m JOIN host h ON h.id = m.host_id
    WHERE m.domain_id = ?');
$glueQuery = $db->prepare('SELECT h.name, a.ip, a.addr
    FROM host h JOIN host_addr a ON a.host_id = h.id
    WHERE h.domain_id = ?');

// 为每个符合条件的域名生成父区中应有的记录。 / Generate parent-zone records for each eligible domain.
$current = [];
foreach ($domains as $domain) {
    $name = strtolower(rtrim($domain['name'], '.')) . '.';
    if (!preg_match('/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.' . preg_quote($zone, '/') . '$/D', $name)) {
        continue;
    }

    $nsQuery->execute([$domain['id']]);
    $records = [];
    $registeredNs = $nsQuery->fetchAll(PDO::FETCH_COLUMN);
    if (!$registeredNs) {
        // 没有显式 NS 的域名不发布委派；旧委派由下方的差异更新撤销。 / Do not publish domains without explicit NS; remove old delegations through the diff below.
        continue;
    }

    foreach ($registeredNs as $ns) {
        $host = strtolower(rtrim($ns, '.')) . '.';
        if (filter_var(rtrim($host, '.'), FILTER_VALIDATE_DOMAIN, FILTER_FLAG_HOSTNAME)) {
            $records[] = [$name, 'NS', $host];
        }
    }

    // 仅发布属于该域名的名称服务器 glue 地址。 / Publish only glue addresses belonging to this domain.
    $glueQuery->execute([$domain['id']]);
    foreach ($glueQuery->fetchAll(PDO::FETCH_ASSOC) as $glue) {
        $host = strtolower(rtrim($glue['name'], '.')) . '.';
        if (!str_ends_with($host, '.' . $name)) {
            continue;
        }
        $type = $glue['ip'] === 'v4' ? 'A' : ($glue['ip'] === 'v6' ? 'AAAA' : null);
        $family = $type === 'A' ? FILTER_FLAG_IPV4 : FILTER_FLAG_IPV6;
        if ($type !== null && filter_var($glue['addr'], FILTER_VALIDATE_IP, $family)) {
            $records[] = [$host, $type, $glue['addr']];
        }
    }

    $records = array_values(array_unique($records, SORT_REGULAR));
    sort($records);
    $current[$name] = $records;
}

// 与上次成功发布的记录比较，内容不变时跳过 DNS 更新。 / Compare against the last successful publication and skip unchanged records.
$previous = is_file(STATE_PATH) ? json_decode(file_get_contents(STATE_PATH), true, 512, JSON_THROW_ON_ERROR) : [];
ksort($current);
ksort($previous);
if ($previous === $current) {
    exit(0);
}

// 仅替换 所选 TLD 父区中发生变化的委派记录和 glue 地址。 / Replace only changed delegation and glue records in the parent zone.
$update = ['server ' . $publication['server'], 'zone ' . $publication['zone']];
foreach (array_unique(array_merge(array_keys($previous), array_keys($current))) as $name) {
    if (($previous[$name] ?? null) === ($current[$name] ?? null)) {
        continue;
    }

    $update[] = "update delete $name NS";
    foreach ($previous[$name] ?? [] as [$owner, $type]) {
        if ($type !== 'NS') {
            $update[] = "update delete $owner $type";
        }
    }

    foreach ($current[$name] ?? [] as [$owner, $type, $value]) {
        $update[] = "update add $owner 300 $type $value";
    }
}
$update[] = 'send';

// 通过 TCP 提交更新；仅在 nsupdate 成功后保存本轮状态。 / Submit updates over TCP and save state only after nsupdate succeeds.
$process = proc_open(
    ['/usr/bin/nsupdate', '-v', '-k', $publication['key_file']],
    [0 => ['pipe', 'r'], 1 => ['pipe', 'w'], 2 => ['pipe', 'w']],
    $pipes
);
if (!is_resource($process)) {
    throw new RuntimeException('Cannot start nsupdate');
}
fwrite($pipes[0], implode("\n", $update) . "\n");
fclose($pipes[0]);
$stdout = stream_get_contents($pipes[1]);
$stderr = stream_get_contents($pipes[2]);
fclose($pipes[1]);
fclose($pipes[2]);
if (proc_close($process) !== 0) {
    throw new RuntimeException("DNS update failed: $stdout $stderr");
}

if (!is_dir(dirname(STATE_PATH))) {
    mkdir(dirname(STATE_PATH), 0755, true);
}
$tmp = STATE_PATH . '.new';
file_put_contents($tmp, json_encode($current, JSON_THROW_ON_ERROR), LOCK_EX);
rename($tmp, STATE_PATH);
echo "Published " . count($current) . " $zone domains\n";
