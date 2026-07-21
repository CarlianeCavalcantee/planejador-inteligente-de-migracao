"""
Agrupa repositórios por similaridade de perfil de impacto e sugere
divisão em 2 trilhas paralelas para trabalho em dupla.

Uso:
    python tools/similarity.py [arquivo.json]
"""

import io
import json
import sys
from collections import defaultdict
from pathlib import Path

# Força UTF-8 no terminal Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

_ROOT = Path(__file__).resolve().parent.parent
JSON_FILE = sys.argv[1] if len(sys.argv) > 1 else str(_ROOT / "docs" / "output" / "impacto_cnpj.json")

d = json.load(open(JSON_FILE, encoding="utf-8"))
ordem = d["ordem_migracao"]

# ---------------------------------------------------------------------------
# Nomes legíveis para cada área
# ---------------------------------------------------------------------------
AREA_LABEL = {
    "Banco de Dados":      "Banco de Dados",
    "Backend":             "Backend (validadores, lógica)",
    "API/Contrato":        "API / Contrato",
    "Frontend":            "Frontend (telas, máscaras)",
    "Integrações":         "Integrações (Kafka, SOAP, REST)",
    "Processamento/Batch": "Batch / ETL / Fiscal",
    "Segurança/LGPD":      "Segurança / LGPD",
    "Infraestrutura/CI":   "Infra / CI-CD",
    "Configuração":        "Configuração",
    "Testes/Qualidade":    "Testes",
    "Documentação":        "Documentação",
    "Pessoa Jurídica/PJ":  "Pessoa Jurídica",
}

ABBREV = {
    "Banco de Dados": "BD", "Backend": "BE", "API/Contrato": "API",
    "Frontend": "FE", "Integrações": "INT", "Processamento/Batch": "BATCH",
    "Segurança/LGPD": "SEC", "Infraestrutura/CI": "INFRA",
    "Configuração": "CFG", "Testes/Qualidade": "TEST",
    "Documentação": "DOC", "Pessoa Jurídica/PJ": "PJ",
}

def fmt_areas(areas):
    return " + ".join(ABBREV.get(a, a[:4]) for a in sorted(areas))

# ---------------------------------------------------------------------------
# 1. Monta perfil de cada repo
# ---------------------------------------------------------------------------
repos = []
for m in ordem:
    areas = frozenset(a["area"] for a in m["areas"])
    repos.append({
        "modulo": m["modulo"],
        "passo":  m["passo"],
        "total":  m["total_impactos"],
        "alta":   m["impactos_alta_complexidade"],
        "dual":   m["requerem_compatibilidade_dual"],
        "areas":  areas,
    })

# ---------------------------------------------------------------------------
# 2. Agrupa repos com perfil parecido (Jaccard >= 0.5)
# ---------------------------------------------------------------------------
def jaccard(a, b):
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)

clusters, used = [], set()
for i, r in enumerate(repos):
    if i in used:
        continue
    cluster = [r]
    used.add(i)
    for j, s in enumerate(repos):
        if j not in used and jaccard(r["areas"], s["areas"]) >= 0.5:
            cluster.append(s)
            used.add(j)
    clusters.append(cluster)

clusters.sort(key=lambda c: sum(r["alta"] for r in c), reverse=True)

# ---------------------------------------------------------------------------
# 3. Divide em 2 trilhas balanceadas pela quantidade de impactos difíceis
# ---------------------------------------------------------------------------
trilhas = [[], []]
carga = [0, 0]
for cluster in clusters:
    t = 0 if carga[0] <= carga[1] else 1
    trilhas[t].extend(cluster)
    carga[t] += sum(r["alta"] for r in cluster)

# ---------------------------------------------------------------------------
# 4. Exibe
# ---------------------------------------------------------------------------
SEP = "=" * 72

print(f"\n{SEP}")
print(f"  GRUPOS DE REPOS COM PERFIL PARECIDO  ({len(clusters)} grupos)")
print(f"  (repos no mesmo grupo têm as mesmas áreas impactadas)")
print(SEP)

for i, cluster in enumerate(clusters, 1):
    areas_union = frozenset().union(*(r["areas"] for r in cluster))
    total_alta = sum(r["alta"] for r in cluster)
    total_imp  = sum(r["total"] for r in cluster)
    print(f"\nGrupo {i}  —  areas: {fmt_areas(areas_union)}")
    print(f"           total de impactos dificeis (Alta): {total_alta}  |  total geral: {total_imp}")
    print(f"  {'Repo':<42} {'Dificeis':>9} {'Total':>7} {'Dual':>6}")
    print(f"  {'-'*42} {'-'*9} {'-'*7} {'-'*6}")
    for r in sorted(cluster, key=lambda x: -x["alta"]):
        dual_flag = "  sim" if r["dual"] > 0 else "  ---"
        print(f"  {r['modulo']:<42} {r['alta']:>9} {r['total']:>7}{dual_flag}")

print(f"\n{SEP}")
print(f"  SUGESTAO DE DIVISAO PARA 2 PESSOAS TRABALHANDO AO MESMO TEMPO")
print(f"  (cada trilha tem repos parecidos entre si, carga equilibrada)")
print(SEP)

for t, (trilha, c) in enumerate(zip(trilhas, carga), 1):
    total_imp = sum(r["total"] for r in trilha)
    print(f"\n  PESSOA {t}  —  {c} impactos dificeis  |  {total_imp} impactos no total")
    print(f"  {'Ordem':>6}  {'Repo':<42} {'Dificeis':>9} {'Total':>7}  Areas")
    print(f"  {'-'*6}  {'-'*42} {'-'*9} {'-'*7}  {'-'*30}")
    for r in sorted(trilha, key=lambda x: x["passo"]):
        print(f"  {r['passo']:>6}  {r['modulo']:<42} {r['alta']:>9} {r['total']:>7}  {fmt_areas(r['areas'])}")

delta = abs(carga[0] - carga[1])
total_alta = carga[0] + carga[1]
pct = round(delta / total_alta * 100) if total_alta else 0
print(f"\n  Diferenca de carga entre as pessoas: {delta} impactos dificeis ({pct}%)")
print(f"  Quanto menor esse numero, mais equilibrada a divisao.\n")

# ---------------------------------------------------------------------------
# 5. Alerta de repos que precisam de coordenacao entre as duas pessoas
# ---------------------------------------------------------------------------
criticos = {"Banco de Dados", "API/Contrato"}
cross = defaultdict(list)
for r in repos:
    for area in r["areas"] & criticos:
        cross[area].append(r["modulo"])

alertas = {area: mods for area, mods in cross.items() if len(mods) > 1}
if alertas:
    print(f"  ATENCAO — coordenar antes de fazer merge:")
    for area, mods in alertas.items():
        label = AREA_LABEL.get(area, area)
        print(f"\n  {label}")
        print(f"  Esses repos mexem na mesma area e precisam ser alinhados:")
        for m in mods:
            print(f"    - {m}")
    print(f"\n  Sugestao: definir quem faz a migration de banco / versao de API primeiro,")
    print(f"  e so depois a outra pessoa sobe o repo que depende disso.\n")
