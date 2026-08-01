"""
Fabric Capacity Radar — rode DENTRO de um notebook Microsoft Fabric.

Descobre o modelo do Capacity Metrics App, valida o schema (o modelo é versionado),
coleta throttle/CU e DIAGNOSTICA: houve throttle e de que tipo, quão perto do limite,
qual item queima CU, e a recomendação de F-SKU.

Pré-requisitos: capacidade Fabric + Capacity Metrics App instalado (por um Capacity
Admin) + o workspace do app acessível. SemPy usa REST (não exige XMLA ReadWrite).
"""
from capacity_radar.radar import radar
import os

CAPACITY_ID = os.getenv("FABRIC_CAPACITY_ID")           # GUID da capacidade
WORKSPACE = os.getenv("FABRIC_METRICS_WORKSPACE")        # workspace do Capacity Metrics App
SKU = os.getenv("FABRIC_SKU")                            # ex.: F64 (p/ recomendação de dimensionamento)

if not CAPACITY_ID:
    raise ValueError("Defina FABRIC_CAPACITY_ID (o GUID da capacidade). Liste com "
                     "`import sempy.fabric as fabric; fabric.list_capacities()`.")

r = radar(CAPACITY_ID, workspace=WORKSPACE, sku=SKU)

print(f"Modelo: {r['modelo']}")
esq = r["schema"]
if esq.get("ausentes"):
    print(f"⚠ Tabelas esperadas AUSENTES (modelo pode ter mudado de versão): {esq['ausentes']}")
    print(f"  Tabelas presentes no modelo: {esq.get('todas', [])[:15]}")

d = r["diagnostico"]
print("\n── DIAGNÓSTICO DE CAPACIDADE ──")
print(f"SKU atual: {d['sku_atual']} · pico util: {d['pico_util_pct']}% · média: {d['media_util_pct']}%")
print(f"Throttle: {d['throttle']['resumo']}")
print(f"Dívida de smoothing: {d['divida_smoothing']['leitura']}")
rec = d["recomendacao_sku"]
print(f"➜ Recomendação: {rec['acao'].upper()} ({rec.get('sku_sugerida')}) — {rec['motivo']}")
if d["top_itens_cu"]:
    print("Top itens por CU(s):")
    for it in d["top_itens_cu"][:5]:
        print(f"  - {it.get('item')}: {it.get('cu_s')} CU-s")

for a in r["avisos"]:
    print(f"  ⚠ {a}")

print("\nNOTA (v0.1): o custo NÃO é o eixo — Fabric é capacidade de preço fixo; isto é "
      "assessment de CAPACIDADE/throttling. A v0.1 entrega o DIAGNÓSTICO DE THROTTLE "
      "(eventos) e o RANKING DE CU por item (interativo+background). A recomendação de "
      "F-SKU e a leitura pico-vs-dívida ficam 'indefinido' de propósito: dependem das "
      "medidas de utilização %/overage, cujos nomes o app não mantém estáveis. Para "
      "ligá-las (v0.2): rode `fabric.evaluate_dax(dataset, 'EVALUATE INFO.MEASURES()')` "
      "no SEU Fabric, ache os nomes reais das medidas e preencha `pico_util_pct`/`overage`.")
