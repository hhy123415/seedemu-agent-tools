<?php
// Generate component configuration by overriding upstream defaults with instance settings.
$config = require '/opt/registry/%s/config.php.dist';
$config = array_replace($config, [
    'db_host' => '127.0.0.1',
    'db_username' => 'registry',
    'db_password' => '%s',
    'roid' => 'COM',
%s]);
file_put_contents('/opt/registry/%s/config.php',
    "<?php
return " . var_export($config, true) . ";
");
