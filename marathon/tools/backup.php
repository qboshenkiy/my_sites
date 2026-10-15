<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
$dir=getenv('MARATHON_DATA_DIR')?:dirname(__DIR__).'/storage';$target=$argv[1]??'';
if(!$target||!is_file($dir.'/marathon.sqlite')||file_exists($target)){fwrite(STDERR,"Pass a new backup filename. The source database must exist.\n");exit(1);}
try{$db=new PDO('sqlite:'.$dir.'/marathon.sqlite');$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);$db->exec('PRAGMA busy_timeout=10000');$db->exec('VACUUM INTO '.$db->quote($target));echo "Backup created.\n";}catch(Throwable $e){fwrite(STDERR,"Backup failed.\n");exit(1);}
