"""
Mapeia componentes do backoffice para telas de negócio e atualiza telas_qa no JSON.
"""
import json
import re
from collections import defaultdict

# ---------------------------------------------------------------------------
# Mapeamento: padrão no caminho/nome do arquivo → tela de negócio
# Ordem importa: primeiro match vence.
# ---------------------------------------------------------------------------
MAPA = [
    # Adesão / Conta Digital
    (r"AdesaoPessoa|AdesaoVo|AdesaoUtil|AdesaoSocio|AdesaoDiretor|AdesaoProcurador|DetalheUploadAdesao|AtualizacaoCadastral|WhiteLabel|CadastroUnico|PreCadastroPessoa|DetalheUploadCadastro",
     "Adesão / Cadastro PJ"),

    # Background Check / Antifraude
    (r"backgroundcheck|AntifraudePj|BackgroundCheck|ConsultaBackgroundCheck|HistoricoBackgroundCheck|PersonService|RelatorioAntifraude|InfosGovernment|MpfExtrajudicial|TjSpCertificate|Trf5Certificates|WorkSlave|MembershipBoard|Rais|CompanyNgc|CompanyVo",
     "Background Check / Antifraude"),

    # PIX
    (r"pix|Pix|ComprovanteRecebimentoPix|ComprovanteTransacao",
     "PIX (chave, transferência, favorito)"),

    # Boleto / Cobrança
    (r"boleto|Boleto|cobranca|Cobranca|NossoNumero|ClienteCobranca|NegociacaoNgc|ReciboCobranca|RetornoCobranca|ClienteCobranca\.jrxml",
     "Boleto / Cobrança"),

    # Remessa / CNAB / Retorno Bancário
    (r"remessa|Remessa|retorno|Retorno|cnab|CNAB|LayoutFebraban|RemessaPagamento|ArquivoRemessa|RegistroRemessa|RegistroRetorno|RelatorioRemessa|RetornoPagamento|BBDetalhe|SantanderDetail|DetalheVo",
     "Remessa Bancária / CNAB"),

    # Integração Bancária
    (r"IntegracaoBancaria|DadosBancarios|BoletoNgc|TituloNgc|PersistenciaBD|RegistroTituloPagar|RelatorioTitulosPagar|RemessaBancoDAO|RetornoBancoDAO|ArquivoRetorno",
     "Boleto / Cobrança"),

    # NFS-e / Nota Fiscal
    (r"nfse|Nfse|NotaFiscal|ReciboProvisorioServico|EmissorNfse|IndicacaoCpfCnpj|TcCpfCnpj|TcIdentificacao|TcLoteRps|ServicoNFSe|NotaFiscal\.jrxml",
     "Emissão NFS-e"),

    # Cartão
    (r"cartao|Cartao|Estabelecimento|Lojista|RecordPaySmart|RedeCompras|Conciliacao|ArquivoParamRedeCompras|ErrosRedeCompras",
     "Cartão"),

    # Holerite / Remuneração
    (r"holerite|Holerite|Remuneracao|ArquivoRemuneracao|ComprovanteRemuneracao|LoteHolerite",
     "Holerite / Remuneração"),

    # Lotação / Importação de Arquivo
    (r"Lotacao|LotacaoBean|LotacaoDAO",
     "Lotação / Importação de Arquivo"),

    # Limite / Crédito
    (r"LimiteDecimo|LimiteRotativo|credito|Credito",
     "Crédito / CCB / Negociação"),

    # DARF / Pagamento Fiscal
    (r"Darf|DARF|TransacaoDarf",
     "Pagamento DARF"),

    # Recarga
    (r"recarga|Recarga|ComprovanteRecarga",
     "Recarga de Crédito"),

    # Seguro / Patrimônio
    (r"Seguro|patrimonio|Patrimonio|ResponsavelAtivo",
     "Seguro / Patrimônio"),

    # Locação
    (r"locacao|Locacao|OrcamentoLocacao|OrcamentoAtivo|OrcamentoVeiculo",
     "Locação / Orçamento"),

    # Eventos / Ficha de Inscrição
    (r"evento|Evento|FichaInscricao|PreInscricao|CaixaEvento|EntradaParticipante|OrcamentoEvento|VendedorOrcamento|RegistroParticipante|RegistroExpositores|RegistroInscricoes|ImpressoraDaruma|InscricoesPorEmpresa|RelacaoParticipantes|RelacaoEmpresaParticipantes|RelatorioExpositores|RelatorioOrcamento|FichaInscricao\.jrxml",
     "Ficha de Inscrição / Eventos"),

    # Contabilidade / Balancete
    (r"contabilidade|Contabilidade|Balancete|BalancoPatrimonial|TermoAbertura|IntegracaoContabilFiscal|LancamentoNgc|RegistroRazaoAuxiliar|RegistroParticipantesDocumentos|BodyExample",
     "Contabilidade / Balancete"),

    # Notificação
    (r"Notificacao|FiltrosEnvioNotificacao",
     "Notificações"),

    # Acesso / Usuário / Empresa
    (r"acesso|Acesso|UsuarioConta|EmpresaAdministradora|GrupoEmpresaUsuario|EmpresaVo|CRMEmpresa",
     "Gestão de Acesso / Empresa"),

    # Colaborador / RH
    (r"Colaborador|ColaboradorDAO|ColaboradorNgc",
     "Cadastro de Colaborador"),

    # Contato / Contrato
    (r"ContatoBean|ContratoValidacao",
     "Cadastro de Contato / Contrato"),

    # Validação / Utilitários compartilhados
    (r"ValidacaoUtil|TipoDado|TipoPessoa|Formato|JsonUtil|CampoLayout|ParametroSistema|TipoDadoNgc|PessoaNgc|PreCadastroPessoaNgc|ConsultaSituacaoCliente|SubstituicaoTexto|ReceitaWs|hibernate\.cfg",
     "Validação de CNPJ (shared)"),

    # Pessoa Jurídica (core)
    (r"PessoaJuridica|PessoaDAO|PessoaVo|PessoaFisica|GrupoEconomico|EmpresaGrupoEconomico|ColaboradorDAO",
     "Cadastro PJ / Pessoa Jurídica"),

    # Relatórios / Impressão
    (r"relatorio|Relatorio|jrxml|CotacaoCompra|ReciboAquisicao|ReciboRepasse",
     "Relatórios / Impressão"),

    # Transações / Extrato
    (r"Transacao|TransacaoDAO|TransacaoCodigoBarras|CredorVo",
     "Extrato / Transações"),

    # Conta Digital (genérico)
    (r"ContaBean|ContaDAO|AdesaoPessoaBean|SocioVo|DiretorVo|AdesaoSocioVo|AdesaoDiretorVo|ArquivoDiretor|ArquivoSocio|TipoDocumento|DiretorDAO|SocioDAO|ArquivoPessoaService",
     "Conta Digital"),

    # Forma de Pagamento
    (r"FormaPagamento",
     "Boleto / Cobrança"),

    # Transmissão de Arquivo
    (r"TransmissaoArquivo",
     "Remessa Bancária / CNAB"),

    # Rede de Compras / Software Express
    (r"redecompras|Redecompras|softwareexpress|SoftwareExpress|DetalheE01|DetalheEST",
     "Cartão"),
]

