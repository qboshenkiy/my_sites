<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
$dataDir=getenv('QUIZ_DATA_DIR') ?: dirname(__DIR__).'/storage';
$output=$argv[1]??'';
if ($output==='' || !is_file($dataDir.'/quiz.sqlite')) { fwrite(STDERR,"Usage: php tools/backup.php /absolute/path/backup.sqlite\nDatabase must already exist.\n"); exit(1); }
if (file_exists($output)) { fwrite(STDERR,"Destination already exists; refusing to overwrite.\n"); exit(1); }
try {
    $db=new PDO('sqlite:'.$dataDir.'/quiz.sqlite');
    $db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);
    $db->exec('PRAGMA busy_timeout=10000');
    $db->exec('VACUUM INTO '.$db->quote($output));
    echo "Backup created.\n";
} catch (Throwable $e) { fwrite(STDERR,"Backup failed: ".$e->getMessage()."\n"); exit(1); }
