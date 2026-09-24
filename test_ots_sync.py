import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import carregar, historico
from ots_sync import COLUMNS, parse_payload, status, sync


def payload(code="001"):
    row = dict.fromkeys(COLUMNS, "")
    row.update(id=1, codigo_monitoramento=code, tipo_registro="ORIGINAL", previsao_carga="2026-09-24", data_hora_registro="2026-09-24T11:31:00-03:00")
    return {"schema": "ots_otd_backup_v1", "records": 1, "rows": [row], "generated_at": "2026-09-24T11:31:00-03:00"}


class SyncTests(unittest.TestCase):
    def test_columns_dates_and_code(self):
        df = parse_payload(payload())
        self.assertEqual(list(df.columns), list(COLUMNS.values()))
        self.assertEqual(df.iloc[0]["Codigo de Monitoramento"], "001")
        self.assertEqual(df.iloc[0]["Previsao Carga"], "24/09/2026")

    def test_invalid_and_duplicate_ids(self):
        for p in [{}, {**payload(), "rows": []}, {**payload(), "records": 4}, {**payload(), "records": 2, "rows": payload()["rows"] * 2}]:
            with self.assertRaises(ValueError):
                parse_payload(p)

    def test_sync_repeat_revert_and_failure_preserves_data(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.sqlite3"
            with patch("ots_sync.download_payload", return_value=payload()) as fetch:
                self.assertEqual(sync("token", path=db), (1, True))
                self.assertEqual(sync("token", path=db), (1, False))
                fetch.return_value = payload("002")
                sync("token", path=db)
                fetch.return_value = payload()
                sync("token", path=db)
                self.assertEqual(len(historico(db)), 2)
                self.assertEqual(carregar(status(db)[0], db).iloc[0]["Codigo de Monitoramento"], "001")
                fetch.return_value = {}
                with self.assertRaises(ValueError):
                    sync("token", path=db)
                self.assertEqual(len(historico(db)), 2)
