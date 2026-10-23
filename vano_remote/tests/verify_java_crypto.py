"""Optional interoperability test against actual Link.java, not a reimplementation.

Usage: python tests/verify_java_crypto.py JAVA_HOME ANDROID_JAR JSON_JAR OKHTTP_JAR OKIO_JAR TEMP_DIR
Requires Python cryptography and a JDK containing javac. Download JSON Java from Maven Central.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.protocol import derive,seal,unseal

def main():
    java,android,js,okhttp,okio,out=sys.argv[1:]
    root=Path(__file__).resolve().parents[1]
    Path(out).mkdir(parents=True,exist_ok=True)
    cp=os.pathsep.join([android,js,okhttp,okio])
    subprocess.run([str(Path(java)/'bin/javac.exe'),'-encoding','UTF-8','-cp',cp,'-d',out,str(root/'android/app/src/main/java/net/sbena/vano/remote/Link.java'),str(root/'tests/JvmCryptoProbe.java')],check=True)
    # Do not include Android's stub android.jar on the runtime classpath.
    cp=os.pathsep.join([out,js,okhttp,okio])
    secret='test-secret-'*5;key=derive('e2e:',secret)
    packet=seal(key,{'type':'probe','value':'Привет'})
    result=subprocess.check_output([str(Path(java)/'bin/java.exe'),'-Dfile.encoding=UTF-8','-Dstdout.encoding=UTF-8','-cp',cp,'net.sbena.vano.remote.JvmCryptoProbe',key.hex(),base64.b64encode(packet).decode(),secret]).decode('utf-8').splitlines()
    assert json.loads(result[0])['value']=='Привет'
    assert unseal(key,base64.b64decode(result[1]))['value']=='Привет'
    assert result[2]==key.hex()
    print('PASS: Python -> Android Java decrypt; Android Java -> Python decrypt; key derivation')

if __name__=='__main__':main()
