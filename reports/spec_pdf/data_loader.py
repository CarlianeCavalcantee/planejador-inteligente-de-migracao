import json

def load(json_path: str) -> dict:
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)

def get_meta(data: dict) -> dict:
    return {
        "sistema": data.get("sistema_escopo", "—"),
        "versao": data.get("spec_versao", "—"),
        "data_execucao": data.get("data_execucao", "—")[:10],
    }

def get_stats(data: dict) -> dict:
    s = data.get("estatisticas", {})
    return {
        "total_repos": s.get("total_repositorios_analisados", 0),
        "repos_com_impacto": s.get("total_repositorios_com_impacto", 0),
        "repos_sem_impacto": s.get("total_repositorios_sem_impacto", 0),
        "total_impactos": s.get("total_impactos_encontrados", 0),
        "por_area": s.get("impactos_por_area", {}),
        "por_complexidade": s.get("impactos_por_complexidade", {}),
        "por_repositorio": s.get("impactos_por_repositorio", {}),
        "arquivos_criticos": s.get("arquivos_criticos", 0),
        "requerem_dual": s.get("requerem_compatibilidade_dual", 0),
        "chamadores_criticos": s.get("chamadores_criticos_total", 0),
        "progresso": s.get("progresso", {}),
    }

def get_matriz(data: dict) -> list:
    return data.get("matriz_impacto", [])

def get_riscos(data: dict) -> list:
    return data.get("riscos_mapeados", [])

def get_parceiros(data: dict) -> list:
    return data.get("parceiros_externos", [])

def get_pendencias(data: dict) -> list:
    return data.get("pendencias_identificadas", [])

def get_pontos_cegos(data: dict) -> list:
    return data.get("cobertura", {}).get("pontos_cegos", [])
