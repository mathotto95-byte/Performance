"""Cruzamento por NF/placa, com monitoramento como ponte para os prazos."""
import re
import json
import unicodedata

import pandas as pd

UNKNOWN = "Sem informação"
RULES = ["OTS 2", "OTS 3", "OTD 1", "OTD 2", "OTD 3"]
MANUAL_OTD_SUPPORTED = True


def text(value):
    return "" if value is None or pd.isna(value) else str(value).strip()


def label(value):
    return "".join(c for c in unicodedata.normalize("NFKD", text(value).lower()) if not unicodedata.combining(c))


def date(value):
    value = text(value)
    if not re.fullmatch(r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?", value):
        return pd.NaT
    return pd.to_datetime(value, dayfirst=not bool(re.match(r"^\d{4}-\d\d-\d\d", value)), errors="coerce") if value else pd.NaT


def sunday_arrival(arrival, deadline):
    limit, reached = date(deadline), date(arrival)
    if pd.isna(limit):
        return None
    limit = limit.tz_convert("America/Sao_Paulo") if limit.tzinfo else limit
    if limit.weekday() != 6:
        return None
    if pd.isna(reached):
        return False
    reached = reached.tz_convert("America/Sao_Paulo") if reached.tzinfo else reached
    return reached.date() == limit.date()


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


def compare_destination_day(arrival, deadline):
    reached, limit = date(arrival), date(deadline)
    if pd.isna(reached) or pd.isna(limit):
        return UNKNOWN, "chegada no destino ou Data Limite ausente ou inválida"
    reached = reached.tz_convert("America/Sao_Paulo") if reached.tzinfo else reached
    limit = limit.tz_convert("America/Sao_Paulo") if limit.tzinfo else limit
    same_day = reached.date() == limit.date()
    return ("Dentro do prazo" if same_day else "Fora do prazo",
            f"chegada no destino {reached:%d/%m/%Y} {'na' if same_day else 'fora da'} Data Limite {limit:%d/%m/%Y}")


def compare_not_early(actual, deadline):
    """Dentro quando o evento ocorre no mesmo dia ou depois do limite."""
    a, b = date(actual), date(deadline)
    if pd.isna(a) or pd.isna(b):
        return UNKNOWN, "data ausente ou inválida"
    if a.tzinfo:
        a = a.tz_convert("America/Sao_Paulo")
    if b.tzinfo:
        b = b.tz_convert("America/Sao_Paulo")
    inside = a.date() >= b.date()
    return ("Dentro do prazo", "no mesmo dia ou posterior ao limite") if inside else ("Fora do prazo", "antecipado ao limite")


def compare_otd3(arrival, agenda, deadline):
    agenda_date, deadline_date = date(agenda), date(deadline)
    if pd.isna(deadline_date):
        return UNKNOWN, "Data Limite ausente ou inválida"
    if pd.isna(agenda_date):
        return compare_destination_day(arrival, deadline)
    agenda_date = agenda_date.tz_convert("America/Sao_Paulo") if agenda_date.tzinfo else agenda_date
    deadline_date = deadline_date.tz_convert("America/Sao_Paulo") if deadline_date.tzinfo else deadline_date
    if agenda_date.date() == deadline_date.date():
        return compare(arrival, agenda)
    if agenda_date > deadline_date:
        return compare_destination_day(arrival, deadline)
    return compare(arrival, agenda)


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
    df = pd.DataFrame(rows)
    marks = result.get("performance_envios", [])
    if marks:
        marks = pd.DataFrame(marks)
        if {"lcte_id", "analise_enviada_em"}.issubset(marks.columns) and not marks.lcte_id.duplicated().any():
            df["analise_enviada_em"] = df.lcte_id.map(marks.set_index("lcte_id").analise_enviada_em)
    return df


def lcte_from_estadias(payload):
    section = payload.get("imports", payload)
    if not isinstance(section, dict) or not isinstance(section.get("tables", {}), dict):
        raise ValueError("Backup de importações do Estadias inválido.")
    rows = section.get("tables", {}).get("mod_estadias_lcte_normalizada", [])
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("LCTE do Estadias inválido; importação anterior preservada.")
    result = []
    for row in rows:
        try:
            original = json.loads(row.get("dados_json") or "{}")
        except (ValueError, TypeError):
            original = {}
        original = {label(k): text(v) for k, v in original.items()} if isinstance(original, dict) else {}
        result.append({
            "Notas fiscais": original.get("notas fiscais") or text(row.get("nf")),
            "Placa tração": original.get("placa tracao") or text(row.get("placa_norm")) or text(row.get("placa")),
            "Observação": original.get("observacao") or original.get("obs") or original.get("comentario") or text(row.get("monitoramento")) or text(row.get("observacao")),
            "Data Emissão NF": original.get("data emissao nf", ""),
            "Município do remetente": original.get("municipio do remetente") or text(row.get("origem")),
            "Município do destinatário": original.get("municipio do destinatario") or text(row.get("destino")),
        })
    return pd.DataFrame(result)


def resolve_arrival(candidates):
    if len(candidates) == 1:
        return candidates[0]
    # Duplicações só podem compartilhar horários quando identificam a mesma viagem.
    if not candidates or not text(candidates[0].get("chave_viagem")):
        return {}
    for field in ["chave_viagem", "origem", "destino", "data_emissao_nf", "monitoramento"]:
        values = {text(r.get(field)) for r in candidates if text(r.get(field))}
        if len(values) > 1 or (field == "chave_viagem" and any(not text(r.get(field)) for r in candidates)):
            return {}
    result = {}
    for field in ["chegada_origem", "chegada_destino"]:
        values = {text(r.get(field)) for r in candidates if text(r.get(field))}
        parsed = {date(v) for v in values}
        if any(pd.isna(v) for v in parsed) or len(parsed) > 1:
            return {}
        result[field] = sorted(values)[0] if values else ""
    return result


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
        arrival = resolve_arrival(candidates)
        item["Correspondência Estadias"] = ("Exata" if len(candidates) == 1 else "NF + placa exata; viagem duplicada compatível") if arrival else "Sem correspondência"
        if arrival and len(candidates) > 1:
            problems.append("chegadas do rastreador recuperadas da mesma chave de viagem; duplicidade pendente de validação no Estadias")
        if not arrival:
            problems.append("NF + placa com registros conflitantes ou viagem não comprovada no Estadias" if candidates else "NF + placa não localizada no Estadias")
        for dest, source in [("Previsão de Carga", "Previsao Carga"), ("Agendamento de Carga", "Agendamento Carga"), ("Data Limite", "Data Limite"), ("Agenda GFL", "Agenda GFL")]:
            item[dest] = text(schedule.get(source))
        item["Chegada na Origem"] = text(arrival.get("chegada_origem"))
        item["Chegada no Destino"] = text(arrival.get("chegada_destino"))
        item["Exceção OTD por chegada"] = False
        for rule, actual, deadline in [
            ("OTS 2", item["Agendamento de Carga"], item["Previsão de Carga"]),
            ("OTS 3", item["Chegada na Origem"], item["Agendamento de Carga"] or item["Previsão de Carga"]),
            ("OTD 2", item["Agenda GFL"], item["Data Limite"]),
            ("OTD 3", item["Chegada no Destino"], item["Data Limite"]),
        ]:
            if rule in {"OTS 2", "OTD 2"}:
                item[rule], reason = compare_not_early(actual, deadline)
            elif rule == "OTD 3":
                item[rule], reason = compare_otd3(actual, item["Agenda GFL"], deadline)
            else:
                item[rule], reason = compare(actual, deadline)
            problems.append(f"{rule}: {reason}")
        registered = date(schedule.get("Data/Hora do Registro"))
        issued = date(item["Emissão da NF"])
        item["OTD 1"] = UNKNOWN
        if pd.isna(registered) or pd.isna(issued):
            problems.append("OTD 1: Data/Hora do Registro ou Data Emissão NF ausente, inválida ou sem vínculo único")
        else:
            registered_day = (registered.tz_convert("America/Sao_Paulo") if registered.tzinfo else registered).date()
            issued_day = (issued.tz_convert("America/Sao_Paulo") if issued.tzinfo else issued).date()
            item["OTD 1"] = "Dentro do prazo" if registered_day == issued_day else "Fora do prazo"
            problems.append(f"OTD 1: data do registro {registered_day:%d/%m/%Y} {'igual à' if registered_day == issued_day else 'diferente da'} emissão da NF {issued_day:%d/%m/%Y}")
        item["Motivo da classificação"] = "; ".join(problems)
        output.append(item)
    columns = ["Nota Fiscal", "Placa", "Monitoramento", "Origem", "Destino", "Previsão de Carga", "Agendamento de Carga", "Chegada na Origem", "Emissão da NF", "Data Limite", "Agenda GFL", "Chegada no Destino", *RULES, "Exceção OTD por chegada", "Motivo da classificação", "Correspondência Estadias"]
    result = pd.DataFrame(output, columns=columns)
    result["Atendeu todas as regras"] = result.apply(attendance, axis=1)
    return result


def schedule_indicators(ots, analysis=None):
    pairs = {"OTS": ("Agendamento Carga", "Previsao Carga"), "OTD": ("Agenda GFL", "Data Limite")}
    required = {"Codigo de Monitoramento", "Data/Hora do Registro", "ID", *[c for pair in pairs.values() for c in pair]}
    if not required.issubset(ots.columns):
        raise ValueError("Os indicadores OTS/OTD precisam das colunas do Banco OTS e OTD.")
    ordered = ots.assign(_date=ots["Data/Hora do Registro"].map(date), _id=pd.to_numeric(ots.ID, errors="coerce"))
    ordered = ordered.sort_values(["_date", "_id"], ascending=False, na_position="last")
    rows = []
    for code, group in ordered.groupby("Codigo de Monitoramento", dropna=False):
        valid = bool(text(code)) and group._date.notna().all() and group._id.notna().all()
        row = group.iloc[0]
        result = {**{c: row[c] for c in ots.columns}, "Monitoramento": text(code)}
        for name, (actual, limit) in pairs.items():
            a, b = date(row[actual]), date(row[limit])
            if pd.notna(b) and b.tzinfo:
                b = b.tz_convert("America/Sao_Paulo")
            result[f"Mês {name}"] = b.strftime("%Y-%m") if pd.notna(b) else "Sem data"
            result[name] = UNKNOWN
            if valid and pd.notna(a) and pd.notna(b):
                a = a.tz_convert("America/Sao_Paulo") if a.tzinfo else a
                b = b.tz_convert("America/Sao_Paulo") if b.tzinfo else b
                if a.date() == b.date() or (b.weekday() == 6 and (a.date() - b.date()).days == 1):
                    result[name] = "OK"
                else:
                    result[name] = "Antecipado" if a.date() < b.date() else "Atrasado"
        rows.append(result)
    result = pd.DataFrame(rows, columns=list(dict.fromkeys(["Monitoramento", *ots.columns, "OTS", "OTD", "Mês OTS", "Mês OTD"])))
    if analysis is not None and not analysis.empty and "Exceção OTD por chegada" in analysis:
        for code, group in analysis.groupby("Monitoramento"):
            if not text(code) or not group["Exceção OTD por chegada"].eq(True).all():
                continue
            result.loc[result.Monitoramento.eq(code) & result.OTD.eq("Atrasado"), "OTD"] = "OK"
    return result


def attendance(row):
    values = [row.get(rule, UNKNOWN) for rule in RULES]
    if "Fora do prazo" in values:
        return "Não"
    return "Sim" if all(v == "Dentro do prazo" for v in values) else UNKNOWN


def indicators(result):
    # analyze já consolida conflitos; não escolher uma linha arbitrária aqui.
    result = result.drop_duplicates()
    if result.duplicated(["Nota Fiscal", "Placa"]).any():
        raise ValueError("Resultados conflitantes para NF + placa.")
    valid = result["Nota Fiscal"].fillna("").ne("") & result.Placa.fillna("").ne("")
    result = result[valid]
    rows = []
    for rule in RULES:
        inside = int(result[rule].eq("Dentro do prazo").sum())
        outside = int(result[rule].eq("Fora do prazo").sum())
        total = inside + outside
        rows.append({"Regra": rule, "Total analisado": total, "Dentro do prazo": inside,
                     "Fora do prazo": outside, "Sem informação": len(result) - total,
                     "% Dentro": inside * 100 / total if total else None,
                     "% Fora": outside * 100 / total if total else None})
    table = pd.DataFrame(rows)
    total = int(table["Total analisado"].sum())
    groups = {"OTS": ["OTS 2", "OTS 3"], "OTD": ["OTD 1", "OTD 2", "OTD 3"], "OTS e OTD": RULES}
    group_percentages = {}
    for name, rules in groups.items():
        complete = result[rules].ne(UNKNOWN).all(axis=1)
        group_percentages[f"{name} %"] = float(result.loc[complete, rules].eq("Dentro do prazo").all(axis=1).mean() * 100) if complete.any() else None
    general = {"Viagens/NFs": len(result), "Regras analisadas": total,
               "Dentro": int(table["Dentro do prazo"].sum()), "Fora": int(table["Fora do prazo"].sum()),
               "Sem informação": int(table["Sem informação"].sum()),
               "Conformidade %": table["Dentro do prazo"].sum() * 100 / total if total else None,
               **group_percentages}
    return table, general
