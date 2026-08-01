"""
Fabric Capacity Radar — assessment de CAPACIDADE/THROTTLING do Microsoft Fabric.

NÃO é "FinOps de consumo": o Fabric cobra por CAPACIDADE de preço FIXO (F-SKU) com
smoothing/throttling. Somar CU × preço dá um número que não existe na fatura. A
pergunta certa é de capacidade: **você está sendo throttled? tem folga (headroom)?
qual item queima CU? deve redimensionar o F-SKU?**

O app "Fabric Capacity Metrics" já mostra os NÚMEROS. O diferencial do Radar é a
INTERPRETAÇÃO: atribuir o throttle a um item, traduzir headroom em decisão de SKU,
e separar "pico real" de "dívida de smoothing". Essa camada é pura Python (testável);
a coleta via SemPy/DAX é defensiva.

⚠ RESTRIÇÃO (doc oficial): o semantic model do app é "não suportado para consumo
externo" e os NOMES de tabela/medida mudam entre versões (referência: app v1031,
out/2025). Por isso a coleta DESCOBRE o modelo e VALIDA os nomes em runtime, com
fallback claro — nunca hardcoda cego.

Fontes: https://learn.microsoft.com/en-us/fabric/enterprise/throttling
        https://learn.microsoft.com/en-us/fabric/enterprise/metrics-app-compute-page
        https://learn.microsoft.com/en-us/python/api/semantic-link-sempy/sempy.fabric
"""
from typing import Optional

# ── Escada de F-SKUs (o número do F = Capacity Units) ─────────────────────────
_FSKUS = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]

# Estágios de throttling do Fabric (doc oficial) — usados no diagnóstico.
_ESTAGIOS = {
    "InteractiveDelay": "jobs interativos atrasados 20s (uso de capacidade futura 10–60 min)",
    "InteractiveRejected": "interativo REJEITADO, background ainda roda (60 min–24 h)",
    "AllRejected": "TUDO rejeitado (> 24 h de capacidade futura)",
    "SurgeProtectionActive": "proteção de surto ativa",
}

# Nomes esperados do modelo (v1031) — para VALIDAR, não para confiar cego.
TABELAS_ESPERADAS = ["Capacities", "Items", "Dates",
                     "Timepoint Interactive Detail", "Timepoint Background Detail",
                     "System events"]


# ── INTERPRETAÇÃO (pura Python — o diferencial, testável sem Fabric) ──────────
def sku_atual_cu(nome_sku: str) -> Optional[int]:
    """CU da SKU a partir do nome (F64 -> 64). None se não reconhecer."""
    if not nome_sku:
        return None
    s = nome_sku.strip().upper().lstrip("F")
    try:
        return int(s)
    except ValueError:
        return None


def recomendar_sku(cu_atual: int, pico_util_pct: float, houve_rejeicao: bool,
                   overage_acumulado_pct: float = 0.0) -> dict:
    """Traduz utilização real + throttle numa DECISÃO de F-SKU (o que o app nativo
    NÃO faz — ele mostra os números; aqui a gente recomenda).

    Regra: dobrar a SKU dá ~2× de headroom. Rejeição ou pico alto = subir; folga
    consistente = candidato a descer. É opinião ancorada em número, com o porquê."""
    if cu_atual is None or cu_atual not in _FSKUS:
        return {"acao": "indefinido", "motivo": "SKU atual não reconhecida", "sku_sugerida": None}
    i = _FSKUS.index(cu_atual)

    if houve_rejeicao or pico_util_pct >= 100 or overage_acumulado_pct > 20:
        alvo = _FSKUS[min(i + 1, len(_FSKUS) - 1)]
        return {"acao": "subir", "sku_sugerida": f"F{alvo}",
                "motivo": f"pico {pico_util_pct:.0f}% + rejeição/overage — no limite; "
                          f"F{alvo} dá ~2× de folga.",
                "urgencia": "alta"}
    if pico_util_pct >= 85:
        return {"acao": "atencao", "sku_sugerida": f"F{cu_atual}",
                "motivo": f"pico {pico_util_pct:.0f}% — perto do teto; monitore, um pico de "
                          f"refresh pode throttlar. Antes de subir, tente rebalancear jobs.",
                "urgencia": "media"}
    if pico_util_pct < 40 and i > 0:
        alvo = _FSKUS[i - 1]
        return {"acao": "descer", "sku_sugerida": f"F{alvo}",
                "motivo": f"pico só {pico_util_pct:.0f}% — F{cu_atual} está superdimensionada; "
                          f"F{alvo} ainda deixaria folga. (confirme picos sazonais antes.)",
                "urgencia": "baixa"}
    return {"acao": "manter", "sku_sugerida": f"F{cu_atual}",
            "motivo": f"pico {pico_util_pct:.0f}% — dimensionamento saudável.", "urgencia": "baixa"}


