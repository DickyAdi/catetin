"""age encryption of the nightly backup.

A backup is a full copy of every user's data, `raw_text` included, and no
`/hapusakun` can reach a copy that has already been made — so the interesting
assertions here are the negative ones: that plaintext does not survive on
disk, and that a failure to encrypt leaves nothing readable behind rather
than quietly degrading to an unencrypted backup nobody notices.

The keypair is generated in-process; nothing here touches a real host, a real
`.env`, or the `age` CLI.
"""

import sqlite3

import pyrage
import pytest
from pyrage import x25519

from catetin.adapters.inbound.scheduler import jobs
from catetin.adapters.outbound.backup.encryption import (
    BackupEncryptionError,
    encrypt_file,
    encrypted_name,
)

AGE_MAGIC = b"age-encryption.org/v1"


@pytest.fixture
def identity() -> x25519.Identity:
    return x25519.Identity.generate()


@pytest.fixture
def recipient(identity: x25519.Identity) -> str:
    return str(identity.to_public())


def _make_sqlite_file(path, secret: bytes = b"jual ayam geprek 50rb") -> None:
    """A database carrying a recognisable piece of "chat" in a row, so the
    tests can assert on plaintext leakage rather than on file bytes."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE transactions (raw_text TEXT)")
    conn.execute("INSERT INTO transactions VALUES (?)", (secret.decode(),))
    conn.commit()
    conn.close()


# --- the encryption module -------------------------------------------------


def test_encrypted_name_appends_rather_than_replaces(tmp_path) -> None:
    """`...db.age`, not `....age` — the file stays recognisable as the SQLite
    backup it is, and the retention glob still matches it."""
    assert encrypted_name(tmp_path / "catetin-2026-08-15-210000.db").name == (
        "catetin-2026-08-15-210000.db.age"
    )


def test_encrypt_file_round_trips_through_the_matching_identity(
    tmp_path, identity: x25519.Identity, recipient: str
) -> None:
    source = tmp_path / "catetin.db"
    source.write_bytes(b"jual ayam geprek 50rb")
    dest = tmp_path / "catetin.db.age"

    encrypt_file(source, dest, recipient)

    assert dest.read_bytes().startswith(AGE_MAGIC)
    assert pyrage.decrypt(dest.read_bytes(), [identity]) == b"jual ayam geprek 50rb"


def test_encrypt_file_rejects_a_malformed_recipient(tmp_path) -> None:
    """A typo'd `CATETIN_BACKUP_AGE_RECIPIENT` must fail loudly at the first
    backup, not produce something unreadable at restore time."""
    source = tmp_path / "catetin.db"
    source.write_bytes(b"x")

    with pytest.raises(BackupEncryptionError, match="not a valid age recipient"):
        encrypt_file(source, tmp_path / "out.age", "age1-obviously-not-a-key")


def test_a_different_identity_cannot_decrypt(
    tmp_path, recipient: str
) -> None:
    source = tmp_path / "catetin.db"
    source.write_bytes(b"jual ayam geprek 50rb")
    dest = tmp_path / "catetin.db.age"
    encrypt_file(source, dest, recipient)

    with pytest.raises(pyrage.DecryptError):
        pyrage.decrypt(dest.read_bytes(), [x25519.Identity.generate()])


# --- the backup job --------------------------------------------------------


async def test_run_backup_without_a_recipient_stays_plaintext(tmp_path) -> None:
    """Unset is the dev/test default and must not change behaviour."""
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)

    dest = await jobs.run_backup(
        f"sqlite+aiosqlite:///{db_path}", tmp_path / "backups", "2026-08-15", keep_n=7
    )

    assert dest.suffix == ".db"
    assert not dest.name.endswith(".age")


async def test_run_backup_with_a_recipient_leaves_only_ciphertext(
    tmp_path, identity: x25519.Identity, recipient: str
) -> None:
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)
    backup_dir = tmp_path / "backups"

    dest = await jobs.run_backup(
        f"sqlite+aiosqlite:///{db_path}",
        backup_dir,
        "2026-08-15",
        keep_n=7,
        age_recipient=recipient,
    )

    assert dest.name.endswith(".db.age")
    assert dest.read_bytes().startswith(AGE_MAGIC)
    # The plaintext `VACUUM INTO` wrote must be gone, not merely renamed.
    assert list(backup_dir.iterdir()) == [dest]
    assert b"ayam geprek" not in dest.read_bytes()
    # ...and the ciphertext really is the database.
    restored = tmp_path / "restored.db"
    restored.write_bytes(pyrage.decrypt(dest.read_bytes(), [identity]))
    conn = sqlite3.connect(restored)
    try:
        assert conn.execute("SELECT raw_text FROM transactions").fetchone()[0] == (
            "jual ayam geprek 50rb"
        )
    finally:
        conn.close()


async def test_failed_encryption_leaves_no_plaintext_behind(tmp_path) -> None:
    """Fail closed. A missing backup is a visible problem; an unnoticed
    plaintext copy of everyone's data is a quiet breach."""
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)
    backup_dir = tmp_path / "backups"

    with pytest.raises(BackupEncryptionError):
        await jobs.run_backup(
            f"sqlite+aiosqlite:///{db_path}",
            backup_dir,
            "2026-08-15",
            keep_n=7,
            age_recipient="age1-not-a-real-key",
        )

    assert list(backup_dir.iterdir()) == []


async def test_pruning_spans_both_namings(tmp_path, recipient: str) -> None:
    """A host switched to encrypted backups must still prune the plaintext
    ones it wrote yesterday, or retention silently doubles."""
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    for day in (1, 2, 3):
        (backup_dir / f"catetin-2026-08-0{day}-210000.db").write_bytes(b"old plaintext")

    await jobs.run_backup(
        f"sqlite+aiosqlite:///{db_path}",
        backup_dir,
        "2026-08-10",
        keep_n=2,
        age_recipient=recipient,
    )

    remaining = sorted(p.name for p in backup_dir.iterdir())
    assert len(remaining) == 2
    assert remaining[-1].endswith(".db.age")  # today's, newest


async def test_encrypted_run_does_not_clobber_a_plaintext_run(
    tmp_path, recipient: str
) -> None:
    """Both namings are checked when picking a destination, so flipping the
    recipient on cannot overwrite an artifact written under the other one."""
    db_path = tmp_path / "catetin.db"
    _make_sqlite_file(db_path)
    backup_dir = tmp_path / "backups"
    url = f"sqlite+aiosqlite:///{db_path}"

    first = await jobs.run_backup(url, backup_dir, "2026-08-15", keep_n=7)
    second = await jobs.run_backup(
        url, backup_dir, "2026-08-15", keep_n=7, age_recipient=recipient
    )

    assert first.exists()
    assert second.exists()
    assert second.name != encrypted_name(first).name
