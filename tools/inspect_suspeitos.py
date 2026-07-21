import os, sys, json, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.github_client import _content_has_anchor, _SEARCH_TERMS
from core.engine import is_false_positive

REPOS = ['BSnegociacao-web', 'bscorporate-bff', 'contabilidade-rotinas', 'bscash-service-client']
_st_lower = [t.lower() for t in _SEARCH_TERMS]

# Impactos do JSON principal
d = json.load(open('docs/output/impacto_cnpj.json', encoding='utf-8'))
matriz = d['matriz_impacto']

for repo in REPOS:
    print(f'\n{"="*60}')
    print(f'REPO: {repo}')

    # Impactos registrados no JSON
    impactos = [i for i in matriz if i.get('repositorio') == repo]
    print(f'  Impactos no JSON: {len(impactos)}')
    for imp in impactos[:5]:
        print(f'    [{imp.get("area")}] {imp.get("filepath")} L{imp.get("match",{}).get("linha","?")}')
        print(f'      > {imp.get("match",{}).get("trecho_codigo","")[:120]}')

    # Candidatos no disco
    root = f'repos/{repo}'
    if not os.path.isdir(root):
        print('  [sem repo local]')
        continue

    candidatos = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d2 for d2 in dirnames if not d2.startswith('.')]
        for f in files:
            fp = os.path.join(dirpath, f)
            try:
                content = open(fp, encoding='utf-8', errors='replace').read()
            except:
                continue
            cl = content.lower()
            hits = [t for t in _st_lower if t in cl]
            anchor = _content_has_anchor(content)
            if hits or anchor:
                rel = fp.replace(root + os.sep, '').replace('\\', '/')
                # mostra linhas que ativaram
                linhas = []
                for i, line in enumerate(content.splitlines(), 1):
                    ll = line.lower()
                    if any(t in ll for t in _st_lower):
                        linhas.append((i, line.strip()[:120], is_false_positive(line)))
                if hits:
                    candidatos.append((rel, hits, linhas))

    print(f'  Candidatos com search_terms no disco: {len(candidatos)}')
    for rel, hits, linhas in candidatos[:10]:
        print(f'    {rel}  terms={hits}')
        for n, l, fp in linhas[:3]:
            print(f'      L{n} [FP={fp}]: {l}')
