import json
from collections import Counter

d = json.load(open('impacto_cnpj.json', encoding='utf-8'))
matriz = d['matriz_impacto']
print(f"Total impactos: {len(matriz)}\n")

# Distribuicao por pattern_matched
pats = Counter()
for m in matriz:
    obs = m['observacoes']
    pat = obs.split('| ')[-1]
    pats[pat] += 1

print("=== Top padroes que geraram impactos ===")
for pat, count in pats.most_common(30):
    print(f"  {count:3d} | {pat[:80]}")

# Impactos que usavam [^\d]\d{14}[^\d]
print("\n=== Impactos capturados por d{14} (padrao removido) ===")
for m in matriz:
    obs = m['observacoes']
    if 'd{14}' in obs and 'd{2}' not in obs:
        print(f"  {m['id']} | {m['repositorio']} | {m['area']}")
        print(f"    trecho: {m['evidencia']['trecho_codigo'][:100]}")

# Impactos CFG-001
print("\n=== Impactos CFG-001 ===")
for m in matriz:
    if 'CFG-001' in m['observacoes']:
        print(f"  {m['id']} | {m['repositorio']}")
        print(f"    trecho: {m['evidencia']['trecho_codigo'][:100]}")
        print(f"    regra:  {m['observacoes']}")
