import json

cfg = json.load(open('scanner-config.json', encoding='utf-8'))
exts = set()
nomes = set()
for r in cfg['regras']:
    exts.update(r['extensoes'])
    nomes.update(r.get('nomes_arquivo', []))

print('EXTENSOES COBERTAS:')
for e in sorted(exts):
    print(' ', e)
print()
print('NOMES COBERTOS:')
for n in sorted(nomes):
    print(' ', n)
