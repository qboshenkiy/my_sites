<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
$checks = [
    'PHP 8.1+' => PHP_VERSION_ID >= 80100,
    'PDO SQLite' => extension_loaded('pdo_sqlite'),
    'mbstring' => extension_loaded('mbstring'),
];
$dataDir = getenv('QUIZ_DATA_DIR') ?: dirname(__DIR__).'/storage';
if (!is_dir($dataDir)) @mkdir($dataDir, 0700, true);
$checks['Writable data directory'] = is_dir($dataDir) && is_writable($dataDir);
foreach ($checks as $name=>$ok) echo ($ok?'OK  ':'FAIL').' '.$name.PHP_EOL;
exit(in_array(false,$checks,true)?1:0);
