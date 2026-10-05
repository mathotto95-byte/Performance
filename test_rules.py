import unittest
import pandas as pd
from rules import analyze, compare, prepare_lcte, estadias_payload, resolve_arrival, schedule_indicators


class RulesTest(unittest.TestCase):
    def test_late_otd_exception_requires_proven_arrival_for_every_nf(self):
        row = {"ID": 1, "Codigo de Monitoramento": "1234567", "Data/Hora do Registro": "01/02/2027", "Previsao Carga": "31/01/2027", "Agendamento Carga": "31/01/2027", "Data Limite": "31/01/2027", "Agenda GFL": "02/02/2027 08:00"}
        ots = pd.DataFrame([row])
        lcte = pd.DataFrame([{"Notas fiscais": "1", "Placa tração": "ABC1D23", "Observação": "1234567"}])
        stay = {"nf": "1", "placa_norm": "ABC1D23", "chegada_origem": "", "chegada_destino": "01/02/2027 23:59"}
        result = analyze(lcte, ots, pd.DataFrame([stay]))
        self.assertTrue(result.iloc[0]["Exceção OTD por chegada"])
        self.assertEqual(result.iloc[0]["OTD 2"], "Dentro do prazo")
        self.assertEqual(schedule_indicators(ots, result).iloc[0].OTD, "OK")
        self.assertEqual(result.iloc[0]["Agenda GFL"], row["Agenda GFL"])
        second = result.copy()
        second["Nota Fiscal"] = "2"
        second["Exceção OTD por chegada"] = False
        self.assertEqual(schedule_indicators(ots, pd.concat([result, second])).iloc[0].OTD, "Atrasado")
        for arrival in ["", "invalid", "02/02/2027 00:00"]:
            failed = analyze(lcte, ots, pd.DataFrame([{**stay, "chegada_destino": arrival}]))
            self.assertEqual(failed.iloc[0]["OTD 2"], "Fora do prazo")
            self.assertEqual(schedule_indicators(ots, failed).iloc[0].OTD, "Atrasado")
        wrong_plate = analyze(lcte, ots, pd.DataFrame([{**stay, "placa_norm": "XXX0000"}]))
        self.assertEqual(wrong_plate.iloc[0]["OTD 2"], "Fora do prazo")

    def test_sunday_otd_allows_monday_preserves_month_and_ots(self):
        row = {"ID": 1, "Codigo de Monitoramento": "1234567", "Data/Hora do Registro": "01/02/2027", "Previsao Carga": "31/01/2027", "Agendamento Carga": "01/02/2027", "Data Limite": "31/01/2027", "Agenda GFL": "01/02/2027 23:59"}
        result = schedule_indicators(pd.DataFrame([row])).iloc[0]
        self.assertEqual((result.OTS, result.OTD, result["Mês OTD"]), ("Atrasado", "OK", "2027-01"))
        lcte = pd.DataFrame([{"Notas fiscais": "1", "Placa tração": "ABC1D23", "Observação": "1234567"}])
        self.assertEqual(analyze(lcte, pd.DataFrame([row]), pd.DataFrame()).iloc[0]["OTD 2"], "Dentro do prazo")
        for agenda, expected in [("30/01/2027", "Antecipado"), ("31/01/2027", "OK"), ("02/02/2027", "Atrasado"), ("", "Sem informação")]:
            row["Agenda GFL"] = agenda
            self.assertEqual(schedule_indicators(pd.DataFrame([row])).iloc[0].OTD, expected)

    def test_standalone_schedules_calendar_days_and_latest(self):
        rows = []
        for i, value in enumerate(["01/09/2026 23:59", "31/08/2026", "02/09/2026", "invalid"]):
            rows.append({"ID": i, "Codigo de Monitoramento": str(i), "Data/Hora do Registro": "01/09/2026 10:00", "Agendamento Carga": value, "Previsao Carga": "01/09/2026 08:00", "Agenda GFL": value, "Data Limite": "01/09/2026"})
        rows.append({**rows[0], "ID": 99, "Data/Hora do Registro": "31/08/2026 10:00", "Agendamento Carga": "10/09/2026"})
        result = schedule_indicators(pd.DataFrame(rows))
        self.assertEqual(len(result), 4)
        self.assertEqual(result["Mês OTS"].tolist(), ["2026-09"] * 4)
        self.assertEqual(result["Mês OTD"].tolist(), ["2026-09"] * 4)
        for rule in ["OTS", "OTD"]:
            self.assertEqual(result[rule].tolist(), ["OK", "Antecipado", "Atrasado", "Sem informação"])

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