def diagnosticar_throttle(eventos: list) -> dict:
    """`eventos`: lista de dicts {estado, quando}. Resume por TIPO e severidade —
    distinguir delay (leve) de rejection (grave) é o coração do diagnóstico."""
    contagem = {}
    for e in eventos or []:
        estado = (e.get("estado") or "").split("/")[-1]  # 'Overloaded/InteractiveDelay' -> 'InteractiveDelay'
        if estado in _ESTAGIOS:
            contagem[estado] = contagem.get(estado, 0) + 1
    if not contagem:
        return {"houve_throttle": False, "resumo": "Sem eventos de throttle no período.",
                "rejeicao": False, "por_tipo": {}}
    rejeicao = any(k in ("InteractiveRejected", "AllRejected") for k in contagem)
    linhas = [f"{n}× {_ESTAGIOS[k]}" for k, n in sorted(contagem.items(), key=lambda x: -x[1])]
    return {"houve_throttle": True, "rejeicao": rejeicao,
            "por_tipo": contagem, "resumo": " · ".join(linhas)}


def classificar_pico_vs_divida(add_pct: float, burndown_pct: float,
                               cumulative_pct: float) -> dict:
    """>100% de CU assusta o leigo, mas há dois casos OPOSTOS (o app não explica):
    - carryforward ACUMULANDO (`cumulative` sobe, add > burndown) = dívida crescendo,
      vai throttlar mesmo sem novo job → AGIR;
    - overage protection absorvendo pico interativo, com burndown acompanhando =
      benigno. Essa leitura é onde quase todo mundo erra."""
    if cumulative_pct <= 0:
        return {"tipo": "sem_divida", "leitura": "Sem carryforward acumulado — capacidade folgada."}
    if add_pct > burndown_pct:
        return {"tipo": "divida_crescendo", "urgencia": "alta",
                "leitura": f"Carryforward ACUMULANDO ({cumulative_pct:.0f}% cumulativo, add>burndown) "
                           "— a dívida de smoothing cresce e vai throttlar mesmo sem novos jobs. Agir."}
    return {"tipo": "divida_drenando", "urgencia": "media",
            "leitura": f"Carryforward existe ({cumulative_pct:.0f}%) mas DRENANDO (burndown≥add) — "
                       "pico sendo absorvido; monitore, tende a normalizar se não empilhar mais jobs."}


def diagnosticar(dados: dict) -> dict:
    """Junta a interpretação num veredito acionável a partir dos dados coletados.
    `dados`: {sku, pico_util_pct, media_util_pct, eventos, overage:{add,burndown,cumulative},
              top_itens:[{item, cu_s, overloaded_min}]}."""
    cu = sku_atual_cu(dados.get("sku"))
    thr = diagnosticar_throttle(dados.get("eventos", []))
    ov = dados.get("overage", {}) or {}
    divida = classificar_pico_vs_divida(ov.get("add", 0), ov.get("burndown", 0), ov.get("cumulative", 0))
    sku = recomendar_sku(cu, dados.get("pico_util_pct", 0), thr["rejeicao"], ov.get("cumulative", 0))
    top = sorted(dados.get("top_itens", []), key=lambda x: -(x.get("cu_s") or 0))[:10]
    return {"sku_atual": dados.get("sku"), "throttle": thr, "divida_smoothing": divida,
            "recomendacao_sku": sku, "top_itens_cu": top,
            "pico_util_pct": dados.get("pico_util_pct"), "media_util_pct": dados.get("media_util_pct")}


# ── COLETA via SemPy/DAX (defensiva; roda em notebook Fabric) ─────────────────
def _sempy():
    try:
        import sempy.fabric as fabric  # noqa
        return fabric
    except Exception as e:
        raise RuntimeError("Este módulo roda dentro de um notebook Microsoft Fabric "
                           f"(precisa de sempy.fabric / semantic-link). Import falhou: {e}")


def descobrir_modelo(workspace: Optional[str] = None,
                     nome_provavel: str = "Fabric Capacity Metrics") -> dict:
    """Descobre o semantic model do Capacity Metrics App. Usa REST (não exige XMLA
    ReadWrite). Retorna {workspace, dataset} ou levanta erro claro se não achar."""
    fabric = _sempy()
    try:
        ds = fabric.list_datasets(workspace=workspace, mode="rest")
        nomes = list(ds["Dataset Name"]) if hasattr(ds, "__getitem__") else []
        alvo = next((n for n in nomes if "capacity metrics" in n.lower()), None) or \
               (nome_provavel if nome_provavel in nomes else None)
        if not alvo:
            raise RuntimeError(
                "Não encontrei o modelo 'Fabric Capacity Metrics' no workspace informado. "
                "Instale o Capacity Metrics App (como Capacity Admin) e aponte o workspace dele "
                f"em `workspace=`. Modelos vistos: {nomes[:10]}")
        return {"workspace": workspace, "dataset": alvo}
    except Exception as e:
        raise RuntimeError(f"Falha ao descobrir o modelo do Capacity Metrics: {e}")


