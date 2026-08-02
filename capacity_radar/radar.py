"""
Fabric Capacity Radar — assessment de CAPACIDADE/THROTTLING do Microsoft Fabric.

NÃO é "FinOps de consumo": o Fabric cobra por CAPACIDADE de preço FIXO (F-SKU) com
smoothing/throttling. A pergunta é de capacidade: **você está sendo throttled? por
causa de qual item? quão perto do limite? deve redimensionar o F-SKU?**

O app "Fabric Capacity Metrics" mostra os NÚMEROS. O Radar CONCLUI o que ele não
conclui, sobre uma fundação ESTÁVEL e ANCORADA EM EVENTOS:

- **Diagnóstico de throttle** — da tabela `System events` (verdade-fundamento,
  event-sourced): quando e de que tipo (Delay leve / Rejection grave).
- **Atribuição causal** — no timepoint de cada throttle, QUAL item consumiu CU
  (ranqueado por `[Timepoint CU (s)]`, a parcela suavizada que aterrissou ali —
  não por hora de início). É o que o app não faz.
- **Utilização % do timepoint (estimada)** — `Σ [Timepoint CU (s)] / (F × 30) × 100` no
  timepoint do evento, sobre TODOS os itens (F = SKU; capacidade do timepoint de 30 s =
  F×30 CU-s). Usa `Timepoint CU (s)`, NÃO `Total CU (s)` (que infla). ⚠ util%>100% num
  timepoint NÃO é throttle (throttle = esgotar capacidade FUTURA de janela — vem de
  System events). Não filtra billable ainda (pode ficar acima do nº que dispara throttle).
- **Overage do timepoint** — `MAX(0, ΣTimepointCU − F×30)` (pico acima de 100% no instante).
- **Recomendação de F-SKU** — dirigida pelos EVENTOS + GATE DE CRONICIDADE (rejeição
  crônica em ≥2 dias → considerar upsize APÓS a escada de remédios; rejeição isolada →
  investigar, não 'dobre a fatura'; sem throttle → saudável). Nunca recomenda DESCER sem
  utilização de janela.

⚠ Limites honestos (declarados): a paridade numérica com `Add%/Burndown%/Cumulative%`
do app NÃO é prometida (pools separados, billable-only, surge/autoscale, borda de
janela). O semantic model do app é "não suportado / versionado" — a ferramenta
DESCOBRE e VALIDA nomes em runtime, nunca hardcoda cego.

Fontes: throttling e F2=2CU×30s https://learn.microsoft.com/en-us/fabric/enterprise/throttling ·
        compute page (CU%Limit, Timepoint CU) https://learn.microsoft.com/en-us/fabric/enterprise/metrics-app-compute-page ·
        timepoint (Timepoint CU (s) vs Total CU (s)) https://learn.microsoft.com/en-us/fabric/enterprise/metrics-app-timepoint-page ·
        SemPy https://learn.microsoft.com/en-us/python/api/semantic-link-sempy/sempy.fabric
"""
import re
from typing import Optional

_FSKUS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]

# Estados de throttle na tabela System events (doc oficial).
_ESTAGIOS = {
    "InteractiveDelay": "Interactive Delay — jobs interativos atrasados 20s (leve)",
    "InteractiveRejected": "Interactive Rejection — interativo REJEITADO, background ainda roda (grave)",
    "AllRejected": "Background/All Rejection — TUDO rejeitado (grave)",
    "SurgeProtectionActive": "Surge Protection ativa",
}
_REJEICAO = ("InteractiveRejected", "AllRejected")

TABELAS_ESPERADAS = ["Capacities", "Items", "Dates",
                     "Timepoint Interactive Detail", "Timepoint Background Detail",
                     "System events"]


# ── INTERPRETAÇÃO (pura Python — o diferencial, testável sem Fabric) ──────────
def sku_atual_cu(nome_sku) -> Optional[int]:
    """CU da SKU a partir do nome (F64 -> 64). None se não reconhecer."""
    if not nome_sku:
        return None
    try:
        return int(str(nome_sku).strip().upper().lstrip("F"))
    except ValueError:
        return None


