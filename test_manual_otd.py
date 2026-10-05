import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from rules import analyze
from manual_otd import review_queue, save_reviews, apply_reviews


class ManualOTDTests(unittest.TestCase):
    def test_persistent_approval_revoke_source_change_and_permissions(self):
        ots = pd.DataFrame([{"ID": 1, "Codigo de Monitoramento": "1234567", "Data/Hora do Registro": "01/09/2026", "Previsao Carga": "01/09/2026", "Agendamento Carga": "01/09/2026", "Data Limite": "02/09/2026", "Agenda GFL": "03/09/2026"}])
        lcte = pd.DataFrame([{"Notas fiscais": "1", "Placa tração": "ABC1D23", "Observação": "1234567"}])
        stays = pd.DataFrame([{"nf": "1", "placa_norm": "ABC1D23", "chegada_origem": "01/09/2026", "chegada_destino": "03/09/2026"}])
        result = analyze(lcte, ots, stays)
        user = {"username": "operador", "role": "OPERACIONAL"}
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "test.sqlite3"
            queue = review_queue(ots, result, db)
            edited = queue.copy()
            edited["Dentro da regra"] = True
            with self.assertRaises(ValueError):
                save_reviews(edited, queue, user, db)
            edited["Justificativa"] = "Cliente confirmou indisponibilidade de grade"
            with self.assertRaises(ValueError):
                save_reviews(edited, queue, {**user, "role": "CONSULTA"}, db)
            self.assertEqual(save_reviews(edited, queue, user, db), 1)
            loaded = review_queue(ots, result, db)
            self.assertTrue(loaded.iloc[0]["Dentro da regra"])
            updated = apply_reviews(result, loaded).iloc[0]
            self.assertEqual(updated["OTD 2"], "Dentro do prazo")
            self.assertEqual(updated["OTD 2 automático"], "Fora do prazo")
            self.assertEqual(updated["Atendeu todas as regras"], "Sem informação")
            self.assertIn("operador", updated["Motivo da classificação"])
            changed = result.copy()
            changed["Chegada no Destino"] = "04/09/2026"
            self.assertFalse(review_queue(ots, changed, db).iloc[0]["Dentro da regra"])
            self.assertEqual(apply_reviews(changed, review_queue(ots, changed, db)).iloc[0]["OTD 2"], "Fora do prazo")
            revoked = loaded.copy()
            revoked["Dentro da regra"] = False
            revoked["Justificativa"] = "Revisão: manter atraso"
            save_reviews(revoked, loaded, user, db)
            self.assertEqual(apply_reviews(result, review_queue(ots, result, db)).iloc[0]["OTD 2"], "Fora do prazo")
            self.assertEqual(len(review_queue(ots, None, db)), 1)

    def test_overview_manual_approval_moves_card_without_lcte(self):
        from streamlit.testing.v1 import AppTest
        from core import FONTES
        ots = pd.DataFrame([{"ID": 1, "Codigo de Monitoramento": "1234567", "Data/Hora do Registro": "01/09/2026", "Previsao Carga": "01/09/2026", "Agendamento Carga": "01/09/2026", "Data Limite": "02/09/2026", "Agenda GFL": "03/09/2026"}])
        history = pd.DataFrame([{"id": 1, "fonte": FONTES[0], "arquivo": "teste", "criado_em": "2026-09-01", "quantidade": 1}])
        with tempfile.TemporaryDirectory() as directory:
            queue = review_queue(ots, None, Path(directory) / "test.sqlite3")
        queue["Dentro da regra"] = True
        queue["Justificativa"] = "Verificado"
        with patch("core.historico", return_value=history), patch("core.carregar", return_value=ots), patch("ots_sync.status", return_value=None), patch("manual_otd.review_queue", return_value=queue):
            app = AppTest.from_file("app.py", default_timeout=30)
            app.session_state["authenticated"] = True
            app.session_state["auth_user"] = {"username": "teste", "name": "Teste", "role": "CONSULTA"}
            app.session_state["performance_menu"] = "Visão geral"
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(next(m.value for m in app.metric if m.label == "OTD OK"), "1")
            self.assertEqual(next(m.value for m in app.metric if m.label == "OTD Atrasado"), "0")
            self.assertEqual(next(m.value for m in app.metric if m.label == "OTD validados manualmente no período"), "1")
            self.assertTrue(next(b.disabled for b in app.button if b.label == "Salvar análise manual"))
