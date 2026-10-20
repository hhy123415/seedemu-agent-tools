<?php
// 仅在首次导入数据库后清理示例账号并初始化 TLD。 / Clear sample accounts and initialize TLDs only after the first schema import.
$db = new PDO('mysql:host=127.0.0.1;dbname=registry', 'registry', '%s');
$db->beginTransaction();
foreach (['registrar_users', 'registrar_whitelist', 'registrar_contact',
          'registrar_ote', 'registrar', 'users'] as $table) {
    $db->exec('DELETE FROM ' . $table);
}
// 保存上游默认参数和价格，再替换示例 TLD；仅用于全新数据库。
// Save upstream defaults and prices before replacing sample TLDs; fresh databases only.
$tldTemplate = $db->query('SELECT idn_table, secure, launch_phase_id FROM domain_tld WHERE id = 1')->fetch(PDO::FETCH_ASSOC);
$prices = $db->query('SELECT * FROM domain_price WHERE tldid = 1')->fetchAll(PDO::FETCH_ASSOC);
$restorePrices = $db->query('SELECT * FROM domain_restore_price WHERE tldid = 1')->fetchAll(PDO::FETCH_ASSOC);
if (!$tldTemplate || count($prices) !== 3 || count($restorePrices) !== 1) {
    throw new RuntimeException('Missing upstream TLD or pricing defaults');
}
$db->exec('DELETE FROM domain_price');
$db->exec('DELETE FROM domain_restore_price');
$db->exec('DELETE FROM domain_tld');
$insertTld = $db->prepare('INSERT INTO domain_tld (id, tld, idn_table, secure, launch_phase_id) VALUES (?, ?, ?, ?, ?)');
foreach ([%s] as $index => $tld) {
    $id = $index + 1;
    $insertTld->execute([$id, $tld, $tldTemplate['idn_table'], $tldTemplate['secure'], $tldTemplate['launch_phase_id']]);
    foreach (['domain_price' => $prices, 'domain_restore_price' => $restorePrices] as $table => $rows) {
        foreach ($rows as $row) {
            unset($row['id']);
            $row['tldid'] = $id;
            // 列名来自固定上游结构，所有值均通过参数绑定写入。
            // Column names come from the pinned schema; all values use bound parameters.
            $columns = '`' . implode('`, `', array_keys($row)) . '`';
            $placeholders = implode(', ', array_fill(0, count($row), '?'));
            $db->prepare("INSERT INTO `$table` ($columns) VALUES ($placeholders)")->execute(array_values($row));
        }
    }
}
$db->exec("UPDATE settings SET value = 'B02a COM Registry' WHERE name = 'company_name'");
$db->commit();
