"""Host-only installation of safe-file denial at the existing Caddy proxy."""
import subprocess
import time
import json
import re
from pathlib import Path

PROXY='glava-marathon-proxy-1'
IMPORT='    import /data/guard-sensitive.caddy # Guard sensitive files'
SNIPPET=r'''# Managed by Guard: shared rate limit and sensitive file protection
route {
    forward_auth unix//data/guard-request.sock {
        uri /check
        header_up X-Guard-IP {remote_host}
        header_up -Cookie
        header_up -Authorization
        transport http {
            response_header_timeout 3s
        }
    }
@guard_sensitive path_regexp guard_sensitive `(?i)(?:^|/)(?:\.env(?:[./][^/]*)?|\.git(?:/.*)?|\.svn(?:/.*)?|\.aws(?:/.*)?|\.ssh(?:/.*)?|\.config/gcloud(?:/.*)?|\.kube/config|\.docker/config\.json|application_default_credentials\.json|firebase-adminsdk\.json|firebase-key\.json|phpinfo\.php|\.DS_Store)(?:$|/)`
respond @guard_sensitive "Not found" 404
}
'''


def disable_automatic_redirects(source):
    # Caddy inserts automatic redirects before a catch-all HTTP route.
    # Keep certificate automation; our explicit gateway performs the redirect.
    lines=source.splitlines()
    first=next((i for i,line in enumerate(lines) if line.strip() and not line.lstrip().startswith('#')),None)
    if first is not None and lines[first].strip()=='{':
        depth=0
        for index in range(first,len(lines)):
            depth+=lines[index].count('{')-lines[index].count('}')
            match=re.match(r'^(\s*auto_https\s+)([^#]*)(.*)$',lines[index])
            if match:
                options=match[2].split()
                if 'off' not in options and 'disable_redirects' not in options:
                    lines[index]=match[1]+' '.join([*options,'disable_redirects'])+(' '+match[3] if match[3] else '')
                return '\n'.join(lines)+'\n'
            if index>first and depth==0:break
        lines.insert(first+1,'    auto_https disable_redirects')
        return '\n'.join(lines)+'\n'
    return '{\n    auto_https disable_redirects\n}\n\n'+source


def install_imports(source):
    source=disable_automatic_redirects(source)
    # Upgrade old gateways whose redir directive ran before the Guard route.
    source=re.sub(r'# Guard HTTP gateway BEGIN.*?# Guard HTTP gateway END\s*','',source,flags=re.S)
    result=[];block=[];depth=0;count=0
    for line in source.splitlines():
        if depth==0 and not block and not (line.strip().endswith('{') and not line.lstrip().startswith('#')):
            result.append(line);continue
        block.append(line);depth+=line.count('{')-line.count('}')
        if depth==0:
            if block[0].strip()!='{' and not block[0].lstrip().startswith('('):
                count+=1
                if not any('/data/guard-sensitive.caddy' in item and item.lstrip().startswith('import ') for item in block):block.insert(1,IMPORT)
                if not any(item.lstrip().startswith('log ') or item.strip()=='log' for item in block):block.insert(2,'    log {\n        output stdout\n        format json\n    }')
            result.extend(block);block=[]
    if '# Guard HTTP gateway BEGIN' not in source:
        count+=1
        result += ['# Guard HTTP gateway BEGIN',':80 {','    log {','        output stdout','        format json','    }','    route {',IMPORT,'        redir https://{host}{uri} 308','    }','}','# Guard HTTP gateway END']
    if depth or block:raise ValueError('Не удалось безопасно разобрать Caddyfile')
    if not count:raise ValueError('В прокси не найдены сайты')
    return '\n'.join(result).rstrip()+'\n',count


def run(args,data=None):
    result=subprocess.run(['docker','exec',*(['-i'] if data is not None else []),PROXY,*args],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
    if result.returncode:raise ValueError('Не удалось проверить или применить защиту файлов Caddy')
    return result.stdout


def main():
    mounts=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .Mounts}}',PROXY],text=True))
    mount=next((m for m in mounts if m['Destination']=='/etc/caddy/Caddyfile'),None)
    if not mount:raise ValueError('Не найден bind mount Caddyfile')
    caddy=Path(mount['Source'])
    if caddy.is_symlink() or not caddy.is_file():raise ValueError('Некорректный путь Caddyfile')
    import install_request_gate
    install_request_gate.main()
    original=caddy.read_text()
    candidate,count=install_imports(original)
    previous=run(['sh','-c','cat /data/guard-sensitive.caddy 2>/dev/null || true'])
    try:
        run(['sh','-c','cat > /data/guard-sensitive.caddy'],SNIPPET.encode())
        run(['sh','-c','cat > /tmp/guard-candidate.caddy'],candidate.encode())
        run(['caddy','validate','--config','/tmp/guard-candidate.caddy','--adapter','caddyfile'])
    except Exception:
        run(['sh','-c','cat > /data/guard-sensitive.caddy'],previous)
        raise
    if caddy.read_text()!=original:raise ValueError('Конфигурация прокси изменилась параллельно; повторите настройку')
    backup='/data/Caddyfile.before-guard-protection-'+str(int(time.time()))
    run(['sh','-c','cat > '+backup],original.encode())
    try:
        caddy.write_text(candidate)
        run(['caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
    except Exception:
        caddy.write_text(original)
        run(['sh','-c','cat > /data/guard-sensitive.caddy'],previous)
        run(['caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'])
        raise
    print('Sensitive file protection active:',count,'sites')
if __name__=='__main__':main()