def diagnosticar_throttle(eventos: list, eventos_lidos: bool = True) -> dict:
    """Resume os eventos de throttle por TIPO, com CRONICIDADE (dias distintos com
    rejeição — 1 pico isolado ≠ problema crônico).

    Três estados, não dois: `eventos_lidos=False` → None (não li);
    lida mas NENHUM estado reconhecido apesar de haver linhas → None também
    (rótulos podem ter mudado de versão — não afirmar 'saudável' sem reconhecer);
    lida e sem throttle de fato → False."""
    if not eventos_lidos:
        return {"houve_throttle": None, "rejeicao": False, "por_tipo": {}, "dias_rejeicao": 0,
                "resumo": "LEITURA INCOMPLETA — não consegui ler 'System events'. Não é 'sem throttle'."}
    contagem, dias_rej = {}, set()
    houve_linha = False
    for e in eventos or []:
        houve_linha = True
        estado = (e.get("estado") or "").split("/")[-1]
        if estado in _ESTAGIOS:
            contagem[estado] = contagem.get(estado, 0) + 1
            if estado in _REJEICAO and e.get("quando"):
                dias_rej.add(str(e["quando"])[:10])  # YYYY-MM-DD
    if not contagem:
        if houve_linha:
            return {"houve_throttle": None, "rejeicao": False, "por_tipo": {}, "dias_rejeicao": 0,
                    "resumo": "INCONCLUSIVO — 'System events' tem linhas, mas nenhum estado casou os "
                              "rótulos conhecidos (a versão do app pode ter renomeado). Não afirmo 'saudável'."}
        return {"houve_throttle": False, "rejeicao": False, "por_tipo": {}, "dias_rejeicao": 0,
                "resumo": "Sem eventos de throttle no período (System events lida, vazia de throttle)."}
    rejeicao = any(k in _REJEICAO for k in contagem)
    linhas = [f"{n}× {_ESTAGIOS[k]}" for k, n in sorted(contagem.items(), key=lambda x: -x[1])]
    return {"houve_throttle": True, "rejeicao": rejeicao, "por_tipo": contagem,
            "dias_rejeicao": len(dias_rej), "resumo": " · ".join(linhas)}


# Remédios da doc, ANTES do upsize (a doc: "consistently high... load balance OR
# increase SKU"). Dobrar a fatura é o último degrau, não o primeiro.
_ESCADA_REMEDIO = ("(1) rebalancear/reescalonar os jobs que empilham no pico; "
                   "(2) load-balancing entre capacidades; (3) pause/resume para zerar o "
                   "carryforward; (4) — só se crônico — subir o F-SKU (dobra o custo).")


def recomendar_sku(cu_atual, throttle: dict, min_dias_cronico: int = 2) -> dict:
    """Recomendação de F-SKU dirigida pelos EVENTOS (System events = verdade), com
    GATE DE CRONICIDADE: rejeição em ≥`min_dias_cronico` dias distintos = crônico
    (justifica considerar upsize); rejeição isolada = investigar, NÃO 'dobre a
    fatura'. O smoothing do Fabric absorve bursts ocasionais — subir SKU por n=1 é
    o conselho que um sênior ridiculariza. Nunca recomenda DESCER sem util de janela."""
    if throttle.get("houve_throttle") is None:
        return {"acao": "indefinido", "sku_sugerida": None, "urgencia": "media",
                "motivo": "leitura de System events incompleta/irreconhecível — não recomendo "
                          "dimensionamento sem o histórico de throttle confiável."}
    if cu_atual is None or cu_atual not in _FSKUS:
        return {"acao": "indefinido", "sku_sugerida": None, "urgencia": "media",
                "motivo": f"informe o F-SKU atual (recebi {cu_atual!r}) para a recomendação."}
    i = _FSKUS.index(cu_atual)
    if not throttle["houve_throttle"]:
        return {"acao": "sem_throttle", "sku_sugerida": f"F{cu_atual}", "urgencia": "baixa",
                "motivo": "Nenhum evento de throttle no período — a capacidade suporta a carga atual. "
                          "Avaliar DOWNSIZE exige a utilização média da janela (frente aberta)."}
    if throttle["rejeicao"]:
        n = sum(v for k, v in throttle["por_tipo"].items() if k in _REJEICAO)
        dias = throttle.get("dias_rejeicao", 0)
        if dias >= min_dias_cronico:
            alvo = _FSKUS[min(i + 1, len(_FSKUS) - 1)]
            return {"acao": "subir", "sku_sugerida": f"F{alvo}", "urgencia": "alta",
                    "motivo": f"REJEIÇÃO CRÔNICA — {n} evento(s) em {dias} dias distintos. Capacidade "
                              f"sub-provisionada. Escada: {_ESCADA_REMEDIO} O piso, se o gargalo "
                              f"persistir após rebalancear, é F{alvo}."}
        return {"acao": "investigar", "sku_sugerida": f"F{cu_atual}", "urgencia": "media",
                "motivo": f"REJEIÇÃO ISOLADA — {n} evento(s) em {dias} dia(s). Pode ser um pico "
                          f"pontual (o smoothing absorve bursts). NÃO subir SKU ainda: {_ESCADA_REMEDIO} "
                          "Investigue o(s) item(ns) atribuído(s) antes de considerar upsize."}
    return {"acao": "atencao", "sku_sugerida": f"F{cu_atual}", "urgencia": "media",
            "motivo": "Interactive Delay observado (throttle leve, +20s) — no limite, sem rejeição. "
                      f"Antes de qualquer upsize: {_ESCADA_REMEDIO}"}


