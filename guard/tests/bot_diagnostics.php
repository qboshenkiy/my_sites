<?php
// Run with either application's bot-guard.php; uses an isolated temporary database.
declare(strict_types=1);
$folder=sys_get_temp_dir().'/guard-diagnostics-'.bin2hex(random_bytes(6));
mkdir($folder,0700);putenv('MARATHON_DATA_DIR='.$folder);putenv('QUIZ_DATA_DIR='.$folder);
require $argv[1];
try {
    foreach([0,403,409,429,503] as $http){
        guardFailure([],'connection',new RuntimeException('HTTP '.$http.'; cURL 28; method getUpdates; https://private.invalid/SECRET'));
        $text=guardDb()->query('SELECT text FROM events ORDER BY id DESC LIMIT 1')->fetchColumn();
        if(!str_contains($text,'HTTP '.$http)||!str_contains($text,'cURL 28')||!str_contains($text,'getUpdates')||str_contains($text,'SECRET'))throw new RuntimeException('Safe diagnostic metadata was lost');
    }
    echo "Safe diagnostics: OK\n";
} finally {
    foreach(glob($folder.'/*') as $file)unlink($file);
    rmdir($folder);
}
