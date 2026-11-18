import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import app
import alerts
import bot_diagnostics as diagnostics
import monitor


class DiagnosticTests(unittest.TestCase):
    def test_docker_missing_container_is_distinct_from_service_failure(self):
        for status in (404, 500):
            connection=Mock()
            connection.getresponse.return_value.status=status
            connection.getresponse.return_value.read.return_value=b'{}'
            with patch.object(monitor.docker_api,'UnixConnection',return_value=connection):
                with self.assertRaises(ValueError) as error:
                    monitor.docker_api.inspect('removed-bot')
            self.assertEqual(isinstance(error.exception,monitor.docker_api.ContainerNotFound),status==404)
            connection.close.assert_called_once()

    def test_removed_bot_disappears_but_stopped_bot_remains_visible(self):
        def inspect(container):
            if container=='milk-duty-web-1':raise monitor.docker_api.ContainerNotFound()
            return {'status':'exited','exit_code':0}
        with patch.object(monitor.docker_api,'inspect',side_effect=inspect),patch.object(monitor.docker_api,'logs',return_value=''):
            rows=monitor.bots()
            self.assertEqual(monitor.inspect_bot('milk'),{'status':'not_installed'})
        self.assertEqual([r['id'] for r in rows],['marathon','pulse'])
        self.assertTrue(all(r['status']=='exited' for r in rows))

    def test_safe_causes_distinguish_recipient_conflict_token_and_network(self):
        for code,kind in [(401,'token'),(403,'forbidden'),(409,'conflict'),(429,'rate_limit'),(503,'telegram_server')]:
            self.assertEqual(diagnostics.explain('Telegram failed HTTP '+str(code))['code'],kind)
        self.assertIn('DNS',diagnostics.explain('HTTP 0; cURL 6')['cause'])
        self.assertIn('время ожидания',diagnostics.explain('HTTP 0; cURL 28')['cause'])
        self.assertIn('не означает остановку',diagnostics.explain('HTTP 403')['action'])

    def test_raw_tokens_urls_and_messages_never_returned_in_diagnosis(self):
        raw='2026-11-05T12:00:00.123Z HTTP 401 https://api.telegram.org/bot123456:SECRET_TOKEN/sendMessage?text=PRIVATE_MESSAGE'
        result=diagnostics.recent(raw)
        self.assertEqual(result['at'],'2026-11-05T12:00:00.123Z')
        for secret in ('SECRET_TOKEN','PRIVATE_MESSAGE','api.telegram.org/bot'):
            self.assertNotIn(secret,json.dumps(result))
        self.assertIsNone(diagnostics.recent('Unrecognized private log content'))

    def test_running_process_is_separate_from_historical_error(self):
        with patch.object(monitor.docker_api,'inspect',return_value={'status':'running','restarts':0}),patch.object(monitor.docker_api,'logs',return_value='2026-11-05T12:00:00Z Bot connection unavailable. Retrying in 5 seconds.'):
            row=monitor.bots()[0]
        self.assertEqual(row['status'],'running')
        self.assertEqual(row['last_error']['code'],'unknown_connection')
        self.assertIn('не проверка доставки',row['diagnosis'])

    def test_monitoring_failure_does_not_claim_bot_stopped(self):
        with patch.object(monitor.docker_api,'inspect',side_effect=OSError):
            row=monitor.bots()[0]
        self.assertEqual(row['status'],'unavailable')
        self.assertIn('не подтверждена',row['diagnosis'])


class HealthAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.old=app.DATA;app.DATA=Path(self.tmp.name);self.addCleanup(setattr,app,'DATA',self.old)
        self.service=alerts.Service(app.database);self.now=time.time()

    def test_startup_running_is_quiet_stop_is_deduplicated_and_recovery_persists(self):
        self.service.observe_bot('pulse',{'status':'running'},self.now)
        self.assertEqual(self.service.listing()['alerts'],[])
        self.service.observe_bot('pulse',{'status':'exited','exit_code':137,'oom_killed':True},self.now+1)
        restarted=alerts.Service(app.database)
        restarted.observe_bot('pulse',{'status':'exited'},self.now+2)
        self.assertEqual(len(self.service.listing()['alerts']),1)
        self.assertIn('OOM',self.service.listing()['alerts'][0]['body'])
        restarted.observe_bot('pulse',{'status':'running'},self.now+3)
        self.assertEqual(self.service.listing()['alerts'][0]['kind'],'recovery')

    def test_failed_activity_check_is_not_a_container_outage(self):
        with patch.object(monitor.docker_api,'inspect',return_value={'status':'running'}),patch.object(monitor.docker_api,'logs',return_value=''),patch.object(monitor,'bot_action',side_effect=ValueError):
            self.service.collect()
        self.assertEqual(self.service.listing()['alerts'],[])
        self.assertIn('не подтверждает остановку',self.service.public()['scan_errors']['pulse'])

    def test_removed_bot_is_not_polled_or_reported_as_broken(self):
        def inspect(bot):
            return {'status':'not_installed' if bot=='milk' else 'running'}
        with patch.object(monitor,'inspect_bot',side_effect=inspect),patch.object(monitor,'proxy_logs',return_value=''),patch.object(monitor,'bot_action',return_value={'events':[],'cursor':0}) as activity:
            self.service.collect()
        self.assertEqual([c.args[0] for c in activity.call_args_list],['marathon','pulse'])
        self.assertEqual(self.service.public()['scan_errors'],{})
        self.assertEqual(self.service.listing()['alerts'],[])

    def test_refused_requests_explained_in_spam_notification(self):
        self.service.save({'http_limit':10})
        rows=[json.dumps({'logger':'http.log.access.log0','ts':self.now+i/1000,'status':403,'request':{'remote_ip':'1.2.3.4','host':'notes.example.com','uri':'/.env','method':'GET'}}) for i in range(10)]
        self.service.ingest(alerts.http_samples('\n'.join(rows),self.now-1),self.now+1)
        body=self.service.listing()['alerts'][0]['body']
        self.assertIn('403 — 10',body)
        self.assertIn('запрос отклонён',body)

    def test_notification_explains_http_error_without_claiming_outage(self):
        events=[{'id':1,'person':'0','created':self.now,'direction':'error','text':'HTTP 409'}]
        body=alerts.bot_samples('pulse',events)[0]['body']
        self.assertIn('Конфликт',body)
        self.assertIn('не подтверждает остановку',body)
