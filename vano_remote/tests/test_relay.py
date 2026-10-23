import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from aiohttp import web, ClientSession, WSServerHandshakeError
from shared.protocol import Channel,derive

class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        os.environ['DATA_DIR']=self.temp.name
        spec=importlib.util.spec_from_file_location('test_relay_app',Path(__file__).resolve().parents[1]/'server/app.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.runner=web.AppRunner(self.module.app);await self.runner.setup()
        site=web.TCPSite(self.runner,'127.0.0.1',0);await site.start()
        self.url='http://127.0.0.1:'+str(site._server.sockets[0].getsockname()[1])
        self.client=ClientSession()
        self.room='a'*32;self.secret='test secret'*5
        self.headers={'Authorization':'Bearer '+derive('auth:',self.secret).hex()}

    async def asyncTearDown(self):
        await self.client.close();await self.runner.cleanup();self.module.db.close();self.temp.cleanup()

    async def connect(self,role,headers=None):
        return await self.client.ws_connect(self.url+'/ws/'+self.room+'/'+role,headers=headers or self.headers)

    async def test_unknown_android_rejected(self):
        with self.assertRaises(WSServerHandshakeError) as e:await self.connect('android')
        self.assertEqual(e.exception.status,401)

    async def test_auth_and_duplicate(self):
        w=await self.connect('windows')
        with self.assertRaises(WSServerHandshakeError) as e:await self.connect('windows')
        self.assertEqual(e.exception.status,409)
        with self.assertRaises(WSServerHandshakeError) as e:await self.connect('android',{'Authorization':'Bearer '+'0'*64})
        self.assertEqual(e.exception.status,401)
        await w.close()

    async def test_encrypted_relay_and_disconnect(self):
        w=await self.connect('windows');a=await self.connect('android')
        self.assertEqual((await w.receive_json())['event'],'paired')
        self.assertEqual((await a.receive_json())['event'],'paired')
        wc,ac=Channel(self.secret,'windows'),Channel(self.secret,'android')
        await w.send_bytes(wc.hello());await a.send_bytes(ac.hello())
        ac.receive((await a.receive()).data);wc.receive((await w.receive()).data)
        packet=ac.send({'type':'click','x':.7})
        await a.send_bytes(packet)
        message=await w.receive()
        self.assertEqual(message.data,packet)
        self.assertEqual(wc.receive(message.data)['x'],.7)
        await a.close()
        msg=await asyncio.wait_for(w.receive(),3)
        self.assertTrue(w.closed)

if __name__=='__main__':unittest.main()
