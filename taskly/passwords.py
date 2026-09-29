"""Password hashing with stdlib scrypt.

Stored as scrypt$n$r$p$salt_hex$hash_hex, so the cost can be raised later without
breaking existing passwords: each hash is checked with its own parameters."""

import hashlib
import hmac
import secrets
import threading

N, R, P = 2**15, 8, 1
MIN_LENGTH = 10

# Each scrypt takes 32 MiB and releases the GIL: 40 at once would commit ~1.3 GiB on a shared VM.
_SLOTS = threading.BoundedSemaphore(4)


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    # scrypt needs 128 * r * n bytes (32 MiB at the defaults), just over OpenSSL's default limit.
    # surrogatepass: JSON can carry a lone surrogate, which plain encode() refuses.
    data = password.encode("utf-8", "surrogatepass")
    with _SLOTS:
        return hashlib.scrypt(data, salt=salt, n=n, r=r, p=p, maxmem=256 * r * n, dklen=32)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    return f"scrypt${N}${R}${P}${salt.hex()}${_scrypt(password, salt, N, R, P).hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _scrypt(password, bytes.fromhex(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except ValueError:
        return False


# Checked when a username doesn't exist, so a wrong name takes as long as a wrong password.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
