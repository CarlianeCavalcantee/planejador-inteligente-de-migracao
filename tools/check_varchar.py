import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Padrão: coluna cnpj ou documento com tipo e tamanho
_COL = re.compile(
    r'(?i)(cnpj|documento|doc_number|nr_doc|num_doc|tax_id|taxid|federal_id|cpf_cnpj|cpfcnpj|company_id|corporate_id)'
    r'.{0,30}(VARCHAR2?|CHAR|NVARCHAR2?|NUMBER|BIGINT|INT|NUMERIC)\s*\(\s*(\d+)'
)
# Também pega ALTER TABLE ... MODIFY/ALTER COLUMN
_ALTER = re.compile(
    r'(?i)ALTER\s+TABLE.{0,60}(cnpj|documento).{0,60}(VARCHAR2?|CHAR|NUMBER)\s*\(\s*(\d+)'
)

SQL_EXTS = {'.sql', '.xml', '.properties', '.yml', '.yaml'}

results = []

for repo in sorted(os.listdir('repos')):
    root = os.path.join('repos', repo)
    if not os.path.isdir(root):
        continue
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in SQL_EXTS:
                continue
            fp = os.path.join(dirpath, f)
            try:
                content = open(fp, encoding='utf-8', errors='replace').read()
            except:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                for pat in [_COL, _ALTER]:
                    m = pat.search(line)
                    if m:
                        col_name = m.group(1)
                        col_type = m.group(2)
                        col_size = int(m.group(3))
                        rel = fp.replace(root + os.sep, '').replace('\\', '/')
                        results.append((repo, rel, i, col_name, col_type, col_size, line.strip()[:120]))

# Agrupa: problemáticos (< 20) vs ok (>= 20)
problematicos = [(r, f, l, c, t, s, ln) for r, f, l, c, t, s, ln in results if s < 20]
ok = [(r, f, l, c, t, s, ln) for r, f, l, c, t, s, ln in results if s >= 20]

print(f'{"="*70}')
print(f'COLUNAS COM TAMANHO INSUFICIENTE (< 20) — PRECISAM DE MIGRATION')
print(f'{"="*70}')
for repo, f, l, col, typ, size, line in sorted(problematicos, key=lambda x: x[0]):
    print(f'\n  [{repo}] {f}:{l}')
    print(f'  coluna={col}  tipo={typ}({size})  << PRECISA SER >= 20')
    print(f'  > {line}')

print(f'\n{"="*70}')
print(f'COLUNAS JÁ OK (>= 20)')
print(f'{"="*70}')
for repo, f, l, col, typ, size, line in sorted(ok, key=lambda x: x[0]):
    print(f'  [{repo}] {f}:{l}  {col} {typ}({size})')

print(f'\nTotal problemáticos: {len(problematicos)}')
print(f'Total ok: {len(ok)}')
