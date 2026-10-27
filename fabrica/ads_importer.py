import csv
import io
import os
import re
from datetime import datetime
from decimal import Decimal
import openpyxl
from django.db.models import Q
from django.utils import timezone
from .models import (
    CampanhaAds,
    Produto,
    ProdutoMarketplace,
    VendaMarketplace,
)


def to_float(val):
    if not val or val == "-":
        return 0.0
    try:
        val_str = str(val).replace("%", "").replace("R$", "").replace(",", ".").strip()
        return float(val_str)
    except Exception:
        return 0.0


def to_int(val):
    if not val or val == "-":
        return 0
    try:
        return int(float(str(val).replace(".", "").replace(",", ".").strip()))
    except Exception:
        return 0


def importar_planilha_ads_shopee(caminho_csv, canal="shopee"):
    """Lê o Relatório Geral de Anúncios da Shopee (Keyword/Placement Level Data).
    Atualiza as Campanhas de Ads, calcula o CAC real por produto,
    distribui o custo nas vendas e quantifica o prejuízo de CAC em pedidos cancelados.
    """
    rows = []
    # Tenta ler com diferentes encodings
    for enc in ["utf-8-sig", "latin1", "cp1252"]:
        try:
            with open(caminho_csv, "r", encoding=enc, errors="ignore") as f:
                rows = list(csv.reader(f))
            if rows and len(rows) > 5:
                break
        except Exception:
            continue

    if not rows:
        raise ValueError("Não foi possível ler as linhas do arquivo de Ads.")

    header_idx = -1
    for i, r in enumerate(rows):
        if len(r) > 1 and r[0] == "#" and ("Nome" in r[1] or "Anúncio" in r[1] or "Anncio" in r[1]):
            header_idx = i
            break

    if header_idx == -1:
        # Fallback para linha que tenha 'Nome' ou 'Despesas'
        for i, r in enumerate(rows[:20]):
            for cell in r:
                if "Despesa" in cell or "Impress" in cell:
                    header_idx = i
                    break
            if header_idx != -1:
                break

    if header_idx == -1:
        raise ValueError("Cabeçalho da tabela de anúncios não foi localizado no arquivo.")

    dados = rows[header_idx + 1 :]

    campanhas_processadas = 0
    despesas_total = 0.0
    gmv_total = 0.0
    conversoes_total = 0
    vendas_atualizadas_total = 0
    pedidos_perdidos_cac_count = 0
    prejuizo_cac_cancelados_total = 0.0

    for r in dados:
        if len(r) < 20 or not r[1].strip():
            continue

        nome_anuncio = r[1].strip()
        status_anuncio = r[2].strip() if len(r) > 2 else ""
        id_produto = r[3].strip() if len(r) > 3 and r[3] != "-" else ""
        
        impressoes = to_int(r[10]) if len(r) > 10 else 0
        cliques = to_int(r[11]) if len(r) > 11 else 0
        conversoes = to_int(r[15]) if len(r) > 15 else 0
        cac = to_float(r[19]) if len(r) > 19 else 0.0
        itens_vendidos = to_int(r[21]) if len(r) > 21 else 0
        gmv = to_float(r[23]) if len(r) > 23 else 0.0
        despesa = to_float(r[25]) if len(r) > 25 else 0.0
        roas = to_float(r[26]) if len(r) > 26 else 0.0

        if despesa == 0.0 and conversoes == 0 and cliques == 0:
            continue

        # 1. Garante ou vincula o ProdutoMarketplace correspondente
        prod_mkt = None
        if nome_anuncio and nome_anuncio != "GMV Max da Loja" and not nome_anuncio.startswith("Grupo de Anúncios"):
            # Limpa o sufixo [2], [3], etc
            nome_clean = re.sub(r"\s*\[\d+\]\s*$", "", nome_anuncio).strip()
            
            prod_mkt = ProdutoMarketplace.objects.filter(
                Q(nome_marketplace__iexact=nome_clean) | Q(nome_marketplace__iexact=nome_anuncio)
            ).first()

            if not prod_mkt:
                # Cria com custo de transferência padrão se ainda não existir
                prod_mkt = ProdutoMarketplace.objects.create(
                    sku_marketplace=id_produto or f"SHP-{abs(hash(nome_clean)) % 100000}",
                    nome_marketplace=nome_clean,
                    canal="shopee",
                    id_produto_canal=id_produto,
                    custo_transferencia_padrao=0.00,
                )

        # 2. Registra ou atualiza a CampanhaAds
        campanha, _ = CampanhaAds.objects.update_or_create(
            canal="shopee",
            nome_campanha=nome_anuncio,
            defaults={
                "id_produto_anuncio": id_produto,
                "produto_marketplace": prod_mkt,
                "impressoes": impressoes,
                "cliques": cliques,
                "conversoes": conversoes,
                "itens_vendidos": itens_vendidos,
                "valor_investido": Decimal(str(round(despesa, 2))),
                "receita_atribuida": Decimal(str(round(gmv, 2))),
                "roas_informado": Decimal(str(round(roas, 2))),
            },
        )

        campanhas_processadas += 1
        despesas_total += despesa
        gmv_total += gmv
        conversoes_total += conversoes

        # 3. Rateia o Ads nas vendas de pedidos correspondentes a esse anúncio
        # Busca vendas que contenham o título do anúncio ou palavras-chave
        palavras = [w for w in re.findall(r"\w+", nome_anuncio.lower()) if len(w) > 4 and w not in ["feminina", "confortavel", "confortvel"]]
        
        vendas_query = VendaMarketplace.objects.filter(canal="shopee")
        if id_produto:
            vendas_candidatas = vendas_query.filter(
                Q(nome_produto_marketplace__icontains=palavras[0] if palavras else "")
                | Q(sku_marketplace__icontains=id_produto)
            )
        elif palavras:
            q_filtro = Q()
            for p in palavras[:2]:
                q_filtro &= Q(nome_produto_marketplace__icontains=p)
            vendas_candidatas = vendas_query.filter(q_filtro)
        else:
            vendas_candidatas = vendas_query.none()

        # Atribui o CAC nas vendas candidatas
        for v in vendas_candidatas:
            v.campanha_ads = campanha
            if prod_mkt and not v.produto_marketplace:
                v.produto_marketplace = prod_mkt

            if cac > 0:
                v.custo_ads_atribuido = Decimal(str(round(cac, 2)))
            
            # Se for cancelado, quantifica o custo perdido
            if v.status == "cancelado" and cac > 0:
                v.custo_ads_pedido_perdido = Decimal(str(round(cac, 2)))
                pedidos_perdidos_cac_count += 1
                prejuizo_cac_cancelados_total += cac

            v.save()
            vendas_atualizadas_total += 1

    return {
        "campanhas_processadas": campanhas_processadas,
        "despesas_total": round(despesas_total, 2),
        "gmv_total": round(gmv_total, 2),
        "conversoes_total": conversoes_total,
        "roas_medio": round((gmv_total / despesas_total), 2) if despesas_total > 0 else 0.0,
        "cac_medio": round((despesas_total / conversoes_total), 2) if conversoes_total > 0 else 0.0,
        "vendas_atualizadas": vendas_atualizadas_total,
        "pedidos_perdidos_cac_count": pedidos_perdidos_cac_count,
        "prejuizo_cac_cancelados_total": round(prejuizo_cac_cancelados_total, 2),
    }


