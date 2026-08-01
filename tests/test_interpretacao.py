"""Testes da camada de INTERPRETAÇÃO (pura Python — o diferencial do Radar).
Não precisa de Fabric: prova a recomendação event-driven de SKU, o diagnóstico de
throttle (incl. 'não li' × 'sem throttle'), e as fórmulas exatas util%/overage.
Rode: python tests/test_interpretacao.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from capacity_radar.radar import (
    sku_atual_cu, diagnosticar_throttle, recomendar_sku,
    utilizacao_pct, overage_cu, diagnosticar, _timepoint_dax)

ok = 0
def t(nome, cond):
    global ok
    assert cond, f"FALHOU: {nome}"
    print("  ok:", nome); ok += 1

# ── sku_atual_cu ──
t("F64 -> 64", sku_atual_cu("F64") == 64)
t("f32 -> 32", sku_atual_cu("f32") == 32)
t("invalido -> None", sku_atual_cu("Premium") is None)
t("None -> None", sku_atual_cu(None) is None)

# ── utilizacao_pct e overage (fórmula validada: cap do timepoint = F×30 CU-s) ──
t("F2 cap=60, cu=90 -> 150%", utilizacao_pct(90, 2) == 150.0)
t("F2 cu=30 -> 50%", utilizacao_pct(30, 2) == 50.0)
t("sem F -> None", utilizacao_pct(90, None) is None)
t("overage F2 cu=90 -> 30", overage_cu(90, 2) == 30.0)
t("overage F2 cu=30 -> 0 (nao negativo)", overage_cu(30, 2) == 0.0)
t("overage sem F -> None", overage_cu(90, None) is None)

# ── diagnosticar_throttle: 'não li' × 'li e é 0' ──
d = diagnosticar_throttle([{"estado": "Overloaded/InteractiveRejected"},
                           {"estado": "Overloaded/InteractiveDelay"},
                           {"estado": "Active/NotOverloaded"}])
t("rejeicao detectada", d["houve_throttle"] and d["rejeicao"] is True)
t("delay contado", d["por_tipo"].get("InteractiveDelay") == 1)
t("estado benigno ignorado", "NotOverloaded" not in d["por_tipo"])
t("lida e vazia -> False (legitimo)", diagnosticar_throttle([])["houve_throttle"] is False)
t("NAO lida -> None (inconclusivo, nunca 'sem throttle')",
  diagnosticar_throttle([], eventos_lidos=False)["houve_throttle"] is None)

# ── diagnosticar_throttle: cronicidade + estados irreconhecíveis ──
d_unk = diagnosticar_throttle([{"estado": "Weird/NovoEstado", "quando": "2026-08-01 10:00:00"}])
t("estados irreconheciveis (mas ha linhas) -> inconclusivo, NAO 'saudavel'",
  d_unk["houve_throttle"] is None)
d_cron = diagnosticar_throttle([
  {"estado": "Overloaded/InteractiveRejected", "quando": "2026-07-30 10:00:00"},
  {"estado": "Overloaded/InteractiveRejected", "quando": "2026-07-31 11:00:00"}])
t("rejeicao em 2 dias -> dias_rejeicao=2", d_cron["dias_rejeicao"] == 2)

# ── recomendar_sku: EVENT-DRIVEN + GATE DE CRONICIDADE ──
thr_cronico = {"houve_throttle": True, "rejeicao": True, "por_tipo": {"InteractiveRejected": 5}, "dias_rejeicao": 3}
r = recomendar_sku(32, thr_cronico)
t("rejeicao CRONICA (3 dias) -> subir p/ F64", r["acao"] == "subir" and r["sku_sugerida"] == "F64")
thr_isolada = {"houve_throttle": True, "rejeicao": True, "por_tipo": {"InteractiveRejected": 1}, "dias_rejeicao": 1}
r = recomendar_sku(32, thr_isolada)
t("rejeicao ISOLADA (1 dia) -> investigar, NAO 'dobre a fatura'",
  r["acao"] == "investigar" and r["sku_sugerida"] == "F32")
thr_delay = {"houve_throttle": True, "rejeicao": False, "por_tipo": {"InteractiveDelay": 2}, "dias_rejeicao": 0}
t("so delay -> atencao, mantem SKU", recomendar_sku(32, thr_delay)["acao"] == "atencao")
thr_ok = {"houve_throttle": False, "rejeicao": False, "por_tipo": {}, "dias_rejeicao": 0}
t("sem throttle -> 'sem_throttle' (NAO 'descer' sem util de janela)",
  recomendar_sku(64, thr_ok)["acao"] == "sem_throttle")
thr_none = {"houve_throttle": None, "rejeicao": False, "por_tipo": {}, "dias_rejeicao": 0}
t("leitura incompleta -> indefinido", recomendar_sku(64, thr_none)["acao"] == "indefinido")
t("SKU desconhecida -> indefinido", recomendar_sku(None, thr_cronico)["acao"] == "indefinido")
t("F2048 rejeicao cronica nao estoura a escada", recomendar_sku(2048, thr_cronico)["sku_sugerida"] == "F2048")

# ── _timepoint_dax: FLOOR ao bucket de 30s (o skeptic apontou sem teste) ──
t("floor :47 -> :30", _timepoint_dax("2026-08-01 14:32:47") == "( DATE(2026,8,1) + TIME(14,32,30) )")
t("floor :12 -> :00 (com T e fracao/tz)",
  _timepoint_dax("2026-08-01T14:32:12.500+00:00") == "( DATE(2026,8,1) + TIME(14,32,0) )")
t("data invalida -> None", _timepoint_dax("ontem de manha") is None)

# ── diagnosticar: coleta VAZIA (modelo ilegível) nunca engana ──
_vazio = diagnosticar({"sku": "F64", "eventos": [], "causas": [],
                       "coletado": {"eventos": False, "causas": False}})
t("coleta vazia -> throttle INCONCLUSIVO", _vazio["throttle"]["houve_throttle"] is None
  and "INCOMPLETA" in _vazio["throttle"]["resumo"])
t("coleta vazia -> recomendacao indefinida (nao 'sem_throttle' nem 'descer')",
  _vazio["recomendacao_sku"]["acao"] == "indefinido")
_lido = diagnosticar({"sku": "F64", "eventos": [], "causas": [],
                      "coletado": {"eventos": True, "causas": False}})
t("eventos lidos e vazios -> sem_throttle legitimo",
  _lido["recomendacao_sku"]["acao"] == "sem_throttle")

print(f"\n  {ok} provas passaram.\n")
