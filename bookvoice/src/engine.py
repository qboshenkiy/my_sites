"""Offline Russian narration and bounded document extraction."""
import os,re,subprocess,wave,zipfile
from pathlib import Path

VOICES={'denis':('Денис','ru_RU-denis-medium'),'dmitri':('Дмитрий','ru_RU-dmitri-medium')}
MAX_TEXT=500_000

def clean_text(text):
    text=text.replace('\r\n','\n').replace('\r','\n').replace('\x00','').replace('\u00ad','')
    text=re.sub(r'(\w)-\n(?=\w)',r'\1',text)
    text=re.sub(r'(?m)^\s*\d{1,5}\s*$','',text)
    text=re.sub(r'[ \t]+',' ',text)
    return re.sub(r'\n{3,}','\n\n',text).strip()

def extract(path):
    path=Path(path)
    if path.suffix=='.docx':
        with zipfile.ZipFile(path) as z:
            if len(z.infolist())>5000 or sum(i.file_size for i in z.infolist())>100*1024**2:raise ValueError('Слишком большой распакованный Word-файл.')
        from docx import Document
        from docx.text.paragraph import Paragraph
        doc=Document(path);blocks=[]
        for block in doc.iter_inner_content():
            blocks.append(block.text if isinstance(block,Paragraph) else '\n'.join(' · '.join(c.text for c in row.cells) for row in block.rows))
        text='\n\n'.join(blocks)
    elif path.suffix=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(path)
        if reader.is_encrypted:raise ValueError('PDF защищён паролем. Сначала сохраните незашифрованную копию.')
        if len(reader.pages)>1500:raise ValueError('В PDF больше 1500 страниц. Разделите книгу на тома.')
        # Poppler runs outside the web process, with a bounded execution time.
        text=subprocess.run(['pdftotext','-enc','UTF-8',str(path),'-'],capture_output=True,check=True,timeout=90).stdout.decode('utf-8')
    elif path.suffix=='.doc':
        text=subprocess.run(['antiword','-m','UTF-8.txt',str(path)],capture_output=True,check=True,timeout=90).stdout.decode('utf-8')
    else:raise ValueError('Поддерживаются PDF, DOCX и DOC.')
    text=clean_text(text)
    if len(text)<20:raise ValueError('Не найден читаемый текст. Возможно, это PDF-скан: распознайте его OCR и загрузите снова.')
    if len(text)>MAX_TEXT:raise ValueError('Больше 500 000 символов. Разделите книгу на несколько файлов.')
    return text

def chunks(text,limit=1300):
    """Keep paragraphs/sentences, but always bound a segment even for unpunctuated text."""
    result=[];buffer=''
    for paragraph in text.split('\n\n'):
        units=re.split(r'(?<=[.!?…])\s+',paragraph.strip())
        for unit in units:
            while len(unit)>limit:
                at=unit.rfind(' ',0,limit+1)
                if at<limit//3:at=limit
                if buffer:result.append(buffer);buffer=''
                result.append(unit[:at].strip());unit=unit[at:].strip()
            if len(buffer)+len(unit)+2>limit:result.append(buffer.strip());buffer=''
            buffer+=((' ' if buffer else '')+unit)
        if buffer:buffer+='\n\n'
    if buffer.strip():result.append(buffer.strip())
    return [s for s in result if s]

class Narrator:
    def __init__(self,model_dir):self.model_dir=Path(model_dir);self.voice=None;self.loaded=None
    def available(self,key):return (self.model_dir/(VOICES[key][1]+'.onnx')).is_file() and (self.model_dir/(VOICES[key][1]+'.onnx.json')).is_file()
    def render(self,text,path,voice,speed,pause):
        from piper import PiperVoice,SynthesisConfig
        if not self.available(voice):raise ValueError('Голос ещё не установлен. На сервере выполните загрузку моделей из инструкции.')
        if self.loaded!=voice:
            self.voice=None
            self.voice=PiperVoice.load(str(self.model_dir/(VOICES[voice][1]+'.onnx')))
            self.loaded=voice
        wav=Path(path).with_suffix('.wav')
        try:
            config=SynthesisConfig(length_scale=1/float(speed))
            initialized=False
            with wave.open(str(wav),'wb') as out:
                # Paragraph pauses are explicit; sentence prosody is produced by the model.
                for paragraph in text.split('\n\n'):
                    if not paragraph.strip():continue
                    for audio in self.voice.synthesize(paragraph,syn_config=config):
                        if not initialized:
                            out.setnchannels(audio.sample_channels);out.setsampwidth(audio.sample_width);out.setframerate(audio.sample_rate);initialized=True
                        out.writeframes(audio.audio_int16_bytes)
                    if initialized:out.writeframes(b'\x00\x00'*int(out.getframerate()*float(pause)))
            subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),'-codec:a','libmp3lame','-b:a','64k',str(path)],check=True,timeout=120)
        finally:wav.unlink(missing_ok=True)