def utilizacao_pct(cu_no_timepoint: float, f_cu: Optional[int]) -> Optional[float]:
    """Utilização% do timepoint = ΣTimepointCU / (F×30) × 100. None sem o F."""
    if not f_cu or f_cu <= 0:
        return None
    return round(100.0 * (cu_no_timepoint or 0) / (f_cu * 30.0), 1)


def overage_cu(cu_no_timepoint: float, f_cu: Optional[int]) -> Optional[float]:
    """CU acima do teto no timepoint = MAX(0, ΣTimepointCU − F×30). None sem o F."""
    if not f_cu or f_cu <= 0:
        return None
    return round(max(0.0, (cu_no_timepoint or 0) - f_cu * 30.0), 1)


def diagnosticar(dados: dict) -> dict:
    """Monta o veredito. Respeita 'não li' × 'li e é 0'; a recomendação de SKU é
    event-driven; a atribuição causal já vem de `dados['causas']`."""
    cu = sku_atual_cu(dados.get("sku"))
    coletado = dados.get("coletado", {})
    thr = diagnosticar_throttle(dados.get("eventos", []), eventos_lidos=coletado.get("eventos", False))
    sku = recomendar_sku(cu, thr)
    causas = dados.get("causas", [])  # [{timepoint, tipo, util_pct, overage_cu, itens:[{item,cu_s}]}]
    return {"sku_atual": dados.get("sku"), "throttle": thr, "recomendacao_sku": sku,
            "atribuicao_causal": causas, "coletado": coletado}


# ── COLETA via SemPy/DAX (defensiva; roda em notebook Fabric) ─────────────────
def _sempy():
    try:
        import sempy.fabric as fabric  # noqa
        return fabric
    except Exception as e:
        raise RuntimeError("Rode dentro de um notebook Microsoft Fabric "
                           f"(precisa de sempy.fabric / semantic-link). Import falhou: {e}")


def descobrir_modelo(workspace: Optional[str] = None,
                     nome_provavel: str = "Fabric Capacity Metrics") -> dict:
    """Descobre o semantic model do Capacity Metrics App (REST, não exige XMLA
    ReadWrite). Acha a coluna de nome por heurística (o rótulo varia por modo)."""
    fabric = _sempy()
    try:
        ds = fabric.list_datasets(workspace=workspace, mode="rest")
        col = next((c for c in ds.columns if "name" in c.lower()), None)
        nomes = [str(v) for v in ds[col]] if col is not None else []
        alvo = next((n for n in nomes if "capacity metrics" in n.lower()), None) or \
               (nome_provavel if nome_provavel in nomes else None)
        if not alvo:
            raise RuntimeError(
                "Não encontrei o modelo 'Fabric Capacity Metrics' no workspace informado. "
                "Instale o Capacity Metrics App (como Capacity Admin) e aponte o workspace dele "
                f"em `workspace=`. Modelos vistos: {nomes[:10]} (colunas: {list(ds.columns)})")
        return {"workspace": workspace, "dataset": alvo}
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Falha ao descobrir o modelo do Capacity Metrics: {e}")


