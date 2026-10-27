from django.test import TestCase
from decimal import Decimal
from django.utils import timezone
from .models import ProdutoMarketplace, VendaMarketplace, ContaMarketplace

class KitDetectionAndCostingTest(TestCase):
    def setUp(self):
        self.conta = ContaMarketplace.objects.create(
            canal='shopee',
            nome_conta='Disfarce Teste',
            taxa_comissao_padrao_pct=Decimal('14.00'),
            taxa_fixa_padrao=Decimal('4.50'),
            ativo=True
        )
        self.produto_mkt = ProdutoMarketplace.objects.create(
            canal='shopee',
            sku_marketplace='TEST-KIT-01',
            nome_marketplace='Kit 3 Cropped Feminino Estampado',
            custo_transferencia_padrao=Decimal('2.30'),
            preco_venda_unitario_base=Decimal('16.50'),
            kits_permitidos='3,5',
        )

    def test_nearest_multiple_detection_croppped(self):
        # R$ 49.50 should be 3 pieces
        k3 = self.produto_mkt.estimar_quantidade_pecas(Decimal('49.50'), nome_item=self.produto_mkt.nome_marketplace)
        self.assertEqual(k3, 3)

        # R$ 76.50 should be 5 pieces even though title says 'Kit 3'
        k5 = self.produto_mkt.estimar_quantidade_pecas(Decimal('76.50'), nome_item=self.produto_mkt.nome_marketplace)
        self.assertEqual(k5, 5)

    def test_venda_marketplace_total_cost_calculation(self):
        # 1 order of 5 pieces with unit factory cost R$ 2.30 -> total cost R$ 11.50
        venda = VendaMarketplace.objects.create(
            codigo_pedido='TEST-PED-5PCS',
            canal='shopee',
            conta=self.conta,
            produto_marketplace=self.produto_mkt,
            nome_produto_marketplace=self.produto_mkt.nome_marketplace,
            sku_marketplace=self.produto_mkt.sku_marketplace,
            quantidade=1,
            quantidade_pecas_kit=5,
            data_venda=timezone.now(),
            valor_bruto_venda=Decimal('76.50'),
            valor_liquido_liberado=Decimal('58.00'),
        )
        self.assertEqual(float(venda.custo_produto_unitario), 2.30)
        self.assertEqual(float(venda.custo_produto_total), 11.50)
        # Net profit: 58.00 - 11.50 = 46.50
        self.assertEqual(float(venda.lucro_liquido), 46.50)

    def test_marketplace_dashboard_renders_with_null_produto(self):
        from django.contrib.auth import get_user_model
        from django.test import Client
        User = get_user_model()
        user = User.objects.create_superuser('testadmin', 'test@test.com', 'adminpass')
        client = Client()
        client.force_login(user)

        # Create a sale where produto is None (only produto_marketplace)
        VendaMarketplace.objects.create(
            codigo_pedido='TEST-PED-NULL-PROD',
            canal='shopee',
            conta=self.conta,
            produto=None,
            produto_marketplace=self.produto_mkt,
            nome_produto_marketplace='Produto sem vínculo com fábrica',
            quantidade=1,
            data_venda=timezone.now(),
            valor_bruto_venda=Decimal('39.50'),
            valor_liquido_liberado=Decimal('30.00'),
        )

        response = client.get('/marketplace/')
        self.assertEqual(response.status_code, 200)

        # Test the new product performance strategy page
        response_desempenho = client.get('/marketplace/desempenho-produtos/')
        self.assertEqual(response_desempenho.status_code, 200)
        self.assertContains(response_desempenho, 'Diagnóstico de Lucratividade')

        # Test the new factory performance and integrated profit page
        response_fabrica = client.get('/marketplace/desempenho-fabrica/')
        self.assertEqual(response_fabrica.status_code, 200)
        self.assertContains(response_fabrica, 'Lucro Total Integrado')

        # Test updating factory production cost
        resp_salvar = client.post(f'/marketplace/produtos/{self.produto_mkt.id}/salvar-custo-fabrica/', {
            'custo_producao_fabrica': '1.80',
            'custo_transferencia_padrao': '2.50',
        })
        self.assertEqual(resp_salvar.status_code, 302)
        self.produto_mkt.refresh_from_db()
        self.assertEqual(float(self.produto_mkt.custo_producao_fabrica), 1.80)
        self.assertEqual(float(self.produto_mkt.custo_transferencia_padrao), 2.50)
        self.assertEqual(self.produto_mkt.get_lucro_unitario_fabrica(), 0.70)

    def test_tiktok_spreadsheet_import_and_anti_duplication(self):
        import os
        from fabrica.marketplace_importer import importar_planilha_tiktok, detectar_tipo_planilha_marketplace
        csv_path = r'C:\Users\wgfer\.gemini\antigravity\brain\9ba6433f-8c90-4d3f-81d8-09692312afd1\scratch\tiktok_sample.csv'
        if os.path.exists(csv_path):
            detected = detectar_tipo_planilha_marketplace(csv_path)
            self.assertEqual(detected, 'tiktok')
            res = importar_planilha_tiktok(csv_path, nome_original='tiktok_sample.csv')
            self.assertGreater(res['total_pedidos'], 0)
            # Re-import should detect 100% duplicates
            res2 = importar_planilha_tiktok(csv_path, nome_original='tiktok_sample.csv')
            self.assertEqual(res2['total_novos'], 0)
