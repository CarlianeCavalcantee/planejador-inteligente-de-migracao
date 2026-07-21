import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.github_client import _SEARCH_TERMS, _content_has_anchor

root = 'repos/cliente-tef'
_st_lower = [t.lower() for t in _SEARCH_TERMS]

for dirpath, _, files in os.walk(root):
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
            rel = fp.replace(root + os.sep, '').replace(root + '/', '')
            print(f'{rel}')
            print(f'  search_terms={hits}  anchor={anchor}')
            # mostra as linhas que contêm os termos
            for i, line in enumerate(content.splitlines(), 1):
                ll = line.lower()
                if any(t in ll for t in _st_lower) or (anchor and any(p.search(line) for p in __import__('core.github_client', fromlist=['_ANCHOR_RES'])._ANCHOR_RES)):
                    print(f'  L{i}: {line.strip()[:150]}')
