<?php
// Application initialization operation.
require '/var/www/fossbilling/load.php';
require '/var/www/fossbilling/library/Registrar/Adapter/Namingo.php';
try {
    $adapter = new Registrar_Adapter_Namingo(CONNECTION_PLACEHOLDER);
    $epp = $adapter->epp_client();
    $adapter->epp_client_logout($epp);
    echo "EPP login OK\n";
} catch (Throwable $error) {
    fwrite(STDERR, $error->getMessage() . "\n");
    exit(1);
}
