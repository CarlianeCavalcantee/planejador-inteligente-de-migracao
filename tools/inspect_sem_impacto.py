import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.github_client import _SEARCH_TERMS, _content_has_anchor
from core.engine import is_false_positive

REPOS_SEM_IMPACTO = [
    '2.0-infra', 'BSnegociacao-web', 'RestoreBancos', 'api-error-lib',
    'api-monitoramento', 'auditoria-outbox', 'autorizacao-alcada-lib',
    'azure-sprint-kanban', 'backoffice-web', 'bscash-box',
    'bscash-receita-efinanceira-tools', 'bscash-teste', 'bscash-uikit',
    'bscorporate-bff', 'bssimples-api', 'caf-webhook', 'cartao-lib',
    'centro-de-observabilidade', 'cliente-tef', 'contabilidade-rotinas',
    'example-java-project', 'file-generator', 'handshake-bmp', 'hmit-util',
    'jenkins-scripts', 'jrimum-texgit', 'ms-auditoria', 'ms-cartao-bandeira',
    'ms-notificacao', 'ms-ura', 'notificacao-lib', 'password-generator',
    'plano-eliminacao-funcao-banco-de-dados', 'poc-area-pix', 'poc-mfa',
    'poc-processaremunercao', 'poc-remuneracao-api', 'poc-remuneracao-web',
    'processa-remuneracao', 'sancao-lib', 'screening', 'screening-lib',
    'senha-acesso-lib', 'senha-transacao-lib', 'sms-lib',
    'sped-efinanceira-client', 'storage-lib', 'swap-webhook', 'teste-caf',
    'teste-xdocreport', 'texgit', 'textgit-bradesco', 'ui', 'whatsapp-lib'
]

_st_lower = [t.lower() for t in _SEARCH_TERMS]
# Padrão direto de CNPJ numérico no código (não âncora numérica genérica)
_CNPJ_DIRETO = re.compile(r'(?i)\bcnpj\b')

results = []

for repo in REPOS_SEM_IMPACTO:
    root = f'repos/{repo}'
    if not os.path.isdir(root):
        results.append((repo, 'SEM_REPO_LOCAL', [], []))
        continue

    candidatos_com_cnpj = []   # arquivos com 'cnpj' literal
    candidatos_so_alias = []   # arquivos só com alias (sem 'cnpj')
    linhas_nao_fp = []         # linhas que NÃO são falso positivo

    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for f in files:
            fp = os.path.join(dirpath, f)
            try:
                content = open(fp, encoding='utf-8', errors='replace').read()
            except:
                continue
            cl = content.lower()
            has_cnpj = 'cnpj' in cl
            has_alias = any(t in cl for t in _st_lower if t != 'cnpj')

            if not has_cnpj and not has_alias:
                continue

            rel = fp.replace(root + os.sep, '').replace('\\', '/')
            # Ignora arquivos .git
            if rel.startswith('.git'):
                continue

            linhas_relevantes = []
            for i, line in enumerate(content.splitlines(), 1):
                ll = line.lower()
                if 'cnpj' in ll or any(t in ll for t in _st_lower if t != 'cnpj'):
                    if not is_false_positive(line):
                        linhas_relevantes.append((i, line.strip()[:120]))

            if has_cnpj:
                candidatos_com_cnpj.append((rel, linhas_relevantes))
            elif has_alias:
                candidatos_so_alias.append((rel, linhas_relevantes))

    results.append((repo, 'OK', candidatos_com_cnpj, candidatos_so_alias))

# Saída
print('=' * 70)
print('REPOS SEM IMPACTO — ANÁLISE DE FALSOS NEGATIVOS')
print('=' * 70)

suspeitos = []
limpos = []

for repo, status, com_cnpj, so_alias in results:
    if status == 'SEM_REPO_LOCAL':
        limpos.append(f'  {repo}: [sem repo local]')
        continue

    # Filtra só arquivos que têm linhas não-FP
    com_cnpj_real = [(f, ls) for f, ls in com_cnpj if ls]
    so_alias_real = [(f, ls) for f, ls in so_alias if ls]

    if com_cnpj_real or so_alias_real:
        suspeitos.append((repo, com_cnpj_real, so_alias_real))
    else:
        limpos.append(f'  {repo}: limpo (sem linhas relevantes fora de FP)')

print(f'\n{"="*70}')
print(f'SUSPEITOS ({len(suspeitos)}) — têm linhas não-FP mas zero impactos:')
print(f'{"="*70}')
for repo, com_cnpj, so_alias in suspeitos:
    print(f'\n>> {repo}')
    if com_cnpj:
        print(f'   Arquivos com "cnpj" ({len(com_cnpj)}):')
        for f, ls in com_cnpj[:5]:
            print(f'     {f}')
            for n, l in ls[:3]:
                print(f'       L{n}: {l}')
    if so_alias:
        print(f'   Arquivos só com alias ({len(so_alias)}):')
        for f, ls in so_alias[:3]:
            print(f'     {f}')
            for n, l in ls[:2]:
                print(f'       L{n}: {l}')

print(f'\n{"="*70}')
print(f'LIMPOS ({len(limpos)}) — confirmados sem impacto:')
print(f'{"="*70}')
for l in limpos:
    print(l)
