import base64
import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZipFile

import pandas as pd

from backup import snapshot, backup_date, run_backup, due_time, BRASILIA, SLOTS
from core import salvar, FONTES, conectar


class BackupTests(unittest.TestCase):
    def test_two_slots_oldest_rotation_schedule_and_recovery(self):
        config = {"token": "test", "repository": "owner/private", "branch": "main"}
        remote = {}
        def api(cfg, endpoint, body=None, raw=False):
            if not endpoint:
                return {"private": True}
            name = endpoint.split("?", 1)[0].removeprefix("contents/")
            if body is not None:
                if name in remote:
                    self.assertEqual(body["sha"], hashlib.sha1(f"blob {len(remote[name])}\0".encode() + remote[name]).hexdigest())
                remote[name] = base64.b64decode(body["content"])
                return {"content": {"sha": "saved"}}
            if name not in remote:
                raise HTTPError("test", 404, "Not found", {}, None)
            return remote[name] if raw else {"sha": hashlib.sha1(f"blob {len(remote[name])}\0".encode() + remote[name]).hexdigest()}

        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "source.sqlite3"
            salvar(FONTES[0], "test", "test", pd.DataFrame({"id": [1]}), db)
            with conectar(db) as conn:
                conn.execute("CREATE TABLE otd_validacoes (id INTEGER, justificativa TEXT)")
                conn.execute("INSERT INTO otd_validacoes VALUES (1, 'Conferido')")
            day = datetime(2026, 10, 5, 20, tzinfo=BRASILIA)
            with patch("backup.github", side_effect=api):
                run_backup(config, db, day)
                self.assertEqual(set(remote), {SLOTS[0]})
                run_backup(config, db, day + timedelta(minutes=1))
                self.assertEqual(len(remote), 1)
                run_backup(config, db, day + timedelta(days=1))
                second = remote[SLOTS[1]]
                run_backup(config, db, day + timedelta(days=2))
                self.assertEqual(set(remote), set(SLOTS))
                self.assertEqual(remote[SLOTS[1]], second)
                self.assertEqual(backup_date(remote[SLOTS[0]]), day + timedelta(days=2))
                # Suspenso na hora agendada: ao voltar no dia seguinte, executa o pendente.
                run_backup(config, db, day + timedelta(days=4, hours=-10))
                self.assertEqual(backup_date(remote[SLOTS[1]]), day + timedelta(days=4, hours=-10))
            with ZipFile(BytesIO(remote[SLOTS[0]])) as archive:
                restored = sqlite3.connect(":memory:")
                restored.deserialize(archive.read("regras_estadia.sqlite3"))
                self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(restored.execute("SELECT justificativa FROM otd_validacoes").fetchone()[0], "Conferido")
                self.assertEqual(restored.execute("SELECT COUNT(*) FROM importacoes").fetchone()[0], 1)
                restored.close()
            self.assertEqual(due_time(day - timedelta(minutes=1)), day - timedelta(days=1))
            self.assertEqual(due_time(day), day)

    def test_empty_or_public_destination_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "empty.sqlite3"
            with conectar(db):
                pass
            with self.assertRaises(ValueError):
                snapshot(db)
            with patch("backup.github", return_value={"private": False}) as network:
                with self.assertRaises(ValueError):
                    run_backup({"token": "test", "repository": "public", "branch": "main"}, db)
                self.assertEqual(network.call_count, 1)