def validar_schema(dataset: str, workspace: Optional[str] = None) -> dict:
    """Quais TABELAS esperadas existem (o modelo é versionado)? {presentes, ausentes}.

    Usa `evaluate_dax`, que lê pelo endpoint XMLA (doc oficial SemPy): exige XMLA
    read-only habilitado na capacidade — read basta, NÃO precisa read-write. Se o XMLA
    estiver desligado, cai no ramo de erro e reporta todas as tabelas como ausentes."""
    fabric = _sempy()
    try:
        info = fabric.evaluate_dax(dataset=dataset, workspace=workspace,
                                   dax_string="EVALUATE INFO.TABLES()")
        col = next((c for c in info.columns if c.lower().endswith("name")), None)
        tabelas = set(str(v) for v in info[col]) if col else set()
        return {"presentes": [t for t in TABELAS_ESPERADAS if t in tabelas],
                "ausentes": [t for t in TABELAS_ESPERADAS if t not in tabelas],
                "todas": sorted(tabelas)}
    except Exception as e:
        return {"presentes": [], "ausentes": TABELAS_ESPERADAS, "erro": str(e)[:200]}


def _achar(colunas, *chaves):
    """Primeira coluna cujo nome contém uma das chaves (case-insensitive)."""
    for ch in chaves:
        c = next((x for x in colunas if ch in str(x).lower()), None)
        if c:
            return c
    return None


def coletar(dataset: str, capacity_id: str, sku: Optional[str],
            workspace: Optional[str] = None, max_eventos: int = 8) -> dict:
    """Coleta ancorada em EVENTOS: lê `System events` (verdade do throttle) e, para
    os N eventos de throttle mais recentes, atribui a causa no timepoint (top itens
    por `Timepoint CU (s)`) + utilização% + overage (usando F do SKU).

    Cada query isolada; `coletado[secao]` marca sucesso — distinguir 'não li' de
    'li e é 0' é o que evita o falso-negativo."""
    fabric = _sempy()
    if not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
                        capacity_id or ""):
        raise ValueError(f"capacity_id inválido: {capacity_id!r} — esperado GUID (8-4-4-4-12).")
    f_cu = sku_atual_cu(sku)
    dados = {"sku": sku, "eventos": [], "causas": [], "avisos": [],
             "coletado": {"eventos": False, "causas": False}}

    def _dax(q):
        return fabric.evaluate_dax(dataset=dataset, workspace=workspace, dax_string=q)

    cap = f"MPARAMETER 'CapacitiesList' = {{\"{capacity_id}\"}}\n"

    # 1) Eventos de throttle (janela inteira — System events NÃO é gated por timepoint).
    eventos_throttle = []
    try:
        ev = _dax(f"DEFINE {cap} EVALUATE 'System events'")
        cst = _achar(ev.columns, "state", "status", "reason")
        ctm = _achar(ev.columns, "time", "date")
        if cst:
            for _, r in ev.iterrows():
                estado = str(r[cst])
                if estado.split("/")[-1] in _ESTAGIOS:
                    eventos_throttle.append({"estado": estado,
                                             "quando": str(r[ctm]) if ctm else None})
            dados["eventos"] = eventos_throttle
            dados["coletado"]["eventos"] = True
        else:
            dados["avisos"].append("System events: coluna de estado não encontrada (modelo mudou?)")
    except Exception as e:
        dados["avisos"].append(f"System events indisponível: {str(e)[:120]}")

    # 2) Atribuição causal nos N throttles mais recentes (cada um num timepoint).
    if eventos_throttle:
        # ORDENA por tempo (System events vem sem ORDER BY garantido) → os N MAIS
        # RECENTES de verdade. Registra que é uma amostra, se houver mais.
        com_data = sorted([e for e in eventos_throttle if e.get("quando")], key=lambda e: e["quando"])
        recentes = com_data[-max_eventos:]
        if len(com_data) > max_eventos:
            dados["avisos"].append(f"Atribuição causal mostrando os {max_eventos} throttles mais "
                                   f"recentes de {len(com_data)} no período.")
        alguma = False
        for ev in recentes:
            tp = _timepoint_dax(ev["quando"])
            if not tp:
                dados["avisos"].append(f"Evento em {ev['quando']!r}: não consegui parsear a data "
                                       "(formato/timezone) — causa não atribuída.")
                continue
            try:
                itens, cu_total = _causa_no_timepoint(_dax, cap, tp)
                if itens is not None:
                    alguma = True
                    ev_causa = {"timepoint": ev["quando"], "tipo": ev["estado"].split("/")[-1],
                                "util_pct": utilizacao_pct(cu_total, f_cu),
                                "overage_cu": overage_cu(cu_total, f_cu),
                                "cu_total_no_timepoint": round(cu_total, 1),
                                "itens": itens[:5]}
                    dados["causas"].append(ev_causa)
            except Exception as e:
                dados["avisos"].append(f"Causa em {ev['quando']}: {str(e)[:100]}")
        dados["coletado"]["causas"] = alguma
        if f_cu is None:
            dados["avisos"].append("SKU não informado — util%/overage por timepoint ficam None "
                                   "(informe FABRIC_SKU=F<n> para os percentuais).")

    return dados


