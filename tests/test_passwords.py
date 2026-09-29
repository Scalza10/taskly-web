from taskly import passwords


def test_a_hash_verifies_only_its_own_password():
    stored = passwords.hash_password("purple-lamp-river")
    assert passwords.verify_password("purple-lamp-river", stored)
    assert not passwords.verify_password("purple-lamp-rivers", stored)


def test_the_hash_records_its_parameters_and_a_fresh_salt():
    first = passwords.hash_password("same password")
    second = passwords.hash_password("same password")
    scheme, n, r, p, salt, digest = first.split("$")
    assert (scheme, int(r), int(p)) == ("scrypt", 8, 1)
    assert int(n) == passwords.N
    assert len(bytes.fromhex(salt)) == 16
    assert first != second


def test_old_hashes_still_verify_after_the_cost_changes(monkeypatch):
    stored = passwords.hash_password("keep working")
    monkeypatch.setattr(passwords, "N", passwords.N * 2)
    assert passwords.verify_password("keep working", stored)


def test_malformed_hashes_never_verify():
    for stored in ["", "plain-password", "bcrypt$1$2$3$aa$bb", "scrypt$x$8$1$aa$bb", "scrypt$16$8$1$zz$bb"]:
        assert not passwords.verify_password("anything", stored)


def test_production_cost():
    # conftest lowers N for speed; the module's own default must stay 2**15.
    import importlib

    fresh = importlib.reload(passwords)
    try:
        assert (fresh.N, fresh.R, fresh.P) == (2**15, 8, 1)
    finally:
        importlib.reload(passwords)
