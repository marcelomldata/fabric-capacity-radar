"""
Fabric Capacity Radar — rode DENTRO de um notebook Microsoft Fabric.

Descobre o modelo do Capacity Metrics App, valida o schema (o modelo é versionado),
lê os eventos de throttle (System events) e ATRIBUI a causa no timepoint de cada um
(qual item queimou CU), com utilização% e overage exatos. Recomenda F-SKU dirigido
pelos eventos.

Pré-requisitos: capacidade Fabric + Capacity Metrics App instalado (por um Capacity
Admin) + o workspace do app acessível. SemPy usa REST (não exige XMLA ReadWrite).
"""
from capacity_radar.radar import radar
import os

CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID")           # GUID da capacidade
WORKSPACE = os.getenv("FABRIC_METRICS_WORKSPACE")        # workspace do Capacity Metrics App
SKU = os.getenv("FABRIC_SKU")                            # ex.: F64 — liga util%/overage + recomendação

if not CAPACITY_ID:
    raise ValueError("Defina FABRIC_CAPACITY_ID (o GUID da capacidade). Liste com "
                     "`import sempy.fabric as fabric; fabric.list_capacities()`.")

r = radar(CAPACITY_ID, workspace=WORKSPACE, sku=SKU)

print(f"Modelo: {r['modelo']}")
esq = r["schema"]
if esq.get("ausentes"):
    print(f"⚠ Tabelas esperadas AUSENTES (modelo pode ter mudado de versão): {esq['ausentes']}")
    print(f"  Tabelas presentes: {esq.get('todas', [])[:15]}")

d = r["diagnostico"]
print("\n── DIAGNÓSTICO DE CAPACIDADE ──")
print(f"SKU atual: {d['sku_atual']}")
print(f"Throttle: {d['throttle']['resumo']}")
rec = d["recomendacao_sku"]
print(f"➜ Recomendação: {rec['acao'].upper()} ({rec.get('sku_sugerida')}) — {rec['motivo']}")

if d["atribuicao_causal"]:
    print("\n── ATRIBUIÇÃO CAUSAL (quem causou cada throttle) ──")
    for c in d["atribuicao_causal"]:
        util = f"{c['util_pct']}%" if c.get("util_pct") is not None else "util% (informe SKU)"
        over = f"+{c['overage_cu']} CU-s acima" if c.get("overage_cu") else "no teto"
        print(f"  {c['timepoint']} [{c['tipo']}] — {util}, {over}:")
        for it in c["itens"][:3]:
            print(f"      • {it['item']}: {it['cu_s']} CU-s (no timepoint)")

for a in r["avisos"]:
    print(f"  ⚠ {a}")

print("\nNOTA: o custo NÃO é o eixo — Fabric é capacidade de preço fixo; isto é assessment "
      "de CAPACIDADE/throttling. Entregue nesta versão, exato: diagnóstico de throttle "
      "(event-sourced), atribuição causal por item, util% e overage por timepoint. A leitura "
      "de DOWNSIZE (utilização média da janela) é a próxima frente — o Radar NÃO recomenda "
      "diminuir SKU sem esse dado, de propósito.")
