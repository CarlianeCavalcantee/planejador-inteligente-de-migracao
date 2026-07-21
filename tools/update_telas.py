"""Atualiza impacto_cnpj.json e .md com a secao telas_qa."""
import json
from core.output import _build_telas_qa, generate_markdown

with open("impacto_cnpj.json", encoding="utf-8") as f:
    d = json.load(f)

d["telas_qa"] = _build_telas_qa(d["matriz_impacto"])

with open("impacto_cnpj.json", "w", encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)

with open("impacto_cnpj.md", "w", encoding="utf-8") as f:
    f.write(generate_markdown(d))

print("OK -", len(d["telas_qa"]), "telas salvas")
