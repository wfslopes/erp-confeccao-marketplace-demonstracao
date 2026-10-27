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
    ContaMarketplace,
    ImportacaoPlanilhaMarketplace,
    Produto,
    ProdutoMarketplace,
    VendaMarketplace,
)


def obter_ou_criar_produto_marketplace(nome, sku="", canal="shopee", prod_fabrica=None):
    """Localiza ou cadastra o ProdutoMarketplace de forma independente dos produtos da fábrica"""
    if not nome:
        return None
    nome_clean = re.sub(r"\s*\[\d+\]\s*$", "", str(nome)).strip()
    sku_clean = str(sku or "").strip()

    p = None
    if sku_clean and sku_clean != "-":
        p = ProdutoMarketplace.objects.filter(canal=canal, sku_marketplace__iexact=sku_clean).first()

    if not p:
        p = ProdutoMarketplace.objects.filter(canal=canal, nome_marketplace__iexact=nome_clean).first()

    if not p:
        p = ProdutoMarketplace.objects.filter(canal=canal, nome_marketplace__icontains=nome_clean[:35]).first()

    if p:
        if prod_fabrica and not p.produto_fabrica:
            p.produto_fabrica = prod_fabrica
            p.save(update_fields=["produto_fabrica"])
        return p

    p = ProdutoMarketplace.objects.create(
        canal=canal,
        sku_marketplace=sku_clean or f"{canal[:3].upper()}-{abs(hash(nome_clean)) % 100000}",
        nome_marketplace=nome_clean,
        produto_fabrica=prod_fabrica,
        custo_transferencia_padrao=0.00,
    )
    return p


def mapear_produto_fabrica(nome_marketplace, sku_marketplace=""):
    """Associa o nome/SKU do marketplace ao produto correspondente na fábrica"""
    if not nome_marketplace:
        return None

    nome_clean = nome_marketplace.lower()
    sku_clean = str(sku_marketplace or "").strip().upper()

    # 1. Tenta por SKU exato se informado
    if sku_clean and sku_clean != "-":
        prod = Produto.objects.filter(sku__iexact=sku_clean).first()
        if prod:
            return prod

    # 2. Mapeamento inteligente por palavras-chave dos modelos da Disfarce
    if "camisola" in nome_clean:
        return Produto.objects.filter(sku="037CAM").first() or Produto.objects.filter(nome__icontains="CAMISOLA").first()
    
    if "baby doll" in nome_clean or "babydoll" in nome_clean or "short doll" in nome_clean or "segunda pele" in nome_clean:
        return Produto.objects.filter(sku="020BBD").first() or Produto.objects.filter(nome__icontains="BABYDOLL").first()
    
    if "macaquinho" in nome_clean:
        return Produto.objects.filter(sku="025MAC").first() or Produto.objects.filter(nome__icontains="MACAQUINHO").first()
    
    if "cropped" in nome_clean or "top" in nome_clean:
        return Produto.objects.filter(sku="015TOP").first() or Produto.objects.filter(sku="010TOP/R").first()
    
    if "pijama" in nome_clean and "short" not in nome_clean and "baby" not in nome_clean:
        return Produto.objects.filter(sku="032PIJ").first() or Produto.objects.filter(nome__icontains="PIJAMA").first()
    
    if "conjunto" in nome_clean or "sutiã" in nome_clean or "soutien" in nome_clean:
        return (
            Produto.objects.filter(sku="TEST-CONJ-01").first()
            or Produto.objects.filter(sku="027SUT").first()
            or Produto.objects.filter(sku="001SUT").first()
            or Produto.objects.filter(nome__icontains="CONJUNTO").first()
        )

    # 3. Busca por similaridade genérica no nome
    palavras = [w for w in re.findall(r"\w+", nome_clean) if len(w) > 3]
    for w in palavras[:3]:
        prod = Produto.objects.filter(nome__icontains=w).first()
        if prod:
            return prod

    return None