def _timepoint_dax(quando: str) -> Optional[str]:
    """Converte o instante do evento numa expressão DAX do timepoint de 30s que o
    CONTÉM. Os timepoints são baldes alinhados a :00/:30 — sem o FLOOR do segundo,
    um evento em :47 não casaria nenhum timepoint (retornaria vazio). Aceita
    'YYYY-MM-DD[ T]HH:MM:SS' (ignora fração/timezone — ⚠ assume mesmo fuso das
    tabelas de timepoint; validar no Fabric real)."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", quando or "")
    if not m:
        return None
    y, mo, d, h, mi, s = map(int, m.groups())
    s = 0 if s < 30 else 30
    return f"( DATE({y},{mo},{d}) + TIME({h},{mi},{s}) )"


def _causa_no_timepoint(_dax, cap: str, timepoint_expr: str):
    """No timepoint do throttle: (1) CU TOTAL de TODOS os itens (denominador da
    util%/overage — scan completo, NÃO o top-15, que subestimaria); (2) top-15
    itens por `Timepoint CU (s)` (a lista de culpados). Retorna (itens, cu_total).

    Retorna (None, 0) se o timepoint não casar nada (cu_total ≤ 0) — evita a
    'causa fantasma' de 0%/sem itens que um desalinhamento de timepoint geraria."""
    base = f"DEFINE {cap} MPARAMETER 'TimePoint' = {timepoint_expr}"
    soma = ("CALCULATE(SUM('Timepoint Interactive Detail'[Timepoint CU (s)])) "
            "+ CALCULATE(SUM('Timepoint Background Detail'[Timepoint CU (s)]))")

    # (1) total do timepoint — SEM TOPN, todos os itens.
    tot = _dax(f'{base}\n EVALUATE ROW("cu_total", {soma})')
    ctot = _achar(tot.columns, "cu_total")
    cu_total = float(tot[ctot].iloc[0] or 0) if (ctot is not None and len(tot)) else 0.0
    if cu_total <= 0:
        return None, 0.0  # timepoint vazio/desalinhado — não inventa causa de 0%

    # (2) top-15 culpados.
    top = _dax(f'{base}\n EVALUATE TOPN(15, SUMMARIZECOLUMNS('
               f"'Items'[Item name], 'Items'[Item kind], \"cu_s\", {soma}), [cu_s], DESC)")
    cnome = _achar(top.columns, "item name")
    ccu = _achar(top.columns, "cu_s")
    itens = []
    if cnome and ccu:
        for _, r in top.iterrows():
            itens.append({"item": str(r[cnome]), "cu_s": round(float(r[ccu] or 0), 1)})
    return itens, cu_total


def radar(capacity_id: str, workspace: Optional[str] = None,
          sku: Optional[str] = None) -> dict:
    """Orquestra: descobre o modelo → valida schema → coleta (event-anchored) →
    DIAGNOSTICA. `sku` (ex.: 'F64') liga util%/overage e a recomendação."""
    modelo = descobrir_modelo(workspace)
    schema = validar_schema(modelo["dataset"], modelo["workspace"])
    # Tabelas SEM as quais o assessment não roda — se faltarem, é versão incompatível.
    essenciais = {"System events", "Timepoint Interactive Detail", "Items"}
    faltam = essenciais.intersection(schema.get("ausentes", []))
    schema["incompativel"] = sorted(faltam)
    dados = coletar(modelo["dataset"], capacity_id, sku, modelo["workspace"])
    diag = diagnosticar(dados)
    return {"modelo": modelo, "schema": schema, "diagnostico": diag, "avisos": dados.get("avisos", [])}
