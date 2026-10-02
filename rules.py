"""Cruzamento por NF/placa, com monitoramento como ponte para os prazos."""
import re
import unicodedata

import pandas as pd

UNKNOWN = "Sem informação"
RULES = ["OTS 2", "OTS 3", "OTD 1", "OTD 2", "OTD 3"]


def text(value):
    return "" if value is None or pd.isna(value) else str(value).strip()


def label(value):
    return "".join(c for c in unicodedata.normalize("NFKD", text(value).lower()) if not unicodedata.combining(c))


def date(value):
    value = text(value)
    return pd.to_datetime(value, dayfirst=not bool(re.match(r"^\d{4}-\d\d-\d\d", value)), errors="coerce") if value else pd.NaT


def compare(actual, deadline):
    a, b = date(actual), date(deadline)
    if pd.isna(a) or pd.isna(b):
        return UNKNOWN, "data ausente ou inválida"
    # Datas sem horário são comparadas por dia, nunca como meia-noite presumida.
    if not re.search(r"\d{1,2}:\d{2}", text(deadline)):
        late = a.date() > b.date()
    elif not re.search(r"\d{1,2}:\d{2}", text(actual)):
        if a.date() == b.date():
            return UNKNOWN, "horário necessário para comparar no mesmo dia"
        late = a.date() > b.date()
    else:
        if a.tzinfo is not None:
            a = a.tz_convert("America/Sao_Paulo").tz_localize(None)
        if b.tzinfo is not None:
            b = b.tz_convert("America/Sao_Paulo").tz_localize(None)
        late = a > b
    return ("Fora do prazo", "posterior ao limite") if late else ("Dentro do prazo", "até o limite")


def prepare_lcte(df):
    columns = {label(c): c for c in df.columns}
    required = ["notas fiscais", "placa tracao", "observacao"]
    if not all(c in columns for c in required):
        raise ValueError("LCTE precisa das colunas Notas fiscais, Placa tração e Observação.")
    rows = []
    for _, row in df.iterrows():
        get = lambda name: text(row.get(columns.get(name, ""), ""))
        # Mesma extração de 7 dígitos do Estadias; múltiplos códigos são ambíguos.
        codes = set(re.findall(r"(?<!\d)\d{7}(?!\d)", get("observacao")))
        raw_nf = get("notas fiscais")
        if re.fullmatch(r"\d+\.0", raw_nf):
            raw_nf = raw_nf[:-2]
        nfs = [n.strip().lstrip("0") or "0" for n in re.split(r"[;,/|\s]+", raw_nf) if n.strip()]
        for nf in nfs or [""]:
            rows.append({"Nota Fiscal": nf, "Placa": re.sub(r"[^A-Z0-9]", "", get("placa tracao").upper()),
                         "Monitoramento": next(iter(codes)) if len(codes) == 1 else "",
                         "Origem": get("municipio do remetente"), "Destino": get("municipio do destinatario"),
                         "Emissão da NF": get("data emissao nf"),
                         "problema": "múltiplos monitoramentos na Observação" if len(codes) > 1 else ""})
    if not rows:
        raise ValueError("LCTE sem registros.")
    return pd.DataFrame(rows)


def estadias_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("Backup Estadias inválido.")
    result = payload.get("results", payload)
    if not isinstance(result, dict) or not isinstance(result.get("tables"), dict):
        raise ValueError("Backup Estadias sem tabelas válidas.")
    rows = result.get("tables", {}).get("mod_estadias_cruzamento_inicial", [])
    if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) and {"nf", "placa_norm", "chegada_origem", "chegada_destino"}.issubset(r) for r in rows):
        raise ValueError("Backup sem resultados de Estadias válidos; base atual preservada.")
    return pd.DataFrame(rows)


