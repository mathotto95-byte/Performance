import unittest
import pandas as pd
import base64
import json
from unittest.mock import patch, MagicMock
from rules import RULES, attendance, indicators, estadias_payload
from reporting import control_panel, panel_totals, money, publish


class ReportingTests(unittest.TestCase):
    def test_analysis_cards_and_approved_panel(self):
        from streamlit.testing.v1 import AppTest
        from core import FONTES
        history = pd.DataFrame([{"id": i, "fonte": source, "arquivo": "teste", "criado_em": "2026-10-02"} for i, source in enumerate(FONTES)])
        result = pd.DataFrame([{"Nota Fiscal": str(i), "Placa": "ABC1D23", "Atendeu todas as regras": status, **dict.fromkeys(RULES, rule)} for i, (status, rule) in enumerate([("Sim", "Dentro do prazo"), ("Não", "Fora do prazo"), ("Sem informação", "Sem informação")])])
        panel = pd.DataFrame({"Dentro da Regra": ["Sim", "Não", "Sem informação", "Sim"], "Horas de Estadia": [10.5, 10.5, 10.5, 0], "Valor": [714, 714, 714, 0]})
        result["Emissão da NF"] = ["01/08/2026", "01/09/2026", "02/09/2026"]
        result.loc[2, ["OTS 2", "OTD 2"]] = "Dentro do prazo"
        with patch("core.historico", return_value=history), patch("core.carregar", return_value=pd.DataFrame({"teste": [1]})), patch("ots_sync.status", return_value=None), patch("rules.analyze", return_value=result), patch("reporting.control_panel", return_value=panel), patch("reporting.render_panel") as render:
            app = AppTest.from_file("app.py", default_timeout=30)
            app.session_state["authenticated"] = True
            app.session_state["auth_user"] = {"username": "teste", "name": "Teste", "role": "CONSULTA"}
            app.session_state["performance_menu"] = "Análise Performance"
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual([m.value for m in app.metric][:4], ["3", "1", "1", "1"])
            self.assertEqual(render.call_args[0][0].index.tolist(), [0])
            self.assertEqual(next(m.value for m in app.metric if m.label == "NFs para validação manual"), "2")
            app.selectbox(key="analysis_month").select("2026-09").run()
            self.assertFalse(app.exception)
            self.assertEqual([m.value for m in app.metric][:4], ["2", "0", "1", "1"])
            self.assertEqual(next(m.value for m in app.metric if m.label == "NFs para validação manual"), "1")

    def test_publication_reuses_remote_sha_and_preserves_previous_on_invalid(self):
        row = {"Nota Fiscal": "1", "Placa": "ABC1D23", "Atendeu todas as regras": "Sem informação", "Correspondência Estadias": "Exata", "Motivo da classificação": "Sem dados", "Chegada na Origem": "", "Chegada no Destino": "", **dict.fromkeys(RULES, "Sem informação")}
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"sha":"existing"}'
        with patch("reporting.urlopen", return_value=response) as network:
            publish(pd.DataFrame([row]), {"LCTE": {"id": 1}}, "2026-10-02T10:00:00-03:00", "secret")
            request = network.call_args[0][0]
            body = json.loads(request.data)
            self.assertEqual(body["sha"], "existing")
            self.assertEqual(json.loads(base64.b64decode(body["content"]))["rows"][0]["Nota Fiscal"], "1")
            before = network.call_count
            with self.assertRaises(ValueError):
                publish(pd.DataFrame([row, row]), {}, "now", "secret")
            self.assertEqual(network.call_count, before)

    def test_status_and_denominators(self):
        row = {"Nota Fiscal": "1", "Placa": "ABC1D23", **dict.fromkeys(RULES, "Dentro do prazo")}
        self.assertEqual(attendance(row), "Sim")
        row["OTD 1"] = "Sem informação"
        self.assertEqual(attendance(row), "Sem informação")
        table, general = indicators(pd.DataFrame([row, row]))
        self.assertEqual(general["Viagens/NFs"], 1)
        self.assertEqual(general["Regras analisadas"], 4)
        self.assertEqual(general["Conformidade %"], 100)
        self.assertTrue(pd.isna(table.loc[table.Regra == "OTD 1", "% Dentro"].iloc[0]))
        row["OTS 2"] = "Fora do prazo"
        self.assertEqual(attendance(row), "Não")
        conflict = {**row, "OTS 2": "Dentro do prazo"}
        with self.assertRaises(ValueError):
            indicators(pd.DataFrame([row, conflict]))

    def test_period_value_deadline_and_duplicate_nf(self):
        analysis = pd.DataFrame([{"Nota Fiscal": nf, "Placa": "ABC1D23", "Correspondência Estadias": "Exata", "Atendeu todas as regras": "Sim"} for nf in ["1", "2"]])
        stays = pd.DataFrame([{"id": 7, "nf": "1;2", "placa_norm": "ABC1D23", "analise_enviada_em": "2026-10-01", "chegada_origem": "2026-10-01 08:00", "saida_origem": "2026-10-01 19:30", "franquia_carga_min": 60, "estadia_carga_min": 630}])
        panel = control_panel(analysis, stays)
        self.assertEqual(panel.iloc[0]["Horas de Estadia"], 10.5)
        self.assertEqual(panel.iloc[0].Prazo, pd.Timestamp("2026-10-16"))
        self.assertEqual(panel_totals(panel)["Valor total"], 714)
        self.assertEqual(money(10), 680)
        self.assertTrue(control_panel(analysis.iloc[:0], stays).empty)
        stays.loc[0, "saida_origem"] = "2026-09-30 08:00"
        self.assertTrue(pd.isna(control_panel(analysis, stays).iloc[0].Valor))

    def test_send_marks_from_backup(self):
        row = {"lcte_id": 7, "nf": "1", "placa_norm": "ABC1D23", "chegada_origem": "", "chegada_destino": ""}
        p = {"tables": {"mod_estadias_cruzamento_inicial": [row]}, "performance_envios": [{"lcte_id": 7, "analise_enviada_em": "2026-10-01"}]}
        self.assertEqual(estadias_payload(p).iloc[0].analise_enviada_em, "2026-10-01")
