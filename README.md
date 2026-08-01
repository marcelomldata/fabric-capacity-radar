# Fabric Capacity Radar

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Assessment de **capacidade e throttling** do Microsoft Fabric. O app nativo *Capacity
Metrics* responde **"quanto"**; o Radar responde **"por causa de quê, quão perto do
limite, e o que fazer"**.

## Por que capacidade, e não "custo"

O Fabric cobra por **capacidade de preço FIXO** (F-SKU) com *smoothing* e *throttling*.
Somar CU × preço dá um número que **não existe na sua fatura** (a fatura é a reserva
fixa). Por isso este **não é** um "FinOps de consumo" — a pergunta certa é de
capacidade: **você está sendo throttled? tem folga? qual item queima CU? deve
redimensionar o F-SKU?**

## O que o Radar entrega

Reproduzir os gráficos do Capacity Metrics App é trabalho perdido — ele já faz isso, de
graça, melhor. O valor está na **leitura sênior** que o app não conclui.

**Vivo na v0.1** (lê de TABELAS do modelo, mais estáveis):
- **Diagnóstico de throttle por tipo** — distingue *Interactive Delay* (leve, +20s) de
  *Interactive Rejection* e *Background Rejection* (graves), lido de `System events`. E
  **não confunde "não li o modelo" com "não há throttle"** — leitura incompleta é dita
  como tal, nunca como "capacidade folgada".
- **Ranking de CU por item** (interativo + background) — quem mais queima capacidade.

**Planejado (v0.2 — depende das medidas de utilização %/overage do app):**
- **Headroom → decisão de F-SKU** (*"78% de pico; F64 dá ~2× de folga"*).
- **"Pico real" vs "dívida de smoothing"** (carryforward acumulando × drenando).
- **Atribuição causal do throttle a um item num timepoint** (join temporal evento×item).

Por que a v0.2 não veio junto: as MEDIDAS de utilização/overage do Capacity Metrics App
**não têm nome público estável** (a Microsoft declara o modelo "não suportado para
consumo externo"). Fabricar um `pico = 0` a partir de dado ausente faria a ferramenta
recomendar *"diminua a SKU"* — o pior erro num assessment de dimensionamento. Então a
v0.1 **suspende** essas leituras honestamente (retornam "indefinido / não medido") em vez
de inventar um número. Ligá-las é confirmar os nomes reais via `INFO.MEASURES()` no seu
tenant — trabalho de projeto, não de isca.

A camada de interpretação é **pura Python e testada** (`tests/`, 15 provas), incluindo o
caminho de **dado ausente** (garante que ausência nunca vira recomendação).

## Como funciona

Roda num **notebook Microsoft Fabric** via **SemPy** (`sempy.fabric.evaluate_dax`, que
usa REST e é classificado como baixa prioridade — não agrava a capacidade que mede).

> ⚠ O modelo semântico do Capacity Metrics App é **"não suportado para consumo externo"**
> pela Microsoft e seus nomes de tabela/medida **mudam entre versões**. O Radar é
> **defensivo**: descobre o modelo e **valida os nomes em runtime** (`INFO.TABLES()`),
> com fallback claro — nunca hardcoda cego.

## Quick start

```bash
pip install -e .            # + semantic-link (SemPy) no ambiente Fabric
```

No notebook Fabric, rode `notebooks/01_capacity_radar.py` com:

```bash
export FABRIC_CAPACITY_ID=<guid-da-capacidade>       # fabric.list_capacities()
export FABRIC_METRICS_WORKSPACE=<workspace-do-app>
export FABRIC_SKU=F64                                # para a recomendação de dimensionamento
```

Pré-requisitos: capacidade Fabric ativa (qualquer SKU, inclusive F2), o **Capacity
Metrics App** instalado por um **Capacity Admin**.

## Precisa agir sobre o diagnóstico?

O Radar aponta o problema e o caminho. Redimensionar, rebalancear refreshes e reprojetar
a capacidade é o trabalho da **[ML Data e IA](mailto:marcelo@mldata.com.br)**.

## Licença

Apache License 2.0.
