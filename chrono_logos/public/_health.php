<?php
// No application data or credentials are returned by this readiness endpoint.
header('Content-Type: application/json');
try {
    $db = new PDO('pgsql:host=' . getenv('DB_HOST') . ';port=' . (getenv('DB_PORT') ?: '5432') . ';dbname=' . getenv('DB_DATABASE'),
        getenv('DB_USERNAME'), getenv('DB_PASSWORD'), [PDO::ATTR_TIMEOUT => 3]);
    $db->query('SELECT 1 FROM migrations LIMIT 1');
    echo '{"status":"ok"}';
} catch (Throwable $e) {
    http_response_code(503);
    echo '{"status":"unavailable"}';
}
