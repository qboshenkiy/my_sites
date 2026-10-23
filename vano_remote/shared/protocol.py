"""Vano Remote v1: relay-independent, authenticated end-to-end channel."""
import base64
import hashlib
import json
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def derive(label, secret):
    return hashlib.sha256(label.encode() + secret.encode()).digest()

def seal(key, value):
    nonce = os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, json.dumps(value, separators=(',', ':')).encode(), b'vano1')

def unseal(key, packet):
    if not 28 <= len(packet) <= 4_000_000:
        raise ValueError('Invalid packet size')
    return json.loads(AESGCM(key).decrypt(packet[:12], packet[12:], b'vano1'))

class Channel:
    def __init__(self, secret, role):
        self.base = derive('e2e:', secret)
        self.role = role
        self.key = None
        self.local = os.urandom(32).hex()
        self.sent = self.received = 0

    def hello(self):
        return seal(self.base, {'type': 'hello', 'role': self.role, 'nonce': self.local})

    def receive(self, packet):
        if self.key is None:
            hello = unseal(self.base, packet)
            peer = 'android' if self.role == 'windows' else 'windows'
            if hello.get('type') != 'hello' or hello.get('role') != peer:
                raise ValueError('Unexpected handshake')
            remote = bytes.fromhex(hello['nonce'])
            if len(remote) != 32:
                raise ValueError('Invalid challenge')
            local = bytes.fromhex(self.local)
            challenges = local + remote if self.role == 'windows' else remote + local
            self.key = hashlib.sha256(self.base + challenges).digest()
            return None
        value = unseal(self.key, packet)
        peer = 'android' if self.role == 'windows' else 'windows'
        if value.get('role') != peer or not isinstance(value.get('seq'), int) or value['seq'] <= self.received:
            raise ValueError('Replayed or reflected packet')
        self.received = value['seq']
        return value

    def send(self, value):
        if self.key is None:
            raise ValueError('Handshake incomplete')
        self.sent += 1
        return seal(self.key, {**value, 'seq': self.sent, 'role': self.role})
