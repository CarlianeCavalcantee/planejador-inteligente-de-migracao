import json
from collections import Counter
import os

d = json.load(open('impacto_cnpj.json', encoding='utf-8'))

exts = Counter()
for m in d['matriz_impacto']:
    f = m['evidencia']['arquivo']
    # pega extensao
    parts = f.split('.')
    if len(parts) > 1:
        ext = '.' + parts[-1]
        exts[ext] += 1

print("Extensoes nos impactos atuais:")
for ext, count in exts.most_common():
    print(f"  {count:3d}  {ext}")