def importar_planilha_ads_tiktok(caminho_csv, canal="tiktok"):
    """Lê o Relatório de Desempenho Diário do TikTok Ads Manager.
    Extrai Custo, Pedidos de SKU, Custo por Pedido (CAC), Receita Bruta (GMV) e ROI.
    Registra a CampanhaAds e atribui o CAC diário nas vendas correspondentes do TikTok.
    Quantifica o prejuízo de CAC em pedidos cancelados do TikTok.
    """
    ext = os.path.splitext(caminho_csv)[1].lower()
    rows = []
    if ext in [".xlsx", ".xlsm", ".xls"]:
        try:
            wb = openpyxl.load_workbook(caminho_csv, data_only=True)
            ws = wb.active
            for r in range(1, ws.max_row + 1):
                row_vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
                row_strs = [str(x).strip() if x is not None else "" for x in row_vals]
                if any(row_strs):
                    rows.append(row_strs)
            wb.close()
        except Exception as e:
            raise ValueError(f"Não foi possível ler o arquivo Excel de TikTok Ads: {e}")
    else:
        for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
            try:
                with open(caminho_csv, "r", encoding=enc, errors="ignore") as f:
                    rows = list(csv.reader(f))
                if rows and len(rows) > 1:
                    break
            except Exception:
                continue

    if not rows:
        raise ValueError("Não foi possível ler as linhas do arquivo de TikTok Ads.")

    header_idx = -1
    for i, r in enumerate(rows):
        if r and ("Por dia" in r[0] or "Custo por pedido" in " ".join(r) or "ROI (loja atual)" in " ".join(r)):
            header_idx = i
            break

    if header_idx == -1:
        raise ValueError("Cabeçalho do relatório do TikTok Ads não foi localizado no arquivo.")

    dados = rows[header_idx + 1 :]

    days_data = {}
    total_data = None
    min_data = None
    max_data = None

    for r in dados:
        if not r or len(r) < 6:
            continue
        dia_str = str(r[0]).strip()
        custo = to_float(r[1])
        pedidos = to_int(r[2])
        cac = to_float(r[3])
        gmv = to_float(r[4])
        roi = to_float(r[5])

        if dia_str == "-":
            total_data = {
                "custo": custo,
                "pedidos": pedidos,
                "cac": cac,
                "gmv": gmv,
                "roi": roi,
            }
        else:
            try:
                dt = datetime.strptime(dia_str[:10], "%Y-%m-%d").date()
                if min_data is None or dt < min_data:
                    min_data = dt
                if max_data is None or dt > max_data:
                    max_data = dt
                if custo > 0 or pedidos > 0:
                    cac_calc = cac if cac > 0 else ((custo / pedidos) if pedidos > 0 else 0.0)
                    days_data[dt] = {
                        "custo": custo,
                        "pedidos": pedidos,
                        "cac": cac_calc,
                        "gmv": gmv,
                        "roi": roi,
                    }
            except Exception:
                pass

    if total_data is None:
        total_custo = sum(d["custo"] for d in days_data.values())
        total_pedidos = sum(d["pedidos"] for d in days_data.values())
        total_gmv = sum(d["gmv"] for d in days_data.values())
        cac_geral = (total_custo / total_pedidos) if total_pedidos > 0 else 0.0
        roi_geral = (total_gmv / total_custo) if total_custo > 0 else 0.0
        total_data = {
            "custo": total_custo,
            "pedidos": total_pedidos,
            "cac": cac_geral,
            "gmv": total_gmv,
            "roi": roi_geral,
        }

    despesas_total = total_data["custo"]
    gmv_total = total_data["gmv"]
    conversoes_total = total_data["pedidos"]
    cac_global = total_data["cac"]
    roas_global = total_data["roi"]

    # Registra ou atualiza a CampanhaAds do TikTok
    nome_campanha = "TikTok Ads - Campanhas da Loja (GMV Max / Diário)"
    campanha, _ = CampanhaAds.objects.update_or_create(
        canal="tiktok",
        nome_campanha=nome_campanha,
        defaults={
            "valor_investido": Decimal(str(round(despesas_total, 2))),
            "receita_atribuida": Decimal(str(round(gmv_total, 2))),
            "conversoes": conversoes_total,
            "itens_vendidos": conversoes_total,
            "roas_informado": Decimal(str(round(roas_global, 2))),
            "data_inicio": min_data,
            "data_fim": max_data,
        },
    )

    # Atribui o CAC nas vendas do TikTok
    vendas_tiktok = VendaMarketplace.objects.filter(canal="tiktok")
    vendas_atualizadas_total = 0
    pedidos_perdidos_cac_count = 0
    prejuizo_cac_cancelados_total = 0.0

    for v in vendas_tiktok:
        v.campanha_ads = campanha
        dt_venda = v.data_venda.date() if hasattr(v.data_venda, "date") else v.data_venda

        if dt_venda in days_data and days_data[dt_venda]["cac"] > 0:
            cac_atribuido = days_data[dt_venda]["cac"]
        else:
            cac_atribuido = cac_global if cac_global > 0 else 3.65

        v.custo_ads_atribuido = Decimal(str(round(cac_atribuido, 2)))

        if v.status == "cancelado":
            v.custo_ads_pedido_perdido = Decimal(str(round(cac_atribuido, 2)))
            pedidos_perdidos_cac_count += 1
            prejuizo_cac_cancelados_total += cac_atribuido

        v.save()
        vendas_atualizadas_total += 1

    return {
        "campanhas_processadas": 1,
        "despesas_total": round(despesas_total, 2),
        "gmv_total": round(gmv_total, 2),
        "conversoes_total": conversoes_total,
        "roas_medio": round(roas_global, 2),
        "cac_medio": round(cac_global, 2),
        "vendas_atualizadas": vendas_atualizadas_total,
        "pedidos_perdidos_cac_count": pedidos_perdidos_cac_count,
        "prejuizo_cac_cancelados_total": round(prejuizo_cac_cancelados_total, 2),
        "dias_com_anuncios": len(days_data),
    }