def parse_date(date_val):
    """Converte valor de data para datetime válido preservando horário quando disponível"""
    if not date_val:
        return timezone.now()
    if isinstance(date_val, datetime):
        return timezone.make_aware(date_val) if timezone.is_naive(date_val) else date_val
    val_str = str(date_val).strip()
    for fmt in [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y",
    ]:
        try:
            dt = datetime.strptime(val_str[:19] if len(val_str) > 19 else val_str, fmt)
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except Exception:
            continue
    try:
        dt = datetime.strptime(val_str[:10], "%Y-%m-%d")
        return timezone.make_aware(dt)
    except Exception:
        pass
    return timezone.now()


def importar_planilha_shopee(arquivo_path, usuario=None, nome_original="", canal="shopee"):
    """Processa o Relatório de Rendimento oficial da Shopee (.xlsx ou .csv).
    Garante não-duplicação: pedidos já existentes no sistema são desconsiderados.
    """
    ext = os.path.splitext(arquivo_path)[1].lower()
    is_excel = ext in [".xlsx", ".xlsm", ".xls"]

    orders_data = {}
    skus_by_order = {}
    seller_name = "disfarcelingerie"
    periodo_de = None
    periodo_ate = None

    if is_excel:
        wb = openpyxl.load_workbook(arquivo_path, data_only=True)
        
        # Lê metadados da aba Summary se existir
        if "Summary" in wb.sheetnames:
            ws_sum = wb["Summary"]
            for r in range(1, min(20, ws_sum.max_row + 1)):
                c1 = str(ws_sum.cell(r, 1).value or "").strip()
                c2 = str(ws_sum.cell(r, 2).value or "").strip()
                if "Nome de usuário" in c1 and c2:
                    seller_name = c2
                elif c1 == "De" and c2:
                    try:
                        periodo_de = datetime.strptime(c2[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass
                elif c1 == "Para" and c2:
                    try:
                        periodo_ate = datetime.strptime(c2[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass

        # Usa aba 'Renda' ou a primeira aba
        sheet_name = "Renda" if "Renda" in wb.sheetnames else wb.sheetnames[0]
        ws = wb[sheet_name]

        # Encontra linha de cabeçalho
        header_row = 3
        for r in range(1, 10):
            val = str(ws.cell(r, 2).value or "").strip()
            if val == "Ver" or "pedido" in str(ws.cell(r, 3).value or "").lower():
                header_row = r
                break

        for r in range(header_row + 1, ws.max_row + 1):
            ver = str(ws.cell(r, 2).value or "").strip()
            order_id = str(ws.cell(r, 3).value or "").strip()
            if not order_id:
                continue

            if ver == "Order":
                orders_data[order_id] = {
                    "order_id": order_id,
                    "reembolso_id": str(ws.cell(r, 4).value or "").strip(),
                    "data_venda": parse_date(ws.cell(r, 7).value),
                    "data_pagamento": parse_date(ws.cell(r, 8).value).date() if ws.cell(r, 8).value else None,
                    "valor_liquido": float(ws.cell(r, 12).value or 0),
                    "preco_produto": float(ws.cell(r, 13).value or 0),
                    "reembolso": float(ws.cell(r, 14).value or 0),
                    "comissao": abs(float(ws.cell(r, 28).value or 0)),
                    "servico": abs(float(ws.cell(r, 29).value or 0)),
                    "transacao": abs(float(ws.cell(r, 30).value or 0)),
                    "afiliados": abs(float(ws.cell(r, 31).value or 0)),
                    "devolucao": abs(float(ws.cell(r, 32).value or 0)),
                    "comprador": str(ws.cell(r, 36).value or ""),
                    "metodo": str(ws.cell(r, 38).value or ""),
                }
            elif ver == "Sku":
                if order_id not in skus_by_order:
                    skus_by_order[order_id] = []
                skus_by_order[order_id].append({
                    "sku": str(ws.cell(r, 5).value or "").strip(),
                    "nome": str(ws.cell(r, 6).value or "").strip(),
                    "valor_liquido": float(ws.cell(r, 12).value or 0),
                    "preco_produto": float(ws.cell(r, 13).value or 0),
                    "comissao": abs(float(ws.cell(r, 28).value or 0)),
                    "servico": abs(float(ws.cell(r, 29).value or 0)),
                })
        wb.close()

    else:
        # Leitura de arquivo CSV
        with open(arquivo_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.reader(f)
            in_renda_section = False
            for row in reader:
                if not row or len(row) < 3:
                    continue
                
                # Metadados
                if "Nome de usuário (Vendedor)" in row[0] and len(row) > 1 and row[1]:
                    seller_name = row[1].strip()
                if row[0] == "De" and len(row) > 1 and row[1]:
                    try:
                        periodo_de = datetime.strptime(row[1].strip()[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass
                if row[0] == "Para" and len(row) > 1 and row[1]:
                    try:
                        periodo_ate = datetime.strptime(row[1].strip()[:10], "%Y-%m-%d").date()
                    except Exception:
                        pass

                if "Informações do pedido" in row[0] or (len(row) > 2 and row[1] == "Ver"):
                    in_renda_section = True
                    continue

                if in_renda_section and len(row) > 13:
                    ver = row[1].strip()
                    order_id = row[2].strip()
                    if not order_id:
                        continue

                    def to_f(v):
                        try:
                            return float(str(v).replace(",", ".").strip() or 0)
                        except Exception:
                            return 0.0

                    if ver == "Order":
                        orders_data[order_id] = {
                            "order_id": order_id,
                            "reembolso_id": row[3].strip() if len(row) > 3 else "",
                            "data_venda": parse_date(row[6]) if len(row) > 6 else timezone.now(),
                            "data_pagamento": parse_date(row[7]).date() if len(row) > 7 and row[7] else None,
                            "valor_liquido": to_f(row[11]) if len(row) > 11 else 0.0,
                            "preco_produto": to_f(row[12]) if len(row) > 12 else 0.0,
                            "reembolso": to_f(row[13]) if len(row) > 13 else 0.0,
                            "comissao": abs(to_f(row[27])) if len(row) > 27 else 0.0,
                            "servico": abs(to_f(row[28])) if len(row) > 28 else 0.0,
                            "transacao": abs(to_f(row[29])) if len(row) > 29 else 0.0,
                            "afiliados": abs(to_f(row[30])) if len(row) > 30 else 0.0,
                            "devolucao": abs(to_f(row[31])) if len(row) > 31 else 0.0,
                            "comprador": row[35].strip() if len(row) > 35 else "",
                            "metodo": row[37].strip() if len(row) > 37 else "",
                        }
                    elif ver == "Sku":
                        if order_id not in skus_by_order:
                            skus_by_order[order_id] = []
                        skus_by_order[order_id].append({
                            "sku": row[4].strip() if len(row) > 4 else "",
                            "nome": row[5].strip() if len(row) > 5 else "",
                            "valor_liquido": to_f(row[11]) if len(row) > 11 else 0.0,
                            "preco_produto": to_f(row[12]) if len(row) > 12 else 0.0,
                            "comissao": abs(to_f(row[27])) if len(row) > 27 else 0.0,
                            "servico": abs(to_f(row[28])) if len(row) > 28 else 0.0,
                        })

    # Conta de Marketplace no sistema
    conta, _ = ContaMarketplace.objects.get_or_create(
        canal=canal,
        defaults={
            "nome_conta": seller_name or f"Disfarce {canal.title()}",
            "taxa_comissao_padrao_pct": 14.00,
            "taxa_fixa_padrao": 4.50,
            "status_conexao": "conectado",
            "ativo": True,
        },
    )

    # Cria registro mestre da Importação
    importacao = ImportacaoPlanilhaMarketplace.objects.create(
        canal=canal,
        conta=conta,
        nome_arquivo=nome_original or os.path.basename(arquivo_path),
        usuario=usuario,
        periodo_de=periodo_de,
        periodo_ate=periodo_ate,
    )

    total_pedidos = len(orders_data)
    total_novos = 0
    total_duplicados = 0
    receita_bruta_acumulada = 0.0
    taxas_acumuladas = 0.0
    liquido_acumulado = 0.0
    lucro_liquido_acumulado = 0.0

    # Processa cada pedido
    for order_id, o in orders_data.items():
        # Verificação rigorosa de duplicidade:
        # Se o número do pedido ou código já constar no banco, desconsidera
        ja_existe = VendaMarketplace.objects.filter(
            Q(numero_pedido=order_id) | Q(codigo_pedido=order_id) | Q(codigo_pedido__startswith=f"{order_id}-")
        ).exists()

        if ja_existe:
            total_duplicados += 1
            continue

        itens = skus_by_order.get(order_id, [])
        status_pedido = "cancelado" if o["valor_liquido"] < 0 or o["reembolso"] < 0 else "aprovado"

        if not itens:
            # Pedido sem linha de SKU (grava nível pedido)
            prod = None
            custo_unit = 0.0
            venda = VendaMarketplace(
                numero_pedido=order_id,
                codigo_pedido=order_id,
                canal=canal,
                conta=conta,
                importacao=importacao,
                produto=prod,
                quantidade=1,
                data_venda=o["data_venda"],
                data_pagamento=o["data_pagamento"],
                comprador=o["comprador"],
                metodo_pagamento=o["metodo"],
                valor_bruto_venda=o["preco_produto"],
                valor_liquido_liberado=o["valor_liquido"],
                taxa_comissao_marketplace=o["comissao"],
                taxa_servico_marketplace=o["servico"],
                taxa_devolucao_facil=o["devolucao"],
                taxa_afiliados=o["afiliados"],
                taxa_transacao=o["transacao"],
                custo_produto_unitario=custo_unit,
                custo_produto_total=custo_unit,
                status=status_pedido,
            )
            venda.save()
            total_novos += 1
            receita_bruta_acumulada += o["preco_produto"]
            taxas_acumuladas += (o["comissao"] + o["servico"] + o["devolucao"] + o["afiliados"] + o["transacao"])
            liquido_acumulado += o["valor_liquido"]
            lucro_liquido_acumulado += float(venda.lucro_liquido)

        elif len(itens) == 1:
            # Pedido de 1 item
            it = itens[0]
            prod = mapear_produto_fabrica(it["nome"], it["sku"])
            prod_mkt = obter_ou_criar_produto_marketplace(it["nome"], it["sku"], canal=canal, prod_fabrica=prod)
            custo_vigente = prod_mkt.get_custo_para_data(o["data_venda"]) if prod_mkt else 0.0
            custo_unit = custo_vigente if custo_vigente > 0 else (float(prod.custo_materia_prima_total()) if prod else 0.0)

            qtd_pecas = prod_mkt.estimar_quantidade_pecas(o["preco_produto"], nome_item=it["nome"]) if prod_mkt else 1
            if prod_mkt and (not prod_mkt.preco_venda_unitario_base or prod_mkt.preco_venda_unitario_base == 0):
                if qtd_pecas == 1 and o["preco_produto"] > 0:
                    prod_mkt.preco_venda_unitario_base = o["preco_produto"]
                    prod_mkt.save(update_fields=["preco_venda_unitario_base"])

            venda = VendaMarketplace(
                numero_pedido=order_id,
                codigo_pedido=order_id,
                canal=canal,
                conta=conta,
                importacao=importacao,
                produto=prod,
                produto_marketplace=prod_mkt,
                nome_produto_marketplace=it["nome"],
                sku_marketplace=it["sku"],
                quantidade=1,
                quantidade_pecas_kit=qtd_pecas,
                data_venda=o["data_venda"],
                data_pagamento=o["data_pagamento"],
                comprador=o["comprador"],
                metodo_pagamento=o["metodo"],
                valor_bruto_venda=o["preco_produto"],
                valor_liquido_liberado=o["valor_liquido"],
                taxa_comissao_marketplace=o["comissao"],
                taxa_servico_marketplace=o["servico"],
                taxa_devolucao_facil=o["devolucao"],
                taxa_afiliados=o["afiliados"],
                taxa_transacao=o["transacao"],
                custo_produto_unitario=custo_unit,
                custo_produto_total=custo_unit * qtd_pecas,
                status=status_pedido,
            )
            venda.save()
            total_novos += 1
            receita_bruta_acumulada += o["preco_produto"]
            taxas_acumuladas += (o["comissao"] + o["servico"] + o["devolucao"] + o["afiliados"] + o["transacao"])
            liquido_acumulado += o["valor_liquido"]
            lucro_liquido_acumulado += float(venda.lucro_liquido)

        else:
            # Pedido com múltiplos itens/SKUs
            for idx, it in enumerate(itens, start=1):
                codigo_item = f"{order_id}-{idx}"
                prod = mapear_produto_fabrica(it["nome"], it["sku"])
                prod_mkt = obter_ou_criar_produto_marketplace(it["nome"], it["sku"], canal=canal, prod_fabrica=prod)
                custo_vigente = prod_mkt.get_custo_para_data(o["data_venda"]) if prod_mkt else 0.0
                custo_unit = custo_vigente if custo_vigente > 0 else (float(prod.custo_materia_prima_total()) if prod else 0.0)

                qtd_pecas = prod_mkt.estimar_quantidade_pecas(it["preco_produto"], nome_item=it["nome"]) if prod_mkt else 1
                if prod_mkt and (not prod_mkt.preco_venda_unitario_base or prod_mkt.preco_venda_unitario_base == 0):
                    if qtd_pecas == 1 and it["preco_produto"] > 0:
                        prod_mkt.preco_venda_unitario_base = it["preco_produto"]
                        prod_mkt.save(update_fields=["preco_venda_unitario_base"])

                # Rateio proporcional de taxas acessórias por item
                fator = (it["preco_produto"] / o["preco_produto"]) if o["preco_produto"] > 0 else (1.0 / len(itens))
                afiliados_item = round(o["afiliados"] * fator, 2)
                devolucao_item = round(o["devolucao"] * fator, 2)
                transacao_item = round(o["transacao"] * fator, 2)

                venda = VendaMarketplace(
                    numero_pedido=order_id,
                    codigo_pedido=codigo_item,
                    canal=canal,
                    conta=conta,
                    importacao=importacao,
                    produto=prod,
                    produto_marketplace=prod_mkt,
                    nome_produto_marketplace=it["nome"],
                    sku_marketplace=it["sku"],
                    quantidade=1,
                    quantidade_pecas_kit=qtd_pecas,
                    data_venda=o["data_venda"],
                    data_pagamento=o["data_pagamento"],
                    comprador=o["comprador"],
                    metodo_pagamento=o["metodo"],
                    valor_bruto_venda=it["preco_produto"],
                    valor_liquido_liberado=it["valor_liquido"],
                    taxa_comissao_marketplace=it["comissao"],
                    taxa_servico_marketplace=it["servico"],
                    taxa_devolucao_facil=devolucao_item,
                    taxa_afiliados=afiliados_item,
                    taxa_transacao=transacao_item,
                    custo_produto_unitario=custo_unit,
                    custo_produto_total=custo_unit * qtd_pecas,
                    status=status_pedido,
                )
                venda.save()
                venda.save()
                total_novos += 1
                receita_bruta_acumulada += it["preco_produto"]
                taxas_acumuladas += (it["comissao"] + it["servico"] + devolucao_item + afiliados_item + transacao_item)
                liquido_acumulado += it["valor_liquido"]
                lucro_liquido_acumulado += float(venda.lucro_liquido)

    # Atualiza registro da importação
    importacao.total_pedidos = total_pedidos
    importacao.total_novos = total_novos
    importacao.total_duplicados = total_duplicados
    importacao.receita_bruta_total = round(Decimal(str(receita_bruta_acumulada)), 2)
    importacao.taxas_total = round(Decimal(str(taxas_acumuladas)), 2)
    importacao.valor_liquido_total = round(Decimal(str(liquido_acumulado)), 2)
    importacao.lucro_liquido_total = round(Decimal(str(lucro_liquido_acumulado)), 2)
    importacao.save()

    conta.ultima_sincronizacao = timezone.now()
    conta.save()

    return {
        "importacao": importacao,
        "total_pedidos": total_pedidos,
        "total_novos": total_novos,
        "total_duplicados": total_duplicados,
        "receita_bruta": receita_bruta_acumulada,
        "taxas_total": taxas_acumuladas,
        "valor_liquido": liquido_acumulado,
        "lucro_liquido": lucro_liquido_acumulado,
        "seller_name": seller_name,
        "periodo_de": periodo_de,
        "periodo_ate": periodo_ate,
    }


def detectar_tipo_planilha_marketplace(arquivo_path, canal_default="shopee"):
    """Identifica automaticamente se o arquivo é da Shopee ou do TikTok Shop pelo cabeçalho"""
    ext = os.path.splitext(arquivo_path)[1].lower()
    is_excel = ext in [".xlsx", ".xlsm", ".xls"]

    try:
        if is_excel:
            wb = openpyxl.load_workbook(arquivo_path, read_only=True, data_only=True)
            ws = wb.active
            for r in range(1, min(15, ws.max_row + 1)):
                row_vals = [str(ws.cell(r, c).value or "").lower() for c in range(1, min(25, ws.max_column + 1))]
                text_line = " ".join(row_vals)
                if "order earnings" in text_line or "fee breakdown" in text_line or "net order margin" in text_line:
                    wb.close()
                    return "tiktok"
                if "relatório de rendimento" in text_line or "informações do pedido" in text_line or "número da sequência" in text_line:
                    wb.close()
                    return "shopee"
            wb.close()
        else:
            with open(arquivo_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                for _ in range(15):
                    line = f.readline().lower()
                    if not line:
                        break
                    if "order earnings" in line or "fee breakdown" in line or "net order margin" in line or "total transactions" in line:
                        return "tiktok"
                    if "relatório de rendimento" in line or "informações do pedido" in line or "número da sequência" in line:
                        return "shopee"
    except Exception:
        pass

    return canal_default or "shopee"


def parse_tiktok_date(val):
    if not val:
        return timezone.now()
    val_str = str(val).strip()
    try:
        if len(val_str) == 8 and val_str.isdigit():
            dt = datetime.strptime(val_str, "%Y%m%d")
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        elif len(val_str) >= 14 and val_str[:14].isdigit():
            dt = datetime.strptime(val_str[:14], "%Y%m%d%H%M%S")
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        elif len(val_str) >= 10 and '-' in val_str:
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(val_str[:len(fmt)], fmt)
                    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
                except Exception:
                    pass
    except Exception:
        pass
    return timezone.now()


def importar_planilha_tiktok(arquivo_path, usuario=None, nome_original="", canal="tiktok"):
    """Processa o Relatório Oficial de Liquidação / Extrato de Transações do TikTok Shop.
    Mapeia receitas, comissões, taxas fixas de R$ 4,00 por item, comissões de criadores/afiliados e frete.
    Anti-duplicação: pedidos já importados são desconsiderados.
    """
    ext = os.path.splitext(arquivo_path)[1].lower()
    is_excel = ext in [".xlsx", ".xlsm", ".xls"]

    conta, _ = ContaMarketplace.objects.get_or_create(
        canal=canal,
        defaults={
            "nome_conta": "TikTok Shop Oficial",
            "taxa_comissao_padrao_pct": Decimal("10.00"),
            "taxa_fixa_padrao": Decimal("4.00"),
            "ativo": True,
        },
    )

    importacao = ImportacaoPlanilhaMarketplace.objects.create(
        canal=canal,
        conta=conta,
        usuario=usuario,
        nome_arquivo=nome_original or os.path.basename(arquivo_path),
        total_pedidos=0,
        total_novos=0,
        total_duplicados=0,
    )

    rows_data = []

    def to_f(v):
        try:
            return float(str(v).replace(",", ".").strip() or 0)
        except Exception:
            return 0.0

    if is_excel:
        wb = openpyxl.load_workbook(arquivo_path, data_only=True)
        ws = wb.active
        header = None
        for r in range(1, ws.max_row + 1):
            row_vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
            row_strs = [str(x or "").strip() for x in row_vals]
            if "Order ID" in row_strs and "Product name" in row_strs:
                header = row_strs
                continue
            if header:
                if row_strs and row_strs[0] == "Order ID":
                    break
                if len(row_strs) >= len(header) - 2 and row_strs[0]:
                    d = dict(zip(header, row_vals))
                    rows_data.append(d)
        wb.close()
    else:
        with open(arquivo_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            reader = csv.reader(f)
            header = None
            for row in reader:
                if not row:
                    continue
                row_clean = [str(c).strip() for c in row]
                if "Order ID" in row_clean and "Product name" in row_clean:
                    header = row_clean
                    continue
                if header:
                    if row_clean and row_clean[0] == "Order ID":
                        break
                    if len(row_clean) >= len(header) - 2 and row_clean[0]:
                        d = dict(zip(header, row_clean))
                        rows_data.append(d)

    total_pedidos = len(rows_data)
    total_novos = 0
    total_duplicados = 0
    receita_bruta_acumulada = 0.0
    taxas_acumuladas = 0.0
    liquido_acumulado = 0.0
    lucro_liquido_acumulado = 0.0

    periodo_de = None
    periodo_ate = None

    for d in rows_data:
        order_id = str(d.get("Order ID") or "").strip()
        sku_id = str(d.get("SKU ID") or "").strip()
        sku_name = str(d.get("SKU name") or "").strip()
        prod_name = str(d.get("Product name") or "").strip()

        if not order_id:
            continue

        ja_existe = VendaMarketplace.objects.filter(
            Q(numero_pedido=order_id) | Q(codigo_pedido=order_id)
        ).exists()

        if ja_existe:
            total_duplicados += 1
            continue

        gross = to_f(d.get("Order earnings", 0))
        net = to_f(d.get("Net order margin", 0))
        items_sold = max(1, int(to_f(d.get("Items sold", 1))))
        refund = to_f(d.get("Product refunds", 0))
        status_raw = str(d.get("Order status") or "").strip().lower()
        is_canceled = (
            status_raw in ["canceled", "cancelled", "refunded"]
            or refund < 0
            or net < 0
        )
        status_pedido = "cancelado" if is_canceled else "aprovado"

        paid_date = parse_tiktok_date(d.get("Order paid date"))
        date_obj = paid_date.date() if hasattr(paid_date, "date") else paid_date
        if periodo_de is None or date_obj < periodo_de:
            periodo_de = date_obj
        if periodo_ate is None or date_obj > periodo_ate:
            periodo_ate = date_obj

        platform_fee = abs(to_f(d.get("Platform commission fee", 0)))
        creator_fee = abs(to_f(d.get("Commission paid to creators", 0)))
        affiliate_fee = abs(to_f(d.get("Commission paid to affiliate partners", 0)))
        sfp_fee = abs(to_f(d.get("SFP service fee", 0)))
        fixed_fee = abs(to_f(d.get("Fee per item sold", 0)))
        shipping_fee = abs(to_f(d.get("Shipping cost", 0)))

        # Fallback para regras oficiais caso não venha preenchido no CSV:
        preco_item = gross / items_sold if items_sold > 0 else gross
        from datetime import date
        if not fixed_fee:
            if date_obj and date_obj >= date(2026, 7, 15):
                taxa_unitaria = 6.00 if preco_item >= 50.00 else 4.00
            else:
                taxa_unitaria = 4.00
            fixed_fee = taxa_unitaria * items_sold

        if not platform_fee and gross > 0:
            if date_obj and date_obj >= date(2026, 7, 15):
                pct_comissao = 0.06 if preco_item >= 50.00 else 0.10
            else:
                pct_comissao = 0.06
            platform_fee = round(gross * pct_comissao, 2)

        # Taxa de serviço da campanha de frete (6% limitada a R$ 50 por item)
        if not sfp_fee and gross > 0 and not is_canceled:
            sfp_fee = round(min(50.00 * items_sold, gross * 0.06), 2)

        # Mapeia produto
        prod_fabrica = mapear_produto_fabrica(prod_name, sku_id)
        prod_mkt = obter_ou_criar_produto_marketplace(
            prod_name, sku=sku_id or f"TT-{order_id[:8]}", canal=canal, prod_fabrica=prod_fabrica
        )

        # Inteligência de Kit / Variação
        qtd_pecas = prod_mkt.estimar_quantidade_pecas(
            gross, nome_item=prod_name, variacao=sku_name
        ) if prod_mkt else 1

        custo_vigente = prod_mkt.get_custo_para_data(paid_date) if prod_mkt else 0.0
        custo_unit = custo_vigente if custo_vigente > 0 else (float(prod_fabrica.custo_materia_prima_total()) if prod_fabrica else 0.0)

        nome_exibicao = f"{prod_name} ({sku_name})" if sku_name else prod_name
        if len(nome_exibicao) > 255:
            nome_exibicao = nome_exibicao[:255]

        venda = VendaMarketplace(
            numero_pedido=order_id,
            codigo_pedido=order_id,
            canal=canal,
            conta=conta,
            importacao=importacao,
            produto=prod_fabrica,
            produto_marketplace=prod_mkt,
            nome_produto_marketplace=nome_exibicao,
            sku_marketplace=sku_id or f"TT-{order_id[:8]}",
            quantidade=items_sold,
            quantidade_pecas_kit=qtd_pecas,
            data_venda=paid_date,
            data_pagamento=date_obj,
            valor_bruto_venda=gross,
            valor_liquido_liberado=net,
            taxa_comissao_marketplace=platform_fee,
            taxa_servico_marketplace=sfp_fee,
            taxa_afiliados=creator_fee + affiliate_fee,
            taxa_fixa_marketplace=fixed_fee,
            taxa_devolucao_facil=shipping_fee,
            custo_produto_unitario=custo_unit,
            custo_produto_total=custo_unit * items_sold * qtd_pecas,
            status=status_pedido,
        )
        venda.save()

        total_novos += 1
        receita_bruta_acumulada += gross
        taxas_acumuladas += (platform_fee + sfp_fee + creator_fee + affiliate_fee + fixed_fee + shipping_fee)
        liquido_acumulado += net
        lucro_liquido_acumulado += float(venda.lucro_liquido)

    importacao.total_pedidos = total_pedidos
    importacao.total_novos = total_novos
    importacao.total_duplicados = total_duplicados
    importacao.receita_bruta_total = round(Decimal(str(receita_bruta_acumulada)), 2)
    importacao.taxas_total = round(Decimal(str(taxas_acumuladas)), 2)
    importacao.valor_liquido_total = round(Decimal(str(liquido_acumulado)), 2)
    importacao.lucro_liquido_total = round(Decimal(str(lucro_liquido_acumulado)), 2)
    importacao.save()

    conta.ultima_sincronizacao = timezone.now()
    conta.save()

    return {
        "importacao": importacao,
        "total_pedidos": total_pedidos,
        "total_novos": total_novos,
        "total_duplicados": total_duplicados,
        "receita_bruta": receita_bruta_acumulada,
        "taxas_total": taxas_acumuladas,
        "valor_liquido": liquido_acumulado,
        "lucro_liquido": lucro_liquido_acumulado,
        "seller_name": "TikTok Shop",
        "periodo_de": periodo_de,
        "periodo_ate": periodo_ate,
    }
