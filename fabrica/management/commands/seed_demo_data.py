"""
Comando de Seeding para Demonstração e Portfólio (Lumina ERP Gestão Fabril & Marketplace)
Gera uma base de dados completa, visualmente impactante e com matemática contábil coerente.
Uso: python manage.py seed_demo_data
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from fabrica.models import (
    Categoria, Maquina, Faccionista, MateriaPrima, Produto,
    ItemConsumoMateriaPrima, LoteCorte, ItemGradeCorte,
    LoteProducao, ItemGradeProducao, ContaMarketplace, ProdutoMarketplace,
    CampanhaAds, VendaMarketplace, Cliente, PedidoProducao,
    ItemPedidoProducao, TransacaoFinanceira, ConfiguracaoContaAzul
)


class Command(BaseCommand):
    help = "Popula o banco de dados com dados fictícios de alta qualidade para portfólio"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🚀 Iniciando geração de dados de demonstração (Lumina ERP)..."))

        # 1. Superuser
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@luminaerp.demo", "admin123")
            self.stdout.write(self.style.SUCCESS("✓ Superusuário criado: admin / admin123"))

        # 2. Categorias
        cat_lingerie, _ = Categoria.objects.get_or_create(nome="Lingerie & Moda Íntima")
        cat_praia, _ = Categoria.objects.get_or_create(nome="Moda Praia & Biquínis")
        cat_sleep, _ = Categoria.objects.get_or_create(nome="Pijamas & Sleepwear")
        self.stdout.write(self.style.SUCCESS("✓ Categorias de produtos criadas."))

        # 3. Máquinas Fabris
        maquinas_dados = [
            ("Overloque 4 Fios Direct Drive", "OV4F"),
            ("Reta Eletrônica Industrial", "RET1"),
            ("Galoneira Base Plana", "GAL1"),
            ("Travete Eletrônica", "TRAV"),
            ("Pespontadeira 2 Agulhas", "PESP"),
        ]
        maquinas_objs = []
        for nome, codigo in maquinas_dados:
            m, _ = Maquina.objects.get_or_create(nome=nome, defaults={"codigo": codigo})
            maquinas_objs.append(m)
        self.stdout.write(self.style.SUCCESS(f"✓ {len(maquinas_objs)} Máquinas industriais configuradas."))

        # 4. Faccionistas e Oficinas
        fac_interna, _ = Faccionista.objects.get_or_create(
            nome="Célula de Costura Interna",
            defaults={"tipo": "costureira_interna", "telefone": "(11) 98888-1001"}
        )
        fac_bela, _ = Faccionista.objects.get_or_create(
            nome="Oficina de Costura Bela Arte",
            defaults={"tipo": "faccionista", "telefone": "(11) 97777-2002"}
        )
        fac_santa, _ = Faccionista.objects.get_or_create(
            nome="Facção Santa Clara Confecções",
            defaults={"tipo": "faccionista", "telefone": "(11) 96666-3003"}
        )
        self.stdout.write(self.style.SUCCESS("✓ Equipes de costura e faccionistas cadastradas."))

        # 5. Matérias-Primas (Estoque de Insumos)
        materias_dados = [
            ("TECIDO", "Microfibra de Poliamida 180g", "Têxtil Nacional S/A", "KG", Decimal("48.00"), Decimal("180.0")),
            ("RENDA", "Renda Chantilly Poliamida 18cm", "Importadora Renda & Fios", "METRO", Decimal("8.50"), Decimal("650.0")),
            ("ELASTICO", "Elástico Sandreline 25mm", "Aviamentos Prime Ltda", "METRO", Decimal("1.80"), Decimal("1200.0")),
            ("BOJO", "Bojo Estruturado Casquinha (Par)", "ST Bojos do Brasil", "UNIDADE", Decimal("4.20"), Decimal("450.0")),
            ("ACESSORIO", "Fecho 2 Ganchos Regulável", "Aviamentos Prime Ltda", "UNIDADE", Decimal("0.90"), Decimal("800.0")),
            ("ALCA", "Alça Acetinada 10mm Conforto", "Aviamentos Prime Ltda", "METRO", Decimal("1.20"), Decimal("950.0")),
            ("TECIDO", "Cetim Silk Premium com Elastano", "Têxtil Nacional S/A", "METRO", Decimal("22.00"), Decimal("220.0")),
            ("TECIDO", "Tecido Trilobal Beach UV50+", "Malharia Brasil S/A", "METRO", Decimal("38.00"), Decimal("140.0")),
        ]
        mp_objs = {}
        for cod, nome, forn, un, preco, estoque in materias_dados:
            mp, _ = MateriaPrima.objects.get_or_create(
                nome=nome,
                defaults={
                    "codigo": cod,
                    "fornecedor": forn,
                    "unidade_medida": un,
                    "preco_unitario": preco,
                    "estoque_metros": estoque,
                    "ativo": True
                }
            )
            mp_objs[nome] = mp
        self.stdout.write(self.style.SUCCESS(f"✓ {len(mp_objs)} Matérias-primas e insumos cadastrados."))

        # 6. Produtos & Fichas Técnicas
        produtos_dados = [
            ("LUM-CONJ-001", "Conjunto Renda Sublime", cat_lingerie, Decimal("26.50"), "Microfibra e Renda Chantilly"),
            ("LUM-SUT-002", "Sutiã Bojo Comfort Fit", cat_lingerie, Decimal("18.20"), "Microfibra e Bojo Casquinha"),
            ("LUM-CALC-003", "Calcinha Fio Duplo Soft", cat_lingerie, Decimal("6.80"), "Microfibra Soft 90% Poliamida"),
            ("LUM-KIT-004", "Kit 3 Calcinhas Cotton Daily", cat_lingerie, Decimal("16.50"), "Algodão com Elastano"),
            ("LUM-PIJ-005", "Pijama Cetim Silk Elegance", cat_sleep, Decimal("39.00"), "Cetim Silk Premium"),
            ("LUM-BOD-006", "Body Rendado Manga Curta", cat_lingerie, Decimal("31.40"), "Renda e Tule de Poliamida"),
            ("LUM-BIQ-007", "Biquíni Cortininha UV50+", cat_praia, Decimal("22.80"), "Trilobal Beach UV50+"),
            ("LUM-MAI-008", "Maiô Decote V Modelador", cat_praia, Decimal("38.50"), "Poliamida Beach com Forro"),
        ]
        produtos_objs = []
        for sku, nome, cat, custo_f, comp in produtos_dados:
            p, _ = Produto.objects.get_or_create(
                sku=sku,
                defaults={
                    "nome": nome,
                    "categoria": cat,
                    "custo_materia_prima": custo_f,
                    "composicao": comp,
                    "status": "linha",
                }
            )
            produtos_objs.append(p)
        self.stdout.write(self.style.SUCCESS(f"✓ {len(produtos_objs)} Produtos de confecção modelados com ficha técnica."))

        # 7. Lotes de Corte e Sub-Lotes de Costura
        hoje = timezone.now().date()
        for i, prod in enumerate(produtos_objs[:4]):
            data_corte = hoje - timedelta(days=45 - (i * 8))
            lote, created = LoteCorte.objects.get_or_create(
                codigo_lote=f"LT-2026-{100 + i}",
                defaults={
                    "produto": prod,
                    "cortador": "Carlos Eduardo (Corte Industrial)",
                    "quantidade_tecido_metros": Decimal("35.50"),
                    "quantidade_total_pecas": 240,
                    "valor_unitario_corte": Decimal("1.25"),
                    "custo_total_corte": Decimal("300.00"),
                    "status": "finalizado",
                    "data_prevista_retorno": data_corte + timedelta(days=2),
                    "pago_cortador": True,
                    "data_pagamento_cortador": data_corte + timedelta(days=3),
                }
            )
            if created:
                for tam, qtd in [("P", 40), ("M", 100), ("G", 80), ("GG", 20)]:
                    ItemGradeCorte.objects.create(lote_corte=lote, tamanho=tam, quantidade=qtd)

                # Cria sub-lote de facção
                sub, _ = LoteProducao.objects.get_or_create(
                    codigo_sub_lote=f"SL-{lote.codigo_lote}-A",
                    defaults={
                        "lote_corte": lote,
                        "faccionista": fac_bela if i % 2 == 0 else fac_santa,
                        "quantidade": 240,
                        "quantidade_enviada": 240,
                        "quantidade_real_costurada": 238,
                        "valor_unitario_costura": Decimal("4.80"),
                        "custo_total_costura": Decimal("1142.40"),
                        "status": "concluido",
                        "data_envio": data_corte + timedelta(days=3),
                        "data_retorno": data_corte + timedelta(days=12),
                        "pago_costura": True,
                        "data_pagamento_costura": data_corte + timedelta(days=15),
                    }
                )

        self.stdout.write(self.style.SUCCESS("✓ Lotes de corte, grade de tamanhos e apontamentos de facção criados."))

        # 8. Contas de Marketplace
        conta_shopee, _ = ContaMarketplace.objects.get_or_create(
            canal="shopee",
            nome_conta="Shopee Oficial Lumina",
            defaults={"taxa_comissao_padrao_pct": Decimal("19.00"), "taxa_fixa_padrao": Decimal("4.00"), "status_conexao": "conectado", "ativo": True}
        )
        conta_ml, _ = ContaMarketplace.objects.get_or_create(
            canal="mercadolivre",
            nome_conta="Mercado Livre Full",
            defaults={"taxa_comissao_padrao_pct": Decimal("16.50"), "taxa_fixa_padrao": Decimal("6.00"), "status_conexao": "conectado", "ativo": True}
        )
        conta_tiktok, _ = ContaMarketplace.objects.get_or_create(
            canal="tiktok",
            nome_conta="TikTok Shop Lumina",
            defaults={"taxa_comissao_padrao_pct": Decimal("8.00"), "taxa_fixa_padrao": Decimal("0.00"), "status_conexao": "conectado", "ativo": True}
        )
        contas_mkt = [conta_shopee, conta_ml, conta_tiktok]
        self.stdout.write(self.style.SUCCESS("✓ 3 Canais de Marketplace configurados (Shopee, Mercado Livre, TikTok)."))

        # 9. Produtos no Marketplace com Preço de Transferência e Custo Fabril
        produtos_mkt_objs = []
        for conta in contas_mkt:
            for prod in produtos_objs:
                custo_fabrica = prod.custo_materia_prima
                transf = round(Decimal(str(custo_fabrica)) * Decimal("1.50"), 2)
                base_venda = round(Decimal(str(transf)) * Decimal("2.10"), 2)

                pm, _ = ProdutoMarketplace.objects.get_or_create(
                    canal=conta.canal,
                    sku_marketplace=f"{prod.sku}-{conta.canal[:3].upper()}",
                    defaults={
                        "nome_marketplace": f"{prod.nome} - Coleção Premium Lumina",
                        "produto_fabrica": prod,
                        "custo_transferencia_padrao": transf,           # Preço de transferência para a loja
                        "custo_producao_fabrica": custo_fabrica,        # Custo de manufatura na fábrica
                        "preco_venda_unitario_base": base_venda,
                        "kits_permitidos": "1,3,5",
                        "ativo": True,
                    }
                )
                produtos_mkt_objs.append(pm)
        self.stdout.write(self.style.SUCCESS(f"✓ {len(produtos_mkt_objs)} Itens mapeados com Lucro Integrado (Fábrica + Loja)."))

        # 10. Campanhas de Ads (Shopee Ads, Mercado Ads, TikTok Ads)
        campanhas_dados = [
            (conta_shopee, "Campanha Top Vendas - Conjuntos", Decimal("840.50"), Decimal("4650.00"), 4200, 310),
            (conta_shopee, "Shopee Ads - Lingerie Dia das Mães", Decimal("1250.00"), Decimal("7890.00"), 6800, 490),
            (conta_ml, "Mercado Ads - Full Express", Decimal("1580.00"), Decimal("9420.00"), 5100, 360),
            (conta_tiktok, "TikTok Ads - Vídeos Virais Pijamas", Decimal("920.00"), Decimal("6140.00"), 9200, 520),
            (conta_tiktok, "TikTok Live Shopping Promo", Decimal("650.00"), Decimal("4320.00"), 5600, 340),
        ]
        for conta, nome_c, gasto, receita, imp, cliq in campanhas_dados:
            CampanhaAds.objects.get_or_create(
                canal=conta.canal,
                nome_campanha=nome_c,
                defaults={
                    "data_inicio": hoje - timedelta(days=60),
                    "data_fim": hoje,
                    "valor_investido": gasto,
                    "receita_atribuida": receita,
                    "impressoes": imp,
                    "cliques": cliq,
                    "roas_informado": round(receita / gasto, 2) if gasto > 0 else Decimal("0.0"),
                }
            )
        self.stdout.write(self.style.SUCCESS("✓ Campanhas de Performance Ads cadastradas com ROAS e ROI calculados."))

        # 11. Vendas de Marketplace (Últimos 60 dias com DRE completo)
        random.seed(42)
        total_vendas_geradas = 0
        for dia_offset in range(60, 0, -1):
            data_venda_dt = hoje - timedelta(days=dia_offset)
            qtd_vendas_dia = random.randint(3, 7)

            for _ in range(qtd_vendas_dia):
                pm = random.choice(produtos_mkt_objs)
                qtd_pecas = random.choices([1, 2, 3], weights=[80, 15, 5])[0]
                valor_bruto = round(pm.preco_venda_unitario_base * qtd_pecas, 2)
                
                # Comissões e taxas proporcionais
                comissao = round(valor_bruto * Decimal("0.16"), 2)
                servico = round(valor_bruto * Decimal("0.02"), 2)
                taxa_fixa = Decimal("4.00")
                custo_prod = round(pm.custo_transferencia_padrao * qtd_pecas, 2)
                imposto = round(valor_bruto * Decimal("0.06"), 2)
                lucro = valor_bruto - comissao - servico - taxa_fixa - custo_prod - imposto
                margem_pct = round((lucro / valor_bruto) * Decimal("100"), 2) if valor_bruto > 0 else Decimal("0.0")

                naive_dt = datetime.combine(data_venda_dt, datetime.min.time()) + timedelta(hours=random.randint(8, 22), minutes=random.randint(0, 59))
                aware_dt = timezone.make_aware(naive_dt, timezone.get_current_timezone())

                codigo = f"PED-{pm.canal[:2].upper()}-{data_venda_dt.strftime('%y%m%d')}-{random.randint(1000, 9999)}"
                if not VendaMarketplace.objects.filter(codigo_pedido=codigo).exists():
                    VendaMarketplace.objects.create(
                        numero_pedido=codigo,
                        codigo_pedido=codigo,
                        canal=pm.canal,
                        conta=ContaMarketplace.objects.filter(canal=pm.canal).first(),
                        produto=pm.produto_fabrica,
                        produto_marketplace=pm,
                        nome_produto_marketplace=pm.nome_marketplace,
                        sku_marketplace=pm.sku_marketplace,
                        quantidade=qtd_pecas,
                        quantidade_pecas_kit=qtd_pecas,
                        data_venda=aware_dt,
                        data_pagamento=data_venda_dt + timedelta(days=random.randint(1, 5)),
                        comprador=f"Cliente {random.randint(100, 999)}",
                        metodo_pagamento=random.choice(["PIX", "Cartão de Crédito", "Boleto"]),
                        valor_bruto_venda=valor_bruto,
                        valor_liquido_liberado=valor_bruto - comissao - servico - taxa_fixa,
                        custo_produto_unitario=pm.custo_transferencia_padrao,
                        custo_produto_total=custo_prod,
                        taxa_comissao_marketplace=comissao,
                        taxa_servico_marketplace=servico,
                        taxa_fixa_marketplace=taxa_fixa,
                        imposto_estimado=imposto,
                        lucro_liquido=lucro,
                        margem_liquida_pct=margem_pct,
                        status="entregue",
                    )
                    total_vendas_geradas += 1

        self.stdout.write(self.style.SUCCESS(f"✓ {total_vendas_geradas} Pedidos de vendas de marketplace simulados com DRE completo."))

        # 12. Clientes Atacado & Pedidos
        cli_1, _ = Cliente.objects.get_or_create(
            nome="Boutique Elegance Moda Íntima",
            defaults={"cpf_cnpj": "11.222.333/0001-44", "email": "compras@boutiqueelegance.demo", "telefone": "(11) 98765-4321"}
        )
        cli_2, _ = Cliente.objects.get_or_create(
            nome="Distribuidora de Lingerie Brasil",
            defaults={"cpf_cnpj": "22.333.444/0001-55", "email": "pedidos@distribuidorabrasil.demo", "telefone": "(21) 99876-5432"}
        )

        for i, cli in enumerate([cli_1, cli_2]):
            ped, created = PedidoProducao.objects.get_or_create(
                numero_pedido=f"PED-ATAC-{202601 + i}",
                defaults={
                    "cliente": cli,
                    "data_pedido": hoje - timedelta(days=20 - (i * 10)),
                    "data_entrega_prevista": hoje + timedelta(days=10 + (i * 5)),
                    "valor_total": Decimal("4850.00") if i == 0 else Decimal("7200.00"),
                    "status": "em_producao",
                }
            )
            if created:
                ItemPedidoProducao.objects.create(pedido=ped, produto=produtos_objs[0], quantidade=50, preco_unitario=Decimal("55.00"), grade_cores_tamanhos="P:10, M:20, G:20")
                ItemPedidoProducao.objects.create(pedido=ped, produto=produtos_objs[1], quantidade=50, preco_unitario=Decimal("42.00"), grade_cores_tamanhos="P:10, M:20, G:20")

        self.stdout.write(self.style.SUCCESS("✓ Clientes atacado e carteira de pedidos B2B cadastrados."))

        # 13. Fluxo Financeiro (Contas a Pagar & Receber com Integração Conta Azul)
        transacoes_dados = [
            ("pagar", "Compra Tecido Microfibra 150kg (NF 4501)", "Materia-Prima", "Têxtil Nacional S/A", Decimal("7200.00"), hoje - timedelta(days=15), "pago", "CA-PAG-000101"),
            ("pagar", "Renda Chantilly Poliamida 500m", "Materia-Prima", "Importadora Renda & Fios", Decimal("4250.00"), hoje - timedelta(days=10), "pago", "CA-PAG-000102"),
            ("pagar", "Elásticos e Aviamentos Diversos", "Aviamentos", "Aviamentos Prime Ltda", Decimal("1860.00"), hoje - timedelta(days=5), "pago", "CA-PAG-000103"),
            ("pagar", "Mão de Obra Facção - Sublote LT-2026-100", "Faccao", "Oficina Bela Arte", Decimal("1142.40"), hoje - timedelta(days=8), "pago", "CA-PAG-000104"),
            ("pagar", "Corte Lotes 100 e 101", "Corte", "Carlos Eduardo (Cortador)", Decimal("600.00"), hoje - timedelta(days=12), "pago", "CA-PAG-000105"),
            ("pagar", "Aluguel Galpão Fabril & Escritório", "Fixos", "Imobiliária Central", Decimal("3800.00"), hoje + timedelta(days=5), "pendente", "CA-PAG-000106"),
            ("pagar", "Energia Elétrica Industrial", "Fixos", "Enel Distribuição", Decimal("1420.50"), hoje + timedelta(days=8), "pendente", "CA-PAG-000107"),
            ("pagar", "Honorários Contabilidade Empresarial", "Outros", "Sousa & Associados Contabilidade", Decimal("980.00"), hoje + timedelta(days=10), "pendente", "CA-PAG-000108"),
            ("pagar", "Manutenção Preventiva Overloque", "Manutencao", "Mecânica Têxtil Express", Decimal("450.00"), hoje - timedelta(days=2), "pago", "CA-PAG-000109"),
            ("receber", "Pedido Atacado Boutique Elegance - Sinal 50%", "Vendas-Atacado", "Boutique Elegance", Decimal("2425.00"), hoje - timedelta(days=18), "pago", "CA-REC-000201"),
            ("receber", "Repasse Semanal Shopee - Vendas Concluídas", "Marketplace", "Shopee Brasil", Decimal("6850.40"), hoje - timedelta(days=3), "pago", "CA-REC-000202"),
            ("receber", "Repasse Quinzenal Mercado Livre Full", "Marketplace", "Mercado Livre / Mercado Pago", Decimal("8940.10"), hoje - timedelta(days=1), "pago", "CA-REC-000203"),
            ("receber", "Repasse TikTok Shop - Vendas Lives", "Marketplace", "TikTok Shop Brasil", Decimal("4320.80"), hoje + timedelta(days=4), "pendente", "CA-REC-000204"),
            ("receber", "Pedido Atacado Distribuidora Brasil - Parcela 1", "Vendas-Atacado", "Distribuidora Brasil", Decimal("3600.00"), hoje + timedelta(days=7), "pendente", "CA-REC-000205"),
        ]

        for tipo, desc, cat, fav, valor, venc, st, ca_id in transacoes_dados:
            TransacaoFinanceira.objects.get_or_create(
                id_conta_azul=ca_id,
                defaults={
                    "tipo": tipo,
                    "descricao": desc,
                    "categoria": cat,
                    "cliente_fornecedor": fav,
                    "valor": valor,
                    "valor_pago": valor if st == "pago" else Decimal("0.00"),
                    "data_competencia": venc - timedelta(days=10),
                    "data_vencimento": venc,
                    "data_pagamento": venc if st == "pago" else None,
                    "status": st,
                    "sincronizado_conta_azul": True,
                    "ultima_sincronizacao": timezone.now(),
                }
            )

        # 14. Configuração Conta Azul (Simulada Ativa)
        cfg, _ = ConfiguracaoContaAzul.objects.get_or_create(id=1)
        cfg.client_id = "lumina_oauth_client_id_demo_2026"
        cfg.client_secret = "lumina_secret_key_demo_placeholder"
        cfg.ativo = True
        cfg.ultima_sincronizacao = timezone.now()
        cfg.save()
        self.stdout.write(self.style.SUCCESS("✓ Fluxo financeiro conciliado com carimbos do Conta Azul criado com sucesso."))

        self.stdout.write(self.style.SUCCESS("\n🎉 BASE DE DEMONSTRAÇÃO CONCLUÍDA COM SUCESSO!"))
        self.stdout.write(self.style.NOTICE("Acesse http://127.0.0.1:8000 com o usuário admin / admin123"))
