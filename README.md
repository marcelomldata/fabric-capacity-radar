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
graça, melhor. O valor está na **leitura sênior** que o app não conclui — e sobre uma
fundação **estável e ancorada em eventos** (tabelas + `System events`), não nas medidas
versionadas do app:

- **Atribuição causal do throttle** *(o que o app NÃO faz)* — no timepoint de cada evento
  de throttle, QUAL item queimou CU, ranqueado por `[Timepoint CU (s)]` (a parcela
  suavizada que aterrissou ali — não por hora de início, que confunde causa com vítima).
- **Utilização % e overage exatos** — `Σ [Timepoint CU (s)] / (F × 30) × 100` no timepoint
  (capacidade de um timepoint de 30 s = F×30 CU-s; fórmula validada contra a doc). Overage
  = `MAX(0, ΣTimepointCU − F×30)`, o pico real acima de 100%.
- **Diagnóstico de throttle por tipo** — de `System events` (verdade-fundamento,
  event-sourced): *Interactive Delay* (leve, +20s) × *Interactive/Background Rejection*
  (graves). E **não confunde "não li o modelo" com "não há throttle"**.
- **Recomendação de F-SKU dirigida pelos EVENTOS** — rejeições → subir (com o quanto);
  só delay → no limite, rebalanceie; sem throttle → saudável. **Nunca** recomenda *descer*
  a partir de ausência de dado.

**Limites honestos, declarados** (é o que faz a ferramenta crível a um sênior):

- A recomendação de **DOWNSIZE** exige a utilização média da JANELA (não só nos timepoints
  de throttle) — é a próxima frente; sem esse dado o Radar não sugere diminuir SKU.
- **Não** prometemos paridade numérica com `Add%/Burndown%/Cumulative%` do app (pools
  interativo/background separados, billable-only, surge/autoscale, borda de janela). O que
  entregamos é exato (util% e overage por timepoint) ou event-sourced (o *quando* do
  throttle) — carryforward reconstruído, se usado, é rotulado como estimativa.
- O semantic model do app é "não suportado / versionado" — a ferramenta **descobre e valida
  os nomes em runtime** (`INFO.TABLES()`), com fallback claro; nunca hardcoda cego.

A interpretação é **pura Python e testada** (`tests/`, 24 provas), incluindo o caminho de
**dado ausente** — garante que ausência de leitura nunca vira uma recomendação confiante.

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