def analyze(lcte, ots, estadias):
    base = prepare_lcte(lcte)
    schedules = {}
    if not ots.empty:
        required = {"Codigo de Monitoramento", "Data/Hora do Registro", "ID", "Previsao Carga", "Agendamento Carga", "Data Limite", "Agenda GFL"}
        if not required.issubset(ots.columns):
            raise ValueError("A base OTS/OTD não contém as colunas do Banco OTS e OTD.")
        ordered = ots.assign(_date=ots["Data/Hora do Registro"].map(date), _id=pd.to_numeric(ots.ID, errors="coerce"))
        ordered = ordered.sort_values(["_date", "_id"], ascending=False, na_position="last")
        for code, group in ordered.groupby("Codigo de Monitoramento"):
            schedules[text(code)] = group.iloc[0].to_dict() if group._date.notna().all() and group._id.notna().all() else {}
    arrivals = {}
    if not estadias.empty:
        if not {"nf", "placa_norm", "chegada_origem", "chegada_destino"}.issubset(estadias.columns):
            raise ValueError("Use o resultado completo do Estadias, com nf, placa_norm e chegadas.")
        for row in estadias.to_dict("records"):
            for nf in re.split(r"[;,/|\s]+", text(row.get("nf"))):
                key = (nf.removesuffix(".0").lstrip("0") or "0", re.sub(r"[^A-Z0-9]", "", text(row.get("placa_norm")).upper()))
                arrivals.setdefault(key, []).append(row)
    output = []
    for key, group in base.groupby(["Nota Fiscal", "Placa"], dropna=False, sort=False):
        item = group.iloc[0].to_dict()
        problems = []
        ambiguous = len(group.drop_duplicates()) > 1 or not all(key) or bool(item.pop("problema"))
        schedule = schedules.get(item["Monitoramento"], {}) if not ambiguous else {}
        if ambiguous:
            problems.append("vínculo NF/placa/monitoramento ausente ou ambíguo")
        if not schedule:
            problems.append("monitoramento não localizado ou histórico OTS/OTD inválido")
        candidates = arrivals.get(key, []) if not ambiguous else []
        arrival = candidates[0] if len(candidates) == 1 else {}
        if not arrival:
            problems.append("NF + placa sem resultado único no Estadias")
        for dest, source in [("Previsão de Carga", "Previsao Carga"), ("Agendamento de Carga", "Agendamento Carga"), ("Data Limite", "Data Limite"), ("Agenda GFL", "Agenda GFL")]:
            item[dest] = text(schedule.get(source))
        item["Chegada na Origem"] = text(arrival.get("chegada_origem"))
        item["Chegada no Destino"] = text(arrival.get("chegada_destino"))
        for rule, actual, deadline in [
            ("OTS 2", item["Agendamento de Carga"], item["Previsão de Carga"]),
            ("OTS 3", item["Chegada na Origem"], item["Agendamento de Carga"] or item["Previsão de Carga"]),
            ("OTD 2", item["Agenda GFL"], item["Data Limite"]),
            ("OTD 3", item["Chegada no Destino"], item["Agenda GFL"] or item["Data Limite"]),
        ]:
            item[rule], reason = compare(actual, deadline)
            problems.append(f"{rule}: {reason}")
        # O registro no OTS não prova quando o agendamento efetivamente foi realizado.
        item["OTD 1"] = UNKNOWN
        problems.append("OTD 1: falta data/hora comprovada de realização do agendamento do destino")
        if not re.search(r"\d{1,2}:\d{2}", item["Emissão da NF"]):
            problems.append("OTD 1: emissão da NF sem horário")
        item["Motivo da classificação"] = "; ".join(problems)
        output.append(item)
    columns = ["Nota Fiscal", "Placa", "Monitoramento", "Origem", "Destino", "Previsão de Carga", "Agendamento de Carga", "Chegada na Origem", "Emissão da NF", "Data Limite", "Agenda GFL", "Chegada no Destino", *RULES, "Motivo da classificação"]
    return pd.DataFrame(output, columns=columns)
