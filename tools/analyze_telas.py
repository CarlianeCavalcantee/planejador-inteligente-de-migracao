import json
from collections import defaultdict

d = json.load(open('impacto_cnpj.json', encoding='utf-8'))
matriz = d['matriz_impacto']

print("=== FRONTEND ===")
for m in [x for x in matriz if x['area'] == 'Frontend']:
    print(f"  {m['repositorio']:30s} | {m['evidencia']['arquivo']}")

print("\n=== BACKEND - arquivos com 'controller' ou 'service' ou 'usecase' ===")
for m in [x for x in matriz if x['area'] == 'Backend']:
    arq = m['evidencia']['arquivo'].lower()
    if any(k in arq for k in ('controller', 'service', 'usecase', 'bean', 'resource')):
        print(f"  {m['repositorio']:30s} | {m['evidencia']['arquivo']}")

print("\n=== BATCH - jasper/relatorio ===")
for m in [x for x in matriz if x['area'] == 'Processamento/Batch']:
    arq = m['evidencia']['arquivo'].lower()
    if any(k in arq for k in ('jrxml', 'relatorio', 'report', 'comprovante')):
        print(f"  {m['repositorio']:30s} | {m['evidencia']['arquivo']}")

print("\n=== REPOS com impacto ===")
repos = defaultdict(list)
for m in matriz:
    repos[m['repositorio']].append(m['area'])
for repo, areas in sorted(repos.items()):
    print(f"  {repo}: {sorted(set(areas))}")
