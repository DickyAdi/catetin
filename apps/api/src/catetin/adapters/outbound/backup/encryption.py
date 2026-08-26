"""age encryption for the nightly database backup.

The threat this addresses is narrow and worth stating: the backup file is a
full copy of every user's transactions, `raw_text` included, sitting on the
same 2 vCPU box as the app. Anyone who gets the box gets the lot, and a
`/hapusakun` cannot reach into a copy that has already been made.

So backups are encrypted to an **age recipient** — an X25519 public key. The
public key lives in `.env` on the VPS (`CATETIN_BACKUP_AGE_RECIPIENT`) and can
only encrypt; the matching identity stays offline and never touches the host.
An attacker who takes the VPS therefore takes ciphertext they cannot open,
and restoring is a deliberate act performed somewhere else.

Implementation note: this uses the `pyrage` bindings (to `rage`, the Rust age
implementation) rather than shelling out to the `age` CLI. The output is
plain age v1 either way, so a backup written here decrypts with the stock
binary and nothing about the recovery path depends on this module:

    age --decrypt -i identity.txt -o catetin.db catetin-<date>-<time>.db.age

A library call also means no PATH assumption on the host, no subprocess
failure modes, and a path that CI actually exercises.
"""

from __future__ import annotations

from pathlib import Path

import pyrage  # type: ignore[import-untyped]
from pyrage import x25519  # type: ignore[import-untyped]

AGE_SUFFIX = ".age"


class BackupEncryptionError(RuntimeError):
    """Raised when a backup could not be encrypted.

    The caller is expected to destroy the plaintext and let the run fail
    rather than keep an unencrypted copy of the database on disk — a backup
    that silently falls back to plaintext is worse than a missing one,
    because nobody notices.
    """


def encrypted_name(path: Path) -> Path:
    """`catetin-2026-08-27-210000.db` -> `...db.age` (suffix appended, not
    replaced, so the file is still recognisable as the SQLite backup it is)."""
    return path.with_name(path.name + AGE_SUFFIX)


def encrypt_file(source: Path, dest: Path, recipient: str) -> None:
    """Encrypt `source` to `dest` for `recipient` (an `age1...` public key).

    Reads the whole file into memory: a VACUUM'd SQLite backup for this
    workload is single-digit MB against a 4 GB host, and streaming would buy
    nothing but complexity here.
    """
    try:
        key = x25519.Recipient.from_str(recipient)
    except Exception as exc:  # pyrage raises its own opaque error types
        raise BackupEncryptionError(
            f"CATETIN_BACKUP_AGE_RECIPIENT is not a valid age recipient: {exc}"
        ) from exc

    try:
        ciphertext = pyrage.encrypt(source.read_bytes(), [key])
    except Exception as exc:
        raise BackupEncryptionError(f"failed to encrypt {source.name}: {exc}") from exc

    dest.write_bytes(ciphertext)
