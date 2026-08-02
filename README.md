# Fabric Capacity Radar

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Assessment de **capacidade e throttling** do Microsoft Fabric. O app nativo *Capacity
Metrics* responde **"quanto"**; o Radar responde **"houve throttle, por causa de qual
item, e o que fazer"** — com um gate de cronicidade que separa pico isolado de problema
crônico. *(A leitura de "quanta folga tenho" — utilização média da janela — é a próxima
frente; ver Limites.)*

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
- **Utilização % e overage do timepoint (estimados)** — `Σ [Timepoint CU (s)] / (F × 30) × 100`
  sobre TODOS os itens no timepoint (capacidade do timepoint de 30 s = F×30 CU-s; fórmula
  validada contra a doc). ⚠ util%>100% num timepoint **não é throttle** (throttle = esgotar
  capacidade de janela, vem de System events); e ainda não filtra *billable*.
- **Diagnóstico de throttle por tipo** — de `System events` (verdade-fundamento,
  event-sourced): *Interactive Delay* (leve, +20s) × *Interactive/Background Rejection*
  (graves). Três estados, não dois: "não li o modelo" e "li mas não reconheci os rótulos"
  viram **inconclusivo**, nunca "não há throttle".
- **Recomendação de F-SKU com GATE DE CRONICIDADE** — rejeição **crônica** (≥2 dias
  distintos) → considerar upsize **após** a escada de remédios (rebalancear → load-balance →
  pause/resume → só então subir SKU); rejeição **isolada** → investigar, **não** "dobre a
  fatura"; sem throttle → saudável. Nunca recomenda *descer* sem utilização de janela.

**Limites honestos, declarados** (é o que faz a ferramenta crível a um sênior):

- **"Quanta folga tenho?" e o DOWNSIZE** exigem a utilização média da JANELA (p50/p95, não só
  nos timepoints de throttle). É a próxima frente — depende de introspecção do modelo no seu
  Fabric; sem esse dado o Radar não afirma folga nem sugere diminuir SKU.
- **Não** prometemos paridade numérica com `Add%/Burndown%/Cumulative%` do app (pools
  interativo/background separados, *billable-only*, surge/autoscale, borda de janela).
- **Alinhamento de timepoint e fuso** entre `System events` e as tabelas de detalhe: a
  ferramenta faz *floor* ao bucket de 30 s, mas assume mesmo fuso — **validar no seu Fabric**.
- O semantic model do app é "não suportado / versionado" — a ferramenta **descobre e valida
  os nomes em runtime** (`INFO.TABLES()`), com fallback claro; nunca hardcoda cego.

A interpretação é **pura Python e testada** (`tests/`, 30 provas), incluindo o caminho de
**dado ausente** — garante que ausência de leitura nunca vira uma recomendação confiante.

## Como funciona

Roda num **notebook Microsoft Fabric** via **SemPy**. A descoberta do modelo usa
`sempy.fabric.list_datasets(mode="rest")` (REST puro, dispensa XMLA). Já a leitura de
schema e dados usa `sempy.fabric.evaluate_dax`, que **lê pelo endpoint XMLA** — por isso
exige o **XMLA read-only habilitado** na capacidade (leitura basta; NÃO precisa
read-write). As requisições vão como **baixa prioridade / interativas**, para não agravar
a capacidade que medem ([doc oficial](https://learn.microsoft.com/en-us/fabric/data-science/read-write-power-bi-python#use-python-to-read-data-from-semantic-models)).

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
Metrics App** instalado por um **Capacity Admin**, e o **endpoint XMLA em read-only
habilitado** na capacidade (o `evaluate_dax` lê por XMLA; sem isso a leitura de schema
e dados falha).

## Precisa agir sobre o diagnóstico?

O Radar aponta o problema e o caminho. Redimensionar, rebalancear refreshes e reprojetar
a capacidade é o trabalho da **[ML Data e IA](mailto:marcelo@mldata.com.br)**.

## Licença

Apache License 2.0.
