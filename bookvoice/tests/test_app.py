import importlib.util,io,json,os,shutil,sqlite3,subprocess,sys,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from app import create_app,Service
from engine import clean_text,chunks,extract
from werkzeug.security import generate_password_hash
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import NameObject,DictionaryObject,DecodedStreamObject

class BooksTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'password.json').write_text(json.dumps({'hash':generate_password_hash('testing-password-2026'),'epoch':'epoch'}))
        self.app=create_app(self.root,models=self.root/'models');self.client=self.app.test_client();self.service=self.app.service
        self.csrf=self.client.post('/api/login',json={'password':'testing-password-2026'}).json['csrf'];self.headers={'X-CSRF-Token':self.csrf}
    def tearDown(self):self.tmp.cleanup()
    def textbook(self,text=None):
        r=self.client.post('/api/books',data={'title':'Тестовая книга','text':text or 'Первая глава. История начинается здесь.\n\nВторая глава. Новая встреча.'},headers=self.headers);self.assertEqual(r.status_code,201,r.json);return r.json['id']
    def test_auth_csrf_and_session_rotation(self):
        outsider=self.app.test_client();self.assertEqual(outsider.get('/api/bootstrap').status_code,401)
        self.assertEqual(self.client.post('/api/books',data={'text':'a'*30}).status_code,403)
        (self.root/'password.json').write_text(json.dumps({'hash':'','epoch':'new'}));self.assertEqual(self.client.get('/api/bootstrap').status_code,401)
    def test_login_rate_limit_and_origin(self):
        c=self.app.test_client();self.assertEqual(c.post('/api/login',json={'password':'testing-password-2026'},headers={'Origin':'https://evil.test'}).status_code,403)
        for i in range(10):self.assertEqual(c.post('/api/login',json={'password':'bad'}).status_code,401)
        self.assertEqual(c.post('/api/login',json={'password':'bad'}).status_code,429)
    def test_upload_docx_and_extraction(self):
        doc=Document();doc.add_paragraph('Глава первая. Хорошая книга ждёт читателя.');doc.add_paragraph('Здесь начинается история.');buf=io.BytesIO();doc.save(buf);buf.seek(0)
        r=self.client.post('/api/books',data={'file':(buf,'книга.docx')},headers=self.headers);self.assertEqual(r.status_code,201)
        id=r.json['id'];self.service.tick();b=self.client.get('/api/books/'+id).json;self.assertEqual(b['state'],'draft');self.assertIn('Глава первая',b['text'])
        self.assertEqual(self.client.post('/api/books',data={'file':(io.BytesIO(b'x'),'run.exe')},headers=self.headers).status_code,400)
    def test_pdf_text_scan_and_encryption(self):
        writer=PdfWriter();page=writer.add_blank_page(width=300,height=300)
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 250 Td (A book with a real text layer and paragraphs.) Tj ET');page[NameObject('/Contents')]=writer._add_object(stream)
        pdf=self.root/'text.pdf';writer.write(pdf);self.assertIn('real text layer',extract(pdf))
        blank=PdfWriter();blank.add_blank_page(width=300,height=300);blank.write(self.root/'scan.pdf')
        with self.assertRaisesRegex(ValueError,'OCR'):extract(self.root/'scan.pdf')
        blank.encrypt('secret');blank.write(self.root/'locked.pdf')
        with self.assertRaisesRegex(ValueError,'паролем'):extract(self.root/'locked.pdf')
    def test_edit_guard_and_validation(self):
        id=self.textbook();path='/api/books/'+id
        self.service.working=id
        self.assertEqual(self.client.post(path+'/save',json={},headers=self.headers).status_code,409)
        self.assertEqual(self.client.delete(path,headers=self.headers).status_code,409);self.service.working=None
        params={'title':'Книга','text':'Текст книги. '*10,'voice':'denis','speed':1,'pause':.35}
        self.assertEqual(self.client.post(path+'/save',json={**params,'speed':9},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post(path+'/save',json=params,headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/books/'+'a'*24).status_code,404)
        self.assertEqual(self.client.post(path+'/action',json={'action':'start'},headers=self.headers).status_code,400)
    def test_queue_resume_audio_range_and_delete(self):
        if not shutil.which('ffmpeg'):self.skipTest('ffmpeg required')
        id=self.textbook('Короткое предложение. '*180);folder=self.service.books/id
        wav=self.root/'tone.wav'
        with wave.open(str(wav),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(22050);f.writeframes(b'\x00\x00'*2205)
        mp3=self.root/'tone.mp3';subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),str(mp3)],check=True)
        calls=[]
        def render(text,path,*args):
            calls.append(text);Path(path).write_bytes(mp3.read_bytes())
            if len(calls)==1:self.service.update(id,state='paused')
        self.service.engine.available=lambda key:True;self.service.engine.render=render
        path='/api/books/'+id
        self.client.post(path+'/action',json={'action':'start'},headers=self.headers);self.service.tick();self.assertEqual(self.service.get(id)['state'],'paused');self.assertEqual(len(calls),1)
        self.client.post(path+'/action',json={'action':'start'},headers=self.headers);self.service.tick();b=self.service.get(id);self.assertEqual(b['state'],'ready');self.assertEqual(len(calls),b['total'])
        response=self.client.get(path+'/audio/full',headers={'Range':'bytes=0-20'});self.assertEqual(response.status_code,206);self.assertEqual(len(response.data),21);response.close()
        self.assertEqual(self.app.test_client().get(path+'/audio/full').status_code,401)
        self.assertEqual(self.client.delete(path,headers=self.headers).status_code,200);self.assertFalse(folder.exists())
    def test_elevenlabs_opt_in_secret_and_no_blind_retry(self):
        import elevenlabs
        key='sk_fixture_not_a_real_key'
        with patch.object(elevenlabs,'list_voices',return_value=[{'id':'voice123','name':'Story Voice'}]):
            response=self.client.post('/api/elevenlabs',json={'key':key},headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertNotIn(key,json.dumps(response.json));self.assertNotIn(key,json.dumps(self.client.get('/api/bootstrap').json));self.assertEqual((self.root/'elevenlabs.json').stat().st_mode&0o777,0o600)
        id=self.textbook();path='/api/books/'+id
        params={'title':'Книга','text':'История для озвучки. '*20,'voice':'denis','provider':'elevenlabs','eleven_voice_id':'voice123','speed':1,'pause':.35}
        self.assertEqual(self.client.post(path+'/save',json=params,headers=self.headers).status_code,200)
        self.assertEqual(self.client.post(path+'/action',json={'action':'start'},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post(path+'/sample',json={},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post(path+'/action',json={'action':'start','consent':True},headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/api/elevenlabs',json={'remove':True},headers=self.headers).status_code,409)
        with patch.object(elevenlabs,'render',side_effect=ValueError('Сбой ElevenLabs')) as render,patch.object(self.service.engine,'render',side_effect=AssertionError('Must not use local fallback')):
            self.service.tick();self.assertEqual(self.service.get(id)['state'],'error');self.service.tick();self.assertEqual(render.call_count,1)
        self.assertEqual(self.client.post('/api/elevenlabs',json={'remove':True},headers=self.headers).status_code,200)
        self.assertNotIn(key,(self.root/'elevenlabs.json').read_text());self.assertEqual(self.client.post(path+'/action',json={'action':'start','consent':True},headers=self.headers).status_code,400)
    def test_elevenlabs_transport_parameters(self):
        import elevenlabs
        with patch.object(elevenlabs,'request_api',return_value=b'ID3fixture') as call:
            elevenlabs.render('not-real-key','Русская книга.',self.root/'el.mp3','voice123',.9)
            args=call.call_args.args;self.assertEqual(args[0],'not-real-key');self.assertIn('/v1/text-to-speech/voice123?',args[1]);self.assertEqual(args[2]['model_id'],'eleven_multilingual_v2');self.assertEqual(args[2]['voice_settings']['speed'],.9)
        with patch.object(elevenlabs,'request_api',return_value=json.dumps({'voices':[{'voice_id':'v1','name':'Голос'}],'has_more':False}).encode()) as call:
            self.assertEqual(elevenlabs.list_voices('key')[0]['id'],'v1');self.assertIn('/v2/voices?',call.call_args.args[1])
    def test_restart_recovery(self):
        id=self.textbook();self.service.update(id,state='rendering',done=2,total=4)
        restarted=Service(self.root,self.root/'models');self.assertEqual(restarted.get(id)['state'],'queued');self.assertEqual(restarted.get(id)['done'],2)
        restarted.update(id,provider='elevenlabs',state='rendering');self.assertEqual(Service(self.root).get(id)['state'],'paused')
    def test_storage_cap_and_cleaning(self):
        with patch.dict(os.environ,MAX_STORAGE_MB='0'):self.assertEqual(self.client.post('/api/books',data={'text':'текст '*10},headers=self.headers).status_code,400)
        text=clean_text('Стра-\nница\n\n12\n\nСледующий абзац.');self.assertIn('Страница',text);self.assertNotIn('12',text)
        self.assertTrue(all(len(s)<=1300 for s in chunks('я'*5000)))
    def test_sample_is_separate(self):
        id=self.textbook('Проверка голоса. '*100);self.service.engine.available=lambda _:True
        r=self.client.post('/api/books/'+id+'/sample',json={},headers=self.headers);self.assertEqual(r.status_code,201);self.assertNotEqual(r.json['id'],id);self.assertEqual(self.service.get(id)['state'],'draft');self.assertLessEqual(len(self.service.get(r.json['id'])['text']),400)

class DeploymentTest(unittest.TestCase):
    def test_registration_and_https_route(self):
        project=ROOT.parent/'deploy-panel'/'app.py';spec=importlib.util.spec_from_file_location('panel',project);panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
        spec=importlib.util.spec_from_file_location('register',ROOT/'src/register_gitdeck.py');reg=importlib.util.module_from_spec(spec);spec.loader.exec_module(reg)
        config=panel.load_config(ROOT.parent/'deploy-panel/config.example.json');projects,changed=reg.add_project(panel,config);self.assertTrue(changed);self.assertEqual(projects[-1]['subdir'],'bookvoice');self.assertIn('requirements.txt',projects[-1]['paths']);self.assertFalse(reg.add_project(panel,dict(config,projects=projects))[1])
        spec=importlib.util.spec_from_file_location('https',ROOT/'src/connect_https.py');https=importlib.util.module_from_spec(spec);spec.loader.exec_module(https)
        original='existing.test {\n reverse_proxy stable-web:80\n}\n';route=https.route(original,'books.vano.sbena.net');self.assertIn(original.strip(),route);self.assertIn('bookvoice-web:8140',route);self.assertEqual(https.route(route,'books.vano.sbena.net'),route)
        with self.assertRaises(ValueError):https.route('x {\n reverse_proxy web:80\n}', 'books.vano.sbena.net')
if __name__=='__main__':unittest.main()
