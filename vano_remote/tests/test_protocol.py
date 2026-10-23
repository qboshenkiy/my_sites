import unittest
from cryptography.exceptions import InvalidTag
from shared.protocol import Channel

SECRET='p7hzHaISfEWBrnQ0tHV4mB1LHJf0RYvCXIX1sp5fq9c'

def connected():
    w,a=Channel(SECRET,'windows'),Channel(SECRET,'android')
    w.receive(a.hello());a.receive(w.hello())
    return w,a

class ProtocolTests(unittest.TestCase):
    def test_bidirectional(self):
        w,a=connected()
        self.assertEqual(a.receive(w.send({'type':'frame','jpeg':'test'}))['jpeg'],'test')
        self.assertEqual(w.receive(a.send({'type':'click','x':.5}))['x'],.5)

    def test_wrong_pairing_secret(self):
        with self.assertRaises(InvalidTag): Channel('wrong','android').receive(Channel(SECRET,'windows').hello())

    def test_tampered(self):
        w,a=connected();p=bytearray(w.send({'type':'click'}));p[-1]^=1
        with self.assertRaises(InvalidTag):a.receive(bytes(p))

    def test_replay(self):
        w,a=connected();p=w.send({'type':'click'});a.receive(p)
        with self.assertRaises(ValueError):a.receive(p)

    def test_previous_session(self):
        w,a=connected();p=w.send({'type':'click'});w2,a2=connected()
        with self.assertRaises(InvalidTag):a2.receive(p)

    def test_reflection(self):
        w,a=connected();p=w.send({'type':'click'})
        with self.assertRaises(ValueError):w.receive(p)

if __name__=='__main__':unittest.main()
