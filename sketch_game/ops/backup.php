<?php
if(PHP_SAPI!=='cli')exit(1);
$path=$argv[1]??'';$source=(getenv('DRAW_DATA_DIR')?:'/var/lib/sketch').'/game.sqlite';
if(!$path||file_exists($path)||!is_file($source))exit(1);
$db=new PDO('sqlite:'.$source);$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);$db->exec('PRAGMA busy_timeout=10000');$db->exec('VACUUM INTO '.$db->quote($path));echo "Backup created\n";