# ---------------------------------------------------------------------------

def inferir_tela(componente: str) -> str:
    for padrao, tela in MAPA:
        if re.search(padrao, componente):
            return tela
    return "Outros / Não classificado"


def main():
    with open("impacto_cnpj.json", encoding="utf-8") as f:
        data = json.load(f)

    impactos_bo = [i for i in data.get("matriz_impacto", [])
                   if i.get("repositorio") == "backoffice"]

    # Agrupa impactos por tela inferida
    por_tela: dict[str, list] = defaultdict(list)
    for imp in impactos_bo:
        tela = inferir_tela(imp.get("componente", ""))
        por_tela[tela].append(imp)

    # Monta estrutura telas_qa para o backoffice
    telas_novas = []
    for tela, imps in sorted(por_tela.items()):
        total = len(imps)
        p1 = sum(1 for i in imps if i.get("prioridade") == "P1")
        prioridade = "P1" if p1 > 0 else "P2"
        areas = sorted(set(i.get("area", "") for i in imps))
        dual = any(i.get("requer_compatibilidade_dual") for i in imps)

        testes = ["Funcional: fluxo completo com CNPJ alfanumérico",
                  "Regressão: CNPJ numérico antigo continua funcionando"]
        if dual:
            testes.append("Integração: compatibilidade dual durante período de transição")
        if any("Relatório" in a or "Batch" in a for a in areas):
            testes.append("Funcional: geração de documento/relatório com CNPJ alfanumérico")

        telas_novas.append({
            "tela": tela,
            "prioridade": prioridade,
            "repositorios": ["backoffice"],
            "areas_impactadas": areas,
            "total_impactos": total,
            "requer_compatibilidade_dual": dual,
            "testes_sugeridos": testes,
        })

    # Ordena: P1 primeiro, depois por total_impactos desc
    telas_novas.sort(key=lambda x: (x["prioridade"], -x["total_impactos"]))

    # Remove entradas antigas exclusivas do backoffice e adiciona as novas
    telas_existentes = [t for t in data.get("telas_qa", [])
                        if t.get("repositorios") != ["backoffice"]]
    data["telas_qa"] = telas_existentes + telas_novas

    with open("impacto_cnpj.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Imprime resumo
    print(f"{'Tela':<45} {'Pri':>3}  {'Impactos':>8}  {'Dual':>4}")
    print("-" * 70)
    for t in telas_novas:
        dual_flag = "S" if t["requer_compatibilidade_dual"] else ""
        print(f"{t['tela']:<45} {t['prioridade']:>3}  {t['total_impactos']:>8}  {dual_flag:>4}")
    print("-" * 70)
    print(f"{'TOTAL':<45} {'':>3}  {sum(t['total_impactos'] for t in telas_novas):>8}")
    print(f"\n{len(telas_novas)} telas mapeadas para o backoffice.")


if __name__ == "__main__":
    main()