def validar_schema(dataset: str, workspace: Optional[str] = None) -> dict:
    """Valida quais TABELAS esperadas existem no modelo (ele é 'não suportado' e
    versionado — os nomes podem ter mudado). Retorna {presentes, ausentes}."""
    fabric = _sempy()
    try:
        info = fabric.evaluate_dax(dataset=dataset, workspace=workspace,
                                   dax_string="EVALUATE INFO.TABLES()")
        col = next((c for c in info.columns if c.lower().endswith("name")), None)
        tabelas = set(str(v) for v in info[col]) if col else set()
        presentes = [t for t in TABELAS_ESPERADAS if t in tabelas]
        ausentes = [t for t in TABELAS_ESPERADAS if t not in tabelas]
        return {"presentes": presentes, "ausentes": ausentes, "todas": sorted(tabelas)}
    except Exception as e:
        return {"presentes": [], "ausentes": TABELAS_ESPERADAS, "erro": str(e)[:200]}


def coletar(dataset: str, capacity_id: str, dia: str,
            workspace: Optional[str] = None) -> dict:
    """Coleta defensiva dos dados de um dia para uma capacidade. Cada query é
    isolada — se uma tabela/medida mudou de nome (o modelo é versionado), o resto
    ainda vem, e a interpretação degrada com o que houver.

    ⚠ As MEDIDAS de utilização %/overage do app não têm nome público estável —
    confirme com `INFO.MEASURES()` no seu Fabric e ajuste `pico_util_pct`/`overage`
    se vierem zerados. Eventos e top-itens usam TABELAS (mais estáveis)."""
    fabric = _sempy()
    dados = {"sku": None, "pico_util_pct": 0.0, "media_util_pct": 0.0,
             "eventos": [], "overage": {"add": 0.0, "burndown": 0.0, "cumulative": 0.0},
             "top_itens": [], "avisos": []}

    def _dax(q):
        return fabric.evaluate_dax(dataset=dataset, workspace=workspace, dax_string=q)

    filtro = (f"MPARAMETER 'CapacitiesList' = {{\"{capacity_id}\"}}\n")

    # Eventos de throttle (tabela System events — a fonte-verdade de "houve throttle").
    try:
        ev = _dax(f"DEFINE {filtro} EVALUATE 'System events'")
        cst = next((c for c in ev.columns if "state" in c.lower() or "status" in c.lower()), None)
        ctm = next((c for c in ev.columns if "time" in c.lower() or "date" in c.lower()), None)
        if cst:
            dados["eventos"] = [{"estado": str(r[cst]), "quando": str(r[ctm]) if ctm else None}
                                for _, r in ev.iterrows()]
    except Exception as e:
        dados["avisos"].append(f"System events indisponível: {str(e)[:120]}")

    # Top itens por CU (Items × Timepoint Interactive Detail).
    try:
        top = _dax(f"""DEFINE {filtro}
          EVALUATE
            TOPN(20,
              SUMMARIZECOLUMNS('Items'[Item name], 'Items'[Item kind],
                "cu_s", CALCULATE(SUM('Timepoint Interactive Detail'[Total CU (s)]))),
              [cu_s], DESC)""")
        cnome = next((c for c in top.columns if "item name" in c.lower()), None)
        ccu = next((c for c in top.columns if c.lower().endswith("cu_s") or "cu_s" in c.lower()), None)
        if cnome and ccu:
            dados["top_itens"] = [{"item": str(r[cnome]), "cu_s": float(r[ccu] or 0)}
                                  for _, r in top.iterrows()]
    except Exception as e:
        dados["avisos"].append(f"Top itens indisponível: {str(e)[:120]}")

    return dados


def radar(capacity_id: str, dia: str, workspace: Optional[str] = None,
          sku: Optional[str] = None) -> dict:
    """Orquestra: descobre o modelo → valida schema → coleta → DIAGNOSTICA.
    `sku` (ex.: 'F64') alimenta a recomendação de dimensionamento."""
    modelo = descobrir_modelo(workspace)
    schema = validar_schema(modelo["dataset"], modelo["workspace"])
    dados = coletar(modelo["dataset"], capacity_id, dia, modelo["workspace"])
    dados["sku"] = sku
    diag = diagnosticar(dados)
    return {"modelo": modelo, "schema": schema, "diagnostico": diag, "avisos": dados.get("avisos", [])}
