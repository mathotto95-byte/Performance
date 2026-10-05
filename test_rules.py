import unittest
import pandas as pd
from rules import analyze, compare, prepare_lcte, estadias_payload, resolve_arrival


class RulesTest(unittest.TestCase):
    def test_same_trip_duplicate_arrivals_and_conflicts(self):
        first = {"chave_viagem": "ABC|20260901|CTE1", "chegada_origem": "2026-09-01 08:00", "chegada_destino": ""}
        empty = {**first, "chegada_origem": "", "chegada_destino": "2026-09-02 12:00"}
        resolved = resolve_arrival([first, empty])
        self.assertEqual(resolved["chegada_origem"], first["chegada_origem"])
        self.assertEqual(resolved["chegada_destino"], empty["chegada_destino"])
        for field, value in [("chave_viagem", "other"), ("chave_viagem", ""), ("chegada_origem", "2026-09-01 09:00"), ("chegada_origem", "invalid")]:
            self.assertEqual(resolve_arrival([first, {**empty, field: value}]), {})
        self.assertEqual(resolve_arrival([{}, {}]), {})

    def test_rules_and_missing_ambiguous_data(self):
        lcte = pd.DataFrame([{"Notas fiscais": "00123", "Placa tração": "ABC-1D23", "Observação": "Monitoramento 9462294", "Data Emissão NF": "01/09/2026"}])
        ots = pd.DataFrame([{"ID": 1, "Codigo de Monitoramento": "9462294", "Data/Hora do Registro": "01/09/2026 08:00", "Previsao Carga": "01/09/2026", "Agendamento Carga": "01/09/2026 12:00", "Data Limite": "03/09/2026", "Agenda GFL": "04/09/2026 08:00"}])
        stay = pd.DataFrame([{"nf": "123", "placa_norm": "ABC1D23", "chegada_origem": "2026-09-01 12:00:00", "chegada_destino": "2026-09-04 09:00:00"}])
        r = analyze(lcte, ots, stay).iloc[0]
        self.assertEqual([r[c] for c in ["OTS 2", "OTS 3", "OTD 1", "OTD 2", "OTD 3"]], ["Dentro do prazo", "Dentro do prazo", "Sem informação", "Fora do prazo", "Fora do prazo"])
        self.assertEqual(analyze(lcte, ots, pd.concat([stay, stay])).iloc[0]["OTS 3"], "Sem informação")
        self.assertEqual(analyze(lcte, pd.DataFrame(), stay).iloc[0]["OTS 2"], "Sem informação")
        lcte.loc[0, "Observação"] += " 1234567"
        self.assertEqual(analyze(lcte, ots, stay).iloc[0]["OTS 2"], "Sem informação")

    def test_dates_multiple_nf_and_payload(self):
        self.assertEqual(compare("01/09/2026", "01/09/2026 10:00")[0], "Sem informação")
        self.assertEqual(compare("01/09/2026 23:59", "01/09/2026")[0], "Dentro do prazo")
        self.assertEqual(compare("texto", "01/09/2026")[0], "Sem informação")
        df = pd.DataFrame([{"Notas fiscais": "001;002", "Placa tração": "ABC-1D23", "Observação": "9462294"}])
        self.assertEqual(prepare_lcte(df)["Nota Fiscal"].tolist(), ["1", "2"])
        row = {"nf": "1", "placa_norm": "ABC1D23", "chegada_origem": "", "chegada_destino": ""}
        p = {"tables": {"mod_estadias_cruzamento_inicial": [row]}}
        self.assertEqual(len(estadias_payload({"results": p})), 1)
        with self.assertRaises(ValueError):
            estadias_payload({})

    def test_latest_ots_record(self):
        lcte = pd.DataFrame([{"Notas fiscais": "1", "Placa tração": "ABC1D23", "Observação": "9462294"}])
        row = {"Codigo de Monitoramento": "9462294", "Previsao Carga": "01/09/2026", "Data Limite": "02/09/2026", "Agenda GFL": ""}
        ots = pd.DataFrame([{**row, "ID": 1, "Data/Hora do Registro": "01/09/2026 08:00", "Agendamento Carga": "01/09/2026"}, {**row, "ID": 2, "Data/Hora do Registro": "02/09/2026 08:00", "Agendamento Carga": "03/09/2026"}])
        self.assertEqual(analyze(lcte, ots, pd.DataFrame()).iloc[0]["OTS 2"], "Fora do prazo")
