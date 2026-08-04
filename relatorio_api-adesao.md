# Relatorio de Migracao CNPJ Alfanumerico

| Metrica | Valor |
|---------|-------|
| Projetos analisados | 3 |
| Arquivos | 514 |
| Ocorrencias | 3 |
| Auto corrigidos | 2 |
| Pendentes | 1 |
| Taxa de automacao | 66.7% |

## Ocorrencias por regra

| Regra | P | Auto | Revisao | Descricao |
|-------|---|------|---------|-----------|
| `RM-001` | 100 | +2 | - | replaceAll('[^0-9]','') -> CnpjUtils.removeMask() |
| `JPA-001` | 75 | - | !1 | @Column(length=1x) em campo CNPJ/CPF/documento -> revisar length=20 |

## `repos\api-adesao\src\main\java\br\com\hmti\pj\entities\backoffice\manager\Socio.java`

### Requer revisao humana

| Linha | Regra | Trecho |
|-------|-------|--------|
| 31 | `JPA-001` | `@Column(name = "CpfCnpj", nullable = false, length = 18)` |

## `repos\api-adesao\src\main\java\br\com\hmti\pj\helpers\StringHelper.java`

### Aplicado automaticamente

| Linha | Regra | Original | Substituido |
|-------|-------|----------|-------------|
| 33 | `RM-001` | `return value.replaceAll("[^0-9]", "");` | `return CnpjUtils.removeMask(value);` |

## `repos\api-adesao\src\main\java\br\com\hmti\pj\validadaodados\service\PessoaDadosSerproServiceImpl.java`

### Aplicado automaticamente

| Linha | Regra | Original | Substituido |
|-------|-------|----------|-------------|
| 150 | `RM-001` | `return value.replaceAll("[^0-9]", "");` | `return CnpjUtils.removeMask(value);` |
