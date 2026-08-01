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

## O que o Radar entrega (a interpretação, não o dashboard)

Reproduzir os gráficos do Capacity Metrics App é trabalho perdido — ele já faz isso, de
graça, melhor. O valor está na **leitura sênior** que o app não conclui:

- **Atribuição causal do throttle** — cruza `System events` com o detalhe do timepoint:
  *"o throttle das 14:32 foi o refresh do modelo X, não os relatórios."*
- **Headroom → decisão de F-SKU** — traduz pico/média + rejeições numa recomendação:
  *"78% de pico com 3 delays/semana; F64 dá ~2× de folga; F32 volta a throttlar em
  picos de refresh."*
- **"Pico real" vs "dívida de smoothing"** — `>100%` assusta, mas há dois casos
  opostos: carryforward **acumulando** (vai throttlar mesmo sem novos jobs → agir) vs.
  overage **drenando** (benigno). Essa leitura é onde quase todo mundo erra.
- **Throttle por tipo** — distingue *Interactive Delay* (leve, +20s) de *Interactive
  Rejection* e *Background Rejection* (graves).

A camada de interpretação é **pura Python e testada** (`tests/`) — 15 provas cobrem a
recomendação de SKU, o diagnóstico de throttle e a leitura pico-vs-dívida.

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
