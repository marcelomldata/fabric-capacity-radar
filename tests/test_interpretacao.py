"""Testes da camada de INTERPRETAÇÃO (pura Python — o diferencial do Radar).
Não precisa de Fabric: prova a lógica de recomendação de SKU, diagnóstico de
throttle e a leitura pico-vs-dívida. Rode: python -m pytest -q  (ou este arquivo)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from capacity_radar.radar import (
    sku_atual_cu, recomendar_sku, diagnosticar_throttle, classificar_pico_vs_divida,
    diagnosticar)

ok = 0
def t(nome, cond):
    global ok
    assert cond, f"FALHOU: {nome}"
    print("  ok:", nome); ok += 1

# sku_atual_cu
t("F64 -> 64", sku_atual_cu("F64") == 64)
t("f32 minusculo -> 32", sku_atual_cu("f32") == 32)
t("invalido -> None", sku_atual_cu("Premium") is None)

# recomendar_sku
r = recomendar_sku(32, 105, houve_rejeicao=True)
t("pico>100 + rejeicao -> subir p/ F64", r["acao"] == "subir" and r["sku_sugerida"] == "F64")
r = recomendar_sku(32, 88, houve_rejeicao=False)
t("pico 88% -> atencao, mantem SKU", r["acao"] == "atencao" and r["sku_sugerida"] == "F32")
r = recomendar_sku(64, 30, houve_rejeicao=False)
t("pico 30% -> descer p/ F32", r["acao"] == "descer" and r["sku_sugerida"] == "F32")
r = recomendar_sku(16, 60, houve_rejeicao=False)
t("pico 60% -> manter", r["acao"] == "manter")
r = recomendar_sku(2, 20, houve_rejeicao=False)
t("F2 pico baixo nao desce abaixo de F2", r["acao"] in ("descer", "manter") and r["sku_sugerida"] is not None)

# diagnosticar_throttle
d = diagnosticar_throttle([{"estado": "Overloaded/InteractiveRejected"},
                           {"estado": "Overloaded/InteractiveDelay"},
                           {"estado": "Active/NotOverloaded"}])
t("rejeicao detectada", d["houve_throttle"] and d["rejeicao"] is True)
t("delay contado", d["por_tipo"].get("InteractiveDelay") == 1)
t("estado benigno ignorado", "NotOverloaded" not in d["por_tipo"])
t("sem eventos -> sem throttle", diagnosticar_throttle([])["houve_throttle"] is False)

# classificar_pico_vs_divida
t("divida crescendo", classificar_pico_vs_divida(30, 10, 120)["tipo"] == "divida_crescendo")
t("divida drenando", classificar_pico_vs_divida(10, 30, 120)["tipo"] == "divida_drenando")
t("sem divida", classificar_pico_vs_divida(0, 0, 0)["tipo"] == "sem_divida")

# ── Caminho de DADO AUSENTE (o perigo que o skeptic pegou) ──────────────────
t("pico None -> indefinido (nunca 'descer' sem medir)",
  recomendar_sku(64, None, houve_rejeicao=False)["acao"] == "indefinido")
t("util_medido False -> indefinido",
  recomendar_sku(64, 20, houve_rejeicao=False, util_medido=False)["acao"] == "indefinido")
t("overage None -> nao_medido", classificar_pico_vs_divida(None, None, None)["tipo"] == "nao_medido")

# diagnosticar com coleta VAZIA (modelo ilegível): NÃO pode dizer 'sem throttle' nem 'descer'
_vazio = diagnosticar({"sku": "F64", "pico_util_pct": None, "util_medido": False,
                       "overage": None, "eventos": [], "top_itens": [],
                       "coletado": {"eventos": False, "top_itens": False}})
t("coleta vazia -> throttle INCONCLUSIVO (nao 'sem throttle')",
  _vazio["throttle"]["houve_throttle"] is None and "INCOMPLETA" in _vazio["throttle"]["resumo"])
t("coleta vazia -> recomendacao SKU indefinida (nao 'descer')",
  _vazio["recomendacao_sku"]["acao"] == "indefinido")

# diagnosticar com eventos LIDOS e sem throttle: aí SIM pode dizer 'sem throttle'
_ok = diagnosticar({"sku": "F64", "pico_util_pct": None, "util_medido": False,
                    "overage": None, "eventos": [], "top_itens": [],
                    "coletado": {"eventos": True, "top_itens": True}})
t("eventos lidos e vazios -> 'sem throttle' (legitimo)",
  _ok["throttle"]["houve_throttle"] is False)

print(f"\n  {ok} provas passaram.\n")
