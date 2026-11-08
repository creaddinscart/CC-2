# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2026 Creaddinscart Teams & CC Team
# SPDX-License-Identifier: MPL-2.0


from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct

PBKDF2_ITERATIONS = 120_000
KEY_LEN = 32
NONCE_LEN = 12
TAG_LEN = 32

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except Exception:
    AESGCM = None


class CryptoError(Exception):
    pass


def has_aes_gcm() -> bool:
    return AESGCM is not None


def new_salt() -> bytes:
    return os.urandom(16)


def derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=KEY_LEN
    )


def auth_token(password: str, salt: bytes) -> str:
    material = salt + b"|cc2-auth"
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), material, PBKDF2_ITERATIONS, dklen=KEY_LEN
    )
    return digest.hex()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(
            key, b"cc2/ctr" + nonce + struct.pack(">I", counter), hashlib.sha256
        ).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _xor(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream))


def encrypt(key: bytes, plaintext: bytes, prefer_aes: bool = True) -> str:
    nonce = os.urandom(NONCE_LEN)
    if AESGCM is not None and prefer_aes:
        sealed = AESGCM(key).encrypt(nonce, plaintext, None)
        raw = b"\x02" + nonce + sealed
    else:
        ciphertext = _xor(plaintext, _keystream(key, nonce, len(plaintext)))
        tag = hmac.new(key, b"cc2/mac" + nonce + ciphertext, hashlib.sha256).digest()
        raw = b"\x01" + nonce + tag + ciphertext
    return base64.b64encode(raw).decode("ascii")


def decrypt(key: bytes, token: str) -> bytes:
    raw = base64.b64decode(token, validate=False)
    if len(raw) < 1 + NONCE_LEN:
        raise CryptoError("ciphertext is truncated")
    version = raw[0]
    nonce = raw[1 : 1 + NONCE_LEN]
    body = raw[1 + NONCE_LEN :]

    if version == 2:
        if AESGCM is None:
            raise CryptoError(
                "this peer sent AES-GCM ciphertext; install `cryptography` "
                "(pip install cryptography) to read it"
            )
        try:
            return AESGCM(key).decrypt(nonce, body, None)
        except Exception as exc:
            raise CryptoError("AES-GCM authentication failed (wrong password?)") from exc

    if version == 1:
        if len(body) < TAG_LEN:
            raise CryptoError("ciphertext is truncated")
        tag, ciphertext = body[:TAG_LEN], body[TAG_LEN:]
        expected = hmac.new(
            key, b"cc2/mac" + nonce + ciphertext, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(tag, expected):
            raise CryptoError("HMAC authentication failed (wrong password or tampered data)")
        return _xor(ciphertext, _keystream(key, nonce, len(ciphertext)))

    raise CryptoError(f"unknown ciphertext version: {version}")


def seal_json(key: bytes, obj: dict, prefer_aes: bool = True) -> str:
    import json

    return encrypt(
        key,
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        prefer_aes=prefer_aes,
    )


def open_json(key: bytes, token: str) -> dict:
    import json

    data = json.loads(decrypt(key, token).decode("utf-8"))
    if not isinstance(data, dict):
        raise CryptoError("bad payload")
    return data
