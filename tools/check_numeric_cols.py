"""Busca colunas cnpj/documento armazenadas como tipo NUMERICO nos SQLs."""
import glob, re, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

pat_cnpj = re.compile(r'cnpj|cpf_cnpj|cpfcnpj|tax_id|taxid', re.I)
pat_num  = re.compile(r'\b(bigint|int8|int4|integer|int|long|number|numeric)\b', re.I)
pat_var  = re.compile(r'\b(varchar|varchar2|char|nvarchar)\b', re.I)

hits = []
for fp in glob.glob('repos/**/*.sql', recursive=True):
    try:
        lines = open(fp, encoding='utf-8', errors='replace').read().splitlines()
    except:
        continue
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if not s or s.startswith('--'):
            continue
        if pat_cnpj.search(s) and pat_num.search(s) and not pat_var.search(s):
            repo = fp.split(os.sep)[1] if os.sep in fp else fp
            hits.append((repo, fp, i, s[:120]))

print(f"Colunas CNPJ/documento com tipo NUMERICO puro: {len(hits)}")
for repo, fp, i, s in hits:
    print(f"\n[{repo}] {fp}:{i}")
    print(f"  > {s}")
