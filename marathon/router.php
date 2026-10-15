<?php
$path=rawurldecode(parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH)??'/');
if(preg_match('~(?:^|/)(?:storage|lib|tools|deploy|tests|dist|\.git)(?:/|$)~i',$path)||preg_match('~(?:^|/)(?:\.[^/]*|Dockerfile|.*\.(?:zip|log|ini|yaml|yml|md|py|ps1|sh))$~i',$path)||str_contains($path,'\\')){http_response_code(404);echo 'Not found';return true;}
return false;
