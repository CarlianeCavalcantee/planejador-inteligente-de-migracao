"""
Gera o Google Doc da SPEC de Impacto CNPJ Alfanumérico.
Uso: python spec_gdocs/generate_gdoc.py [impacto_cnpj.json]
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleapiclient.discovery import build
import auth

AZUL = {"red": 0.106, "green": 0.227, "blue": 0.420}

# ── helpers de request ────────────────────────────────────────────────────────

def _insert(text, index):
    return {"insertText": {"location": {"index": index}, "text": text}}

def _style(start, end, **kwargs):
    return {"updateTextStyle": {
        "range": {"startIndex": start, "endIndex": end},
        "textStyle": kwargs,
        "fields": ",".join(kwargs.keys()),
    }}

def _para_style(start, end, named, align="START"):
    return {"updateParagraphStyle": {
        "range": {"startIndex": start, "endIndex": end},
        "paragraphStyle": {"namedStyleType": named, "alignment": align},
        "fields": "namedStyleType,alignment",
    }}

def _color(r, g, b):
    return {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}

# ── funções de escrita ────────────────────────────────────────────────────────

def heading(reqs, idx, text, level=1):
    t = text + "\n"
    reqs.append(_insert(t, idx))
    s, e = idx, idx + len(text)
    reqs.append(_para_style(s, e + 1, f"HEADING_{level}"))
    reqs.append(_style(s, e, bold=True, foregroundColor=_color(**AZUL),
                       fontSize={"magnitude": 14 - (level - 1) * 2, "unit": "PT"}))
    return idx + len(t)

def para(reqs, idx, text, bold=False, size=10, color=None):
    t = text + "\n"
    reqs.append(_insert(t, idx))
    s, e = idx, idx + len(t)
    st = {"fontSize": {"magnitude": size, "unit": "PT"}}
    if bold:  st["bold"] = True
    if color: st["foregroundColor"] = _color(*color)
    reqs.append(_style(s, e, **st))
    return e

# ── seções ────────────────────────────────────────────────────────────────────

def build_doc(reqs, data):
    meta  = data.get("sistema_escopo", "BScash")
    versao = data.get("spec_versao", "—")
    data_ex = data.get("data_execucao", "—")[:10]
    stats = data.get("estatisticas", {})
    idx = 1

    # Capa
    t = "SPEC – Análise de Impacto do CNPJ Alfanumérico\n"
    reqs.append(_insert(t, idx))
    reqs.append(_para_style(idx, idx + len(t), "TITLE", "CENTER"))
    reqs.append(_style(idx, idx + len(t) - 1, bold=True,
                       foregroundColor=_color(**AZUL),
                       fontSize={"magnitude": 22, "unit": "PT"}))
    idx += len(t)
    idx = para(reqs, idx, f"Sistema: {meta}  |  Versão: {versao}  |  Data: {data_ex}",
               size=11, color=(0.4, 0.4, 0.4))

    # 1. Sumário
    idx = heading(reqs, idx, "1. Sumário Executivo")
    s = stats
    for label, val in [
        ("Repositórios Analisados",       s.get("total_repositorios_analisados", 0)),
        ("Com Impacto",                   s.get("total_repositorios_com_impacto", 0)),
        ("Sem Impacto",                   s.get("total_repositorios_sem_impacto", 0)),
        ("Total de Impactos",             s.get("total_impactos_encontrados", 0)),
        ("Arquivos Críticos",             s.get("arquivos_criticos", 0)),
        ("Requerem Compatibilidade Dual", s.get("requerem_compatibilidade_dual", 0)),
        ("Chamadores Críticos Total",     f"{s.get('chamadores_criticos_total', 0):,}"),
    ]:
        idx = para(reqs, idx, f"  {label}: {val}")

    idx = heading(reqs, idx, "Impactos por Área", level=2)
    for area, qtd in sorted(s.get("impactos_por_area", {}).items(), key=lambda x: -x[1]):
        idx = para(reqs, idx, f"  {area}: {qtd}")

    idx = heading(reqs, idx, "Impactos por Complexidade", level=2)
    for comp, qtd in s.get("impactos_por_complexidade", {}).items():
        idx = para(reqs, idx, f"  {comp}: {qtd}")

    # 2. Por Repositório
    idx = heading(reqs, idx, "2. Impactos por Repositório")
    for repo, info in sorted(s.get("impactos_por_repositorio", {}).items(), key=lambda x: -x[1]["total"]):
        areas = ", ".join(info.get("areas", []))
        idx = para(reqs, idx,
                   f"  {repo}  —  Total: {info['total']}  Alta: {info.get('Alta',0)}  "
                   f"Média: {info.get('Média',0)}  Baixa: {info.get('Baixa',0)}  |  {areas}", size=9)

    # 3. Matriz
    idx = heading(reqs, idx, "3. Matriz de Impacto")
    idx = para(reqs, idx, f"Total de itens: {len(data.get('matriz_impacto', []))}", bold=True)
    for item in data.get("matriz_impacto", []):
        idx = para(reqs, idx,
                   f"[{item.get('id','')}] {item.get('area','')} — {item.get('repositorio','')} "
                   f"— {item.get('complexidade','')} / {item.get('prioridade','')}", bold=True, size=9)
        idx = para(reqs, idx, f"  Componente: {item.get('componente','')}", size=8)
        idx = para(reqs, idx, f"  Impacto: {item.get('descricao_impacto','')}", size=8)
        ev = item.get("evidencia", {})
        if ev.get("arquivo"):
            idx = para(reqs, idx, f"  Evidência: {ev['arquivo']} : L{ev.get('linha','')}", size=8)

    # 4. Riscos
    idx = heading(reqs, idx, "4. Lista de Riscos")
    for r in data.get("riscos_mapeados", []):
        idx = para(reqs, idx, f"Risco: {r.get('risco','')}", bold=True, size=9)
        idx = para(reqs, idx, f"  Impacto: {r.get('impacto','')}", size=9)
        idx = para(reqs, idx, f"  Mitigação: {r.get('mitigacao','')}", size=9)

    # 5. Parceiros
    idx = heading(reqs, idx, "5. Parceiros Externos")
    for p in data.get("parceiros_externos", []):
        idx = para(reqs, idx,
                   f"{p.get('parceiro','').upper()} — {p.get('descricao','')} "
                   f"| Repos: {', '.join(p.get('repositorios',[]))} | Status: {p.get('status_alinhamento','')}", size=9)

    # 6. Pendências
    idx = heading(reqs, idx, "6. Pendências Identificadas")
    for p in data.get("pendencias_identificadas", []):
        idx = para(reqs, idx, f"{p.get('id','')} — {p.get('descricao','')}", bold=True, size=9)
        idx = para(reqs, idx, f"  Responsável: {p.get('responsavel','')}  |  Prazo: {p.get('prazo_estimado','')}", size=9)

    # 7. Pontos Cegos
    idx = heading(reqs, idx, "7. Pontos Cegos")
    for pc in data.get("cobertura", {}).get("pontos_cegos", []):
        idx = para(reqs, idx, f"{pc.get('id','')} — {pc.get('descricao','')}", bold=True, size=9)
        idx = para(reqs, idx, f"  Recomendação: {pc.get('recomendacao','')}", size=9)

    # 8. Critérios de Aceite
    idx = heading(reqs, idx, "8. Critérios de Aceite")
    for c in [
        "Todos os pontos do sistema que manipulam CNPJ foram plenamente identificados.",
        "Todas as estruturas de banco de dados relacionadas ao CNPJ estão devidamente mapeadas.",
        "Todas as APIs expostas e consumidas foram completamente analisadas.",
        "Todas as validações locais e regras de negócio foram documentadas.",
        "Todas as telas e componentes de UI foram inventariados.",
        "Todas as integrações internas e externas foram avaliadas.",
        "Todos os riscos e dependências de terceiros foram registrados.",
        "A matriz de impacto está revisada pelo responsável técnico.",
        "O documento está aprovado formalmente pela equipe de engenharia.",
    ]:
        idx = para(reqs, idx, f"☐  {c}")

    # 9. Resultado Esperado
    idx = heading(reqs, idx, "9. Resultado Esperado")
    for q in [
        "Onde o CNPJ é persistido?",
        "Onde ele é validado?",
        "Onde ele é exibido?",
        "Onde ele é enviado ou recebido por integrações?",
        "Quais componentes precisarão ser alterados?",
        "Quais riscos e dependências existem para a futura implementação?",
        "Qual a estimativa de complexidade de cada impacto identificado?",
    ]:
        idx = para(reqs, idx, f"→  {q}")

    return reqs


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    _root   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _cwd    = os.getcwd()
    _arg    = sys.argv[1] if len(sys.argv) > 1 else None
    json_in = (os.path.join(_cwd, _arg) if _arg and not os.path.isabs(_arg) else _arg) \
              or os.path.join(_root, "impacto_cnpj.json")

    with open(json_in, encoding="utf-8") as f:
        data = json.load(f)

    meta   = data.get("sistema_escopo", "BScash")
    versao = data.get("spec_versao", "—")

    MEU_EMAIL = "carlianecavalcantebscash@gmail.com"

    creds = auth.get_credentials()
    docs  = build("docs",  "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    # cria o doc no Drive da service account
    doc    = docs.documents().create(body={"title": f"SPEC – Impacto CNPJ – {meta} v{versao}"}).execute()
    doc_id = doc["documentId"]
    print(f"Documento criado: https://docs.google.com/document/d/{doc_id}/edit")

    # compartilha com seu e-mail pessoal como editor
    drive.permissions().create(
        fileId=doc_id,
        body={"type": "user", "role": "writer", "emailAddress": MEU_EMAIL},
        sendNotificationEmail=False,
    ).execute()

    # compartilha com qualquer pessoa com o link
    drive.permissions().create(
        fileId=doc_id,
        body={"type": "anyone", "role": "writer"},
    ).execute()

    reqs = build_doc([], data)
    print(f"Enviando {len(reqs)} requests...")
    for i in range(0, len(reqs), 800):
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": reqs[i:i+800]},
        ).execute()
        print(f"  lote {i//800 + 1} ok")

    print(f"\nPronto! https://docs.google.com/document/d/{doc_id}/edit")


if __name__ == "__main__":
    main()
