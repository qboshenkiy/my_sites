"""Idempotently register the installed Milk Duty application in the existing GitDeck."""
import fcntl
import importlib.util
import os
from pathlib import Path
import secrets
import subprocess
import types

PROJECT = {
    'id':'milk-duty', 'name':'Молоко — дежурства', 'kind':'docker',
    'repo':'https://github.com/qboshenkiy/my_sites.git', 'branch':'main',
    'subdir':'milk_duty', 'directory':'/opt/milk-duty', 'compose':'compose.yaml',
    'profiles':[], 'services':['web'], 'main_service':'web', 'paths':['src','web'],
    'wait_health':True, 'ssh_key':''
}


def add_project(panel, config, project=None):
    project = dict(project or PROJECT)
    existing = next((p for p in config['projects'] if p['id']==project['id']),None)
    if existing:
        if any(existing.get(key)!=project[key] for key in ('kind','directory','repo','subdir')):
            raise ValueError('ID milk-duty уже занят другим модулем. Существующие настройки не изменены.')
        return config['projects'], False
    validated = panel.project_from_form(project,None,config)
    projects = [*config['projects'],validated]
    panel.validate_config(dict(config,projects=projects))
    return projects, True


def main():
    if os.geteuid()!=0:
        raise SystemExit('Запустите через sudo python3 src/register_gitdeck.py')
    os.umask(0o077)
    config_path=Path('/etc/gitdeck/config.json')
    module_path=Path('/opt/gitdeck/app.py')
    if not config_path.is_file() or not module_path.is_file():
        raise SystemExit('GitDeck не найден. Установленное приложение не изменено.')
    if not (Path(PROJECT['directory'])/'compose.yaml').is_file():
        raise SystemExit('Сначала установите приложение в /opt/milk-duty.')
    if config_path.is_symlink():
        raise SystemExit('Конфигурация GitDeck не должна быть символической ссылкой.')
    spec=importlib.util.spec_from_file_location('gitdeck_registration',module_path)
    panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
    # Validate everything before pausing the panel.
    config=panel.load_config(config_path)
    _, needed=add_project(panel,config)
    if not needed:
        print('Карточка «Молоко — дежурства» уже есть в GitDeck. Настройки сохранены.')
        return
    if subprocess.run(['systemctl','is-active','--quiet','gitdeck']).returncode:
        raise SystemExit('Сначала запустите GitDeck: systemctl start gitdeck')
    subprocess.run(['systemctl','stop','gitdeck'],check=True)
    original=None
    changed=False
    try:
        config=panel.load_config(config_path)
        state=Path(config['state_dir'])
        with (state/'worker.lock').open('a') as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('В GitDeck идёт обновление. Дождитесь завершения и повторите.')
            with panel.db_open(config) as db:
                if db.execute("SELECT 1 FROM jobs WHERE status NOT IN ('success','failed') LIMIT 1").fetchone():
                    raise ValueError('В GitDeck есть незавершённые задания. Завершите их и повторите подключение.')
                if db.execute('SELECT 1 FROM jobs WHERE project=? LIMIT 1',(PROJECT['id'],)).fetchone():
                    raise ValueError('ID milk-duty уже есть в истории удалённого модуля. Подключите его через интерфейс GitDeck.')
            projects,needed=add_project(panel,config)
            if needed:
                original=config_path.read_bytes()
                backup=config_path.with_name('config.before-milk-duty-'+secrets.token_hex(6)+'.json')
                backup.write_bytes(original)
                os.chmod(backup,0o600)
                server=types.SimpleNamespace(config=config,config_path=str(config_path))
                panel.save_config(server,projects,panel.config_revision(config))
                changed=True
    except Exception as error:
        raise SystemExit(str(error)) from None
    finally:
        try:
            subprocess.run(['systemctl','start','gitdeck'],check=True)
        except Exception:
            if changed and original is not None:
                temp=config_path.with_name('config.rollback-'+secrets.token_hex(6)+'.tmp')
                temp.write_bytes(original);os.chmod(temp,0o600);os.replace(temp,config_path)
                subprocess.run(['systemctl','start','gitdeck'],check=False)
            raise SystemExit('GitDeck не запустился после подключения. Прежняя конфигурация восстановлена; проверьте systemctl status gitdeck.') from None
    print('Карточка «Молоко — дежурства» добавлена в GitDeck. Обновите страницу панели.')

if __name__=='__main__':main()
