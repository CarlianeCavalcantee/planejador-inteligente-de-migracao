import json

old = json.load(open('docs/output/impacto_cnpj.json', encoding='utf-8'))
new = json.load(open('docs/scans/scan_bscash-service-client.json', encoding='utf-8'))

old_imp = [i for i in old['matriz_impacto'] if i.get('repositorio') == 'bscash-service-client']
new_imp = new.get('matriz_impacto', [])

print(f'ANTIGO: {len(old_imp)} impactos')
nulls = sum(1 for i in old_imp if not i.get('filepath'))
print(f'  filepath=null: {nulls}')

print(f'\nNOVO: {len(new_imp)} impactos')
nulls_new = sum(1 for i in new_imp if not i.get('filepath'))
print(f'  filepath=null: {nulls_new}')

print('\nAMOSTRA NOVO (primeiros 10):')
for imp in new_imp[:10]:
    print(f'  [{imp.get("area")}] {imp.get("filepath")} L{imp.get("match", {}).get("linha", "?")}')
    print(f'    > {imp.get("match", {}).get("trecho_codigo", "")[:100]}')
