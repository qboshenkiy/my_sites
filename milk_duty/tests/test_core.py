import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import Store, Invalid
from app import Application, TelegramError

class RotationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'db.sqlite')
        self.people=[self.store.add_person(n) for n in ('Анна','Борис','Вера')]
        with self.store.db() as db:
            for p in self.people:
                db.execute('UPDATE people SET chat_id=? WHERE id=?',(100+p,p))
            self.store.put(db,'start_date','2026-10-26')
            self.store.put(db,'bot_token','123:test')
            self.store.put(db,'bot_id','123')
            self.store.put(db,'enabled',True)
        self.zone=ZoneInfo('Asia/Bishkek')
    def tearDown(self): self.tmp.cleanup()
    def at(self,date,time):return dt.datetime.fromisoformat(date+'T'+time).replace(tzinfo=self.zone)
    def cfg(self,db):return self.store.settings(db)
    def test_weekdays_and_wrap(self):
        with self.store.db() as db:
            cfg=self.cfg(db)
            self.assertEqual([self.store.nominal(db,dt.date(2026,10,d),cfg) for d in range(26,32)],[1,2,3,1,2,None])
            self.assertEqual(self.store.nominal(db,dt.date(2026,11,1),cfg),None)
            self.assertEqual(self.store.nominal(db,dt.date(2026,11,2),cfg),3)
    def test_eve_and_morning_exact_time_and_restart(self):
        self.store.schedule(self.at('2026-10-26','07:59'))
        with self.store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)
        self.store.schedule(self.at('2026-10-26','08:00'))
        self.store.schedule(self.at('2026-10-26','19:00'))
        restarted=Store(self.store.path);restarted.schedule(self.at('2026-10-26','19:01'))
        with self.store.db() as db:
            rows=list(db.execute('SELECT day,kind,person FROM outbox ORDER BY id'))
            self.assertEqual([tuple(r) for r in rows],[('2026-10-26','morning',1),('2026-10-27','eve',2)])
    def test_sunday_reminds_for_monday_only(self):
        self.store.schedule(self.at('2026-11-01','19:00'))
        with self.store.db() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT day,kind FROM outbox')],[('2026-11-02','eve')])
    def test_disable_eve_and_pause(self):
        with self.store.db() as db:self.store.put(db,'eve_enabled',False)
        self.store.schedule(self.at('2026-10-26','19:00'))
        with self.store.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
            self.store.put(db,'enabled',False)
        self.store.schedule(self.at('2026-10-27','08:00'))
        with self.store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
    def test_replacement_keeps_rotation_and_notifies_both(self):
        day=(dt.datetime.now(self.zone).date()+dt.timedelta(days=1))
        while day.weekday()>4:day+=dt.timedelta(days=1)
        with self.store.db() as db:
            self.store.put(db,'start_date',day.isoformat())
            duty=self.store.duty(db,day,self.cfg(db),True)
            self.store.enqueue(db,duty,'eve',1,'old',time_after(day,self.zone))
            db.execute("UPDATE outbox SET status='sent'")
        self.store.replace(day.isoformat(),3)
        with self.store.db() as db:
            duty=self.store.duty(db,day,self.cfg(db))
            self.assertEqual((duty['planned'],duty['person']),(1,3))
            following=day+dt.timedelta(days=1)
            while following.weekday()>4:following+=dt.timedelta(days=1)
            self.assertEqual(self.store.nominal(db,following,self.cfg(db)),2)
            self.assertEqual(db.execute("SELECT count(*) FROM outbox WHERE status='pending'").fetchone()[0],2)
        self.store.replace(day.isoformat(),3)
        with self.store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],3)
    def test_rapid_replacements_cancel_original_not_uninformed_middle_person(self):
        day=dt.datetime.now(self.zone).date()+dt.timedelta(days=1)
        while day.weekday()>4:day+=dt.timedelta(days=1)
        with self.store.db() as db:
            self.store.put(db,'start_date',day.isoformat())
            duty=self.store.duty(db,day,self.cfg(db),True)
            self.store.enqueue(db,duty,'eve',1,'old',time_after(day,self.zone))
            db.execute("UPDATE outbox SET status='sent'")
        self.store.replace(day.isoformat(),2)
        self.store.replace(day.isoformat(),3)
        with self.store.db() as db:
            pending=[tuple(r) for r in db.execute("SELECT kind,person FROM outbox WHERE status='pending' ORDER BY id")]
            self.assertEqual(pending,[('replacement-old',1),('replacement-new',3)])

    def test_disabling_weekday_stops_existing_duty(self):
        self.store.schedule(self.at('2026-10-26','08:00'))
        with self.store.db() as db:
            cfg=self.cfg(db);cfg['weekdays']=[1,2,3,4]
        self.store.save_settings(cfg)
        self.store.schedule(self.at('2026-10-26','08:05'))
        with self.store.db() as db:self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)

    def test_failed_send_retries_and_expiry(self):
        self.store.schedule(self.at('2026-10-26','08:00'))
        calls=[]
        def broken(*args):calls.append(args);raise TelegramError(429,60)
        app=Application(self.store,broken);stamp=self.at('2026-10-26','08:00').timestamp()
        app.deliver(stamp)
        app.deliver(stamp+10)
        self.assertEqual(len(calls),1)
        with self.store.db() as db:self.assertEqual(db.execute('SELECT status FROM outbox').fetchone()[0],'retry')
        app.transport=lambda *args:calls.append(args)
        app.deliver(stamp+61)
        app.deliver(stamp+62)
        self.assertEqual(len(calls),2)
        with self.store.db() as db:self.assertEqual(db.execute('SELECT status FROM outbox').fetchone()[0],'sent')
    def test_one_time_invite(self):
        p=self.store.add_person('Гость')
        with self.store.db() as db:token=db.execute('SELECT invite FROM people WHERE id=?',(p,)).fetchone()[0]
        self.assertEqual(self.store.join(token,999),'Гость')
        with self.assertRaises(Invalid):self.store.join(token,888)
    def test_secret_not_in_snapshot(self):
        snapshot=json.dumps(self.store.snapshot())
        self.assertNotIn('123:test',snapshot)
        self.assertNotIn('password_hash',snapshot)
    def test_validation(self):
        cfg=dict(__import__('core').DEFAULTS)
        for key,value in [('weekdays',[]),('morning_time','25:00'),('timezone','bad'),('message','{person.password}')]:
            with self.assertRaises(Invalid):self.store.validate_settings({**cfg,key:value})

def time_after(day,zone):return dt.datetime.combine(day+dt.timedelta(days=1),dt.time(),zone).timestamp()
if __name__=='__main__':unittest.main()
