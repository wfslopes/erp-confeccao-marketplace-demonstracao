from django.core.management.base import BaseCommand
from decimal import Decimal
from fabrica.models import (
    Categoria, Produto, DificuldadeManuseio, ReferenciaMaquinaOperacao,
    ConfiguracaoEngenharia, OperacaoProduto
)

class Command(BaseCommand):
    help = "Popula tabelas de referência de engenharia e operações da planilha"

    def handle(self, *args, **options):
        self.stdout.write("Inicializando configurações e tabelas de referência...")

        # 1. Configuração de Engenharia
        cfg, _ = ConfiguracaoEngenharia.objects.get_or_create(id=1)
        cfg.tempo_pacote_min = Decimal('0.7000')
        cfg.tamanho_pacote = 50
        cfg.jornada_horas_dia = Decimal('8.00')
        cfg.tolerancia_padrao = Decimal('0.15')
        cfg.custo_minuto_costura = Decimal('0.3500')
        cfg.save()
        self.stdout.write("Configuração geral de Engenharia atualizada.")

        # 2. Dificuldade de Manuseio
        difs = [
            ('F1', 'Muito Fácil', Decimal('0.0300'), 1),
            ('F2', 'Fácil', Decimal('0.0500'), 2),
            ('M1', 'Médio', Decimal('0.0700'), 3),
            ('M2', 'Médio Difícil', Decimal('0.0900'), 4),
            ('D1', 'Difícil', Decimal('0.1100'), 5),
            ('D2', 'Muito Difícil', Decimal('0.1300'), 6),
        ]
        for cod, nome, t_min, ord_num in difs:
            DificuldadeManuseio.objects.update_or_create(
                codigo=cod,
                defaults={'nome': nome, 'tempo_min': t_min, 'ordem': ord_num, 'ativo': True}
            )
        self.stdout.write(f"{len(difs)} níveis de dificuldade de manuseio configurados.")

        # 3. Referência de Máquinas / Operações
        maquinas_ref = [
            ('20U', '20 U', '10cm', Decimal('0.0750')),
            ('ZZ', 'Zig-Zag', '10cm', Decimal('0.0750')),
            ('3ZZ', '3 Pontos Zig-Zag', '10cm', Decimal('0.0800')),
            ('1AG', 'Reta 1 Agulha', '10cm', Decimal('0.0700')),
            ('2AG', 'Reta 2 Agulhas', '10cm', Decimal('0.0800')),
            ('3AG', 'Reta 3 Agulhas', '10cm', Decimal('0.1000')),
            ('OVL', 'Overlock', '10cm', Decimal('0.0700')),
            ('COL', 'Colarete / Galoneira', '10cm', Decimal('0.0400')),
            ('INTL', 'Interlock', '10cm', Decimal('0.0500')),
            ('MAO', 'Manual / Geral', 'unidade', Decimal('0.0000')),
            ('LAC', 'Lacinho', 'unidade', Decimal('0.0500')),
            ('TRV', 'Travete', 'unidade', Decimal('0.0500')),
            ('REV', 'Revisão', 'unidade', Decimal('0.0000')),
            ('FLT', 'Flate', '10cm', Decimal('0.0600')),
            ('SILK', 'Etiqueta / Silk', 'unidade', Decimal('0.2000')),
            ('BTAO', 'Botão', 'unidade', Decimal('0.2000')),
        ]
        for cod, nome, t_calc, t_base in maquinas_ref:
            ReferenciaMaquinaOperacao.objects.update_or_create(
                codigo=cod,
                defaults={
                    'nome': nome,
                    'tipo_calculo': t_calc,
                    'tempo_base': t_base,
                    'fator_elastico': Decimal('0.0500'),
                    'fator_vies': Decimal('0.0500'),
                    'fator_2vies': Decimal('0.1000'),
                    'ativo': True
                }
            )
        self.stdout.write(f"{len(maquinas_ref)} referências de máquinas/operações configuradas.")

        # 4. Produtos e Operações da Planilha
        cat_lingerie, _ = Categoria.objects.get_or_create(nome='Lingerie & Moda Íntima')
        cat_fitness, _ = Categoria.objects.get_or_create(nome='Fitness & Top')

        produtos_dados = [
            {
                'sku': '027TNG',
                'nome': 'Calça Renda',
                'categoria': cat_lingerie,
                'operacoes': [
                    (1, 'FECHAR ENTREPERNA DIANT C/FORRO E TRASEIRA', 'OVL', 'sem_aviamento', 6, 'F2', Decimal('20.00'), None, None, 'TEM ESTA OPERAÇÃO EM OUTROS TAMANHOS?'),
                    (2, 'PREGAR VIES PERNA/CINTURA', 'COL', 'com_vies', 4, 'F2', Decimal('60.00'), Decimal('52.0'), Decimal('1.20'), ''),
                    (3, 'FECHAR ENTREPERNA TRASEIRA', 'OVL', 'sem_aviamento', 2, 'F2', Decimal('10.00'), Decimal('28.0'), Decimal('1.10'), ''),
                    (4, 'PREGAR ALÇAS 8X', 'TRV', 'sem_aviamento', 13, 'F1', Decimal('8.00'), Decimal('4.0'), Decimal('0.90'), ''),
                    (5, 'LIMPAR/REVISAR', 'MAO', 'sem_aviamento', 6, 'F1', Decimal('0.00'), Decimal('10.0'), Decimal('0.90'), ''),
                    (6, 'EMBALAR', 'MAO', 'sem_aviamento', 6, 'F1', Decimal('0.00'), Decimal('15.0'), Decimal('0.90'), ''),
                ]
            },
            {
                'sku': '027SUT',
                'nome': 'Soutien Renda',
                'categoria': cat_lingerie,
                'operacoes': [
                    (1, 'FECHAR MEIO PALA', 'OVL', 'sem_aviamento', 6, 'F2', Decimal('20.00'), Decimal('45.0'), Decimal('0.90'), ''),
                    (2, 'PREGAR ETIQUETA PALA', 'OVL', 'sem_aviamento', 2, 'F2', Decimal('10.00'), Decimal('138.0'), Decimal('0.80'), ''),
                    (3, 'FECHAR MEIO BOJO', 'OVL', 'sem_aviamento', 6, 'F2', Decimal('40.00'), Decimal('104.0'), Decimal('0.90'), ''),
                    (4, 'CHULEAR INF/BOJO', 'OVL', 'sem_aviamento', 4, 'F2', Decimal('40.00'), Decimal('18.0'), Decimal('0.70'), ''),
                    (5, 'PREGAR BOJO/PALA', 'OVL', 'sem_aviamento', 4, 'F2', Decimal('40.00'), Decimal('12.0'), Decimal('0.90'), ''),
                    (6, 'PREGAR VIES CAVA', 'COL', 'com_vies', 2, 'F2', Decimal('60.00'), Decimal('136.0'), Decimal('1.20'), ''),
                    (7, 'PREGAR ELASTICO EMB/BTO', '3ZZ', 'com_elastico', 1, 'M1', Decimal('60.00'), Decimal('24.0'), Decimal('0.70'), ''),
                    (8, 'PESPONTAR BOJO/PALA C/VIES', '2AG', 'com_vies', 4, 'M1', Decimal('40.00'), Decimal('58.0'), Decimal('0.80'), ''),
                    (9, 'PREGAR COLCHETE MACHO/FEMEA', 'ZZ', 'sem_aviamento', 4, 'M1', Decimal('20.00'), Decimal('129.0'), Decimal('1.00'), ''),
                    (10, 'ENFIAR ARCO PLUMA', 'MAO', 'sem_aviamento', 8, 'F2', Decimal('0.00'), Decimal('100.0'), Decimal('0.70'), ''),
                    (11, 'PREGAR ALÇAS E ARREM/VIES E PREGAR BIJU 10X', 'TRV', 'sem_aviamento', 17, 'F1', Decimal('10.00'), Decimal('20.0'), Decimal('1.00'), 'FALTOU UMA TRANSFER'),
                    (12, 'LIMPAR/REVISAR', 'MAO', 'sem_aviamento', 10, 'F1', Decimal('0.00'), None, None, 'FALTOU OPERAÇÃO'),
                    (13, 'EMBALAR', 'MAO', 'sem_aviamento', 6, 'F1', Decimal('0.00'), Decimal('44.0'), Decimal('1.00'), ''),
                ]
            },
            {
                'sku': '001SUT',
                'nome': 'Soutien Alice',
                'categoria': cat_lingerie,
                'operacoes': [
                    (1, 'FECHAR LATERAL PALA', 'OVL', 'sem_aviamento', 4, 'F2', Decimal('20.00'), Decimal('40.0'), Decimal('0.70'), 'FALTOU ETIQUETA ADESIVA NA SACOLA'),
                    (2, 'FECHAR BOJO', 'OVL', 'sem_aviamento', 4, 'F2', Decimal('80.00'), Decimal('52.0'), Decimal('1.20'), ''),
                    (3, 'PREGAR RENDA/BOJO', 'ZZ', 'sem_aviamento', 4, 'M1', Decimal('60.00'), None, None, ''),
                    (4, 'PREGAR ELASTICO EMB/BTO', '3ZZ', 'com_elastico', 1, 'M1', Decimal('70.00'), Decimal('21.0'), Decimal('1.10'), ''),
                    (5, 'PREGAR VIES CAVA', 'COL', 'com_vies', 2, 'F2', Decimal('40.00'), Decimal('4.0'), Decimal('0.90'), ''),
                    (6, 'ENCAPAR BOJO', 'OVL', 'sem_aviamento', 4, 'F2', Decimal('40.00'), Decimal('10.0'), Decimal('0.90'), ''),
                    (7, 'PREGAR BOJO/PALA', 'OVL', 'sem_aviamento', 4, 'F2', Decimal('40.00'), Decimal('15.0'), Decimal('0.90'), ''),
                    (8, 'PESPONTAR BOJO/PALA C/VIES', '2AG', 'com_vies', 4, 'M1', Decimal('40.00'), Decimal('36.0'), Decimal('1.00'), ''),
                    (9, 'PREGAR COLCHETE MACHO/FEMEA', 'ZZ', 'sem_aviamento', 4, 'M1', Decimal('20.00'), Decimal('135.0'), Decimal('0.80'), ''),
                    (10, 'ENFIAR ARCO PLUMA', 'MAO', 'sem_aviamento', 8, 'F2', Decimal('0.00'), Decimal('112.0'), Decimal('1.00'), 'VIDEO MENOR QUE TODOS OS MOVIMENTOS'),
                    (11, 'PREGAR ALÇAS E ARREM/VIES E PREGAR BIJU 9X', 'TRV', 'sem_aviamento', 16, 'F1', Decimal('9.00'), Decimal('45.0'), Decimal('0.90'), ''),
                    (12, 'LIMPAR/REVISAR', 'MAO', 'sem_aviamento', 9, 'F1', Decimal('0.00'), Decimal('20.0'), Decimal('0.90'), ''),
                    (13, 'EMBALAR', 'MAO', 'sem_aviamento', 6, 'F1', Decimal('0.00'), Decimal('42.0'), Decimal('1.00'), ''),
                ]
            },
            {
                'sku': '001TNG',
                'nome': 'Calça Alice',
                'categoria': cat_lingerie,
                'operacoes': [
                    (1, 'FECHAR ENTREPERNA DIANT C/FORRO E TRASEIRA', 'OVL', 'sem_aviamento', 6, 'F2', Decimal('20.00'), None, None, ''),
                    (2, 'PREGAR VIES PERNA/CINTURA', 'COL', 'com_vies', 4, 'F2', Decimal('90.00'), None, None, ''),
                    (3, 'PREGAR ALÇAS 9X', 'TRV', 'sem_aviamento', 16, 'F1', Decimal('9.00'), None, None, ''),
                    (4, 'LIMPAR/REVISAR', 'MAO', 'sem_aviamento', 6, 'F1', Decimal('0.00'), Decimal('23.0'), Decimal('1.00'), ''),
                    (5, 'EMBALAR', 'MAO', 'sem_aviamento', 6, 'F1', Decimal('0.00'), Decimal('128.0'), Decimal('1.00'), ''),
                ]
            },
            {
                'sku': '015TOP',
                'nome': 'Top Camille Farm',
                'categoria': cat_fitness,
                'operacoes': [
                    (1, 'FECHAR DECOTE/CAVA/TRASEIRA', 'OVL', 'sem_aviamento', 13, 'M1', Decimal('90.00'), Decimal('15.0'), Decimal('1.00'), ''),
                    (2, 'FECHAR LATERAIS', 'OVL', 'sem_aviamento', 4, 'M2', Decimal('80.00'), None, None, ''),
                    (3, 'CHULEAR BARRA', 'OVL', 'sem_aviamento', 6, 'F2', Decimal('80.00'), Decimal('20.0'), Decimal('1.10'), ''),
                    (4, 'PREGAR ELASTICO BARRA', 'OVL', 'com_elastico', 1, 'M1', Decimal('80.00'), Decimal('5.0'), Decimal('0.90'), ''),
                    (5, 'PESPONTAR ELASTICO BARRA', 'COL', 'sem_aviamento', 1, 'M1', Decimal('80.00'), Decimal('28.0'), Decimal('0.90'), ''),
                    (6, 'FAZER ALÇA/TECIDO', 'COL', 'com_vies', 1, 'F2', Decimal('80.00'), Decimal('16.0'), Decimal('1.15'), ''),
                    (7, 'PREGAR ALÇAS 6X', 'TRV', 'sem_aviamento', 10, 'F1', Decimal('6.00'), Decimal('4.0'), Decimal('0.80'), ''),
                    (8, 'LIMPAR/REVISAR', 'MAO', 'sem_aviamento', 4, 'F1', Decimal('0.00'), Decimal('4.0'), Decimal('1.00'), ''),
                    (9, 'EMBALAR', 'MAO', 'sem_aviamento', 8, 'F1', Decimal('0.00'), Decimal('4.0'), Decimal('1.00'), ''),
                ]
            },
            {
                'sku': '010TOP/R',
                'nome': 'Top Vitoria Roman',
                'categoria': cat_fitness,
                'operacoes': [
                    (1, 'FECHAR DECOTE/CAVA/TRASEIRA', 'OVL', 'sem_aviamento', 13, 'M1', Decimal('90.00'), Decimal('4.0'), Decimal('0.95'), ''),
                    (2, 'FECHAR LATERAIS', 'OVL', 'sem_aviamento', 4, 'M2', Decimal('80.00'), None, None, ''),
                    (3, 'CHULEAR BARRA', 'OVL', 'sem_aviamento', 6, 'F2', Decimal('80.00'), Decimal('3.0'), Decimal('0.95'), ''),
                    (4, 'PREGAR ELASTICO BARRA', 'OVL', 'com_elastico', 1, 'M1', Decimal('80.00'), Decimal('4.0'), Decimal('0.90'), ''),
                    (5, 'PESPONTAR ELASTICO BARRA', 'COL', 'sem_aviamento', 1, 'M1', Decimal('80.00'), Decimal('137.0'), Decimal('0.90'), ''),
                    (6, 'PREGAR ALÇAS 6X', 'TRV', 'sem_aviamento', 10, 'F1', Decimal('6.00'), None, None, ''),
                    (7, 'LIMPAR/REVISAR', 'MAO', 'sem_aviamento', 4, 'F1', Decimal('0.00'), Decimal('40.0'), Decimal('0.80'), ''),
                    (8, 'EMBALAR', 'MAO', 'sem_aviamento', 8, 'F1', Decimal('0.00'), Decimal('130.0'), Decimal('1.00'), ''),
                ]
            },
            {
                'sku': '010TOP/M',
                'nome': 'Top Vitoria Micro',
                'categoria': cat_fitness,
                'operacoes': [
                    (1, 'FECHAR DECOTE/CAVA/TRASEIRA', 'OVL', 'sem_aviamento', 13, 'M1', Decimal('90.00'), None, None, ''),
                    (2, 'FECHAR LATERAIS', 'OVL', 'sem_aviamento', 4, 'M2', Decimal('80.00'), None, None, ''),
                    (3, 'CHULEAR BARRA', 'OVL', 'sem_aviamento', 6, 'F2', Decimal('80.00'), None, None, ''),
                    (4, 'PREGAR ELASTICO BARRA', 'OVL', 'com_elastico', 1, 'M1', Decimal('80.00'), None, None, ''),
                    (5, 'PESPONTAR ELASTICO BARRA', 'COL', 'sem_aviamento', 1, 'M1', Decimal('80.00'), None, None, ''),
                    (6, 'PREGAR ALÇAS 6X', 'TRV', 'sem_aviamento', 10, 'F1', Decimal('6.00'), Decimal('27.0'), Decimal('0.90'), ''),
                    (7, 'LIMPAR/REVISAR', 'MAO', 'sem_aviamento', 4, 'F1', Decimal('0.00'), None, None, ''),
                    (8, 'EMBALAR', 'MAO', 'sem_aviamento', 8, 'F1', Decimal('0.00'), None, None, ''),
                ]
            }
        ]

        for p_data in produtos_dados:
            produto, _ = Produto.objects.update_or_create(
                sku=p_data['sku'],
                defaults={
                    'nome': p_data['nome'],
                    'categoria': p_data['categoria'],
                    'status': 'linha'
                }
            )

            # Recria operações com cálculos automáticos
            produto.operacoes.all().delete()
            for op in p_data['operacoes']:
                ordem_op, tit, maq_cod, cond, qtde_m, dif, comp, pot_s, ritmo, obs = op
                OperacaoProduto.objects.create(
                    produto=produto,
                    ordem=ordem_op,
                    titulo=tit,
                    maquina_codigo=maq_cod,
                    condicao=cond,
                    qtde_manuseio=qtde_m,
                    dificuldade=dif,
                    comprimento_costura_cm=comp,
                    pot_seg=pot_s,
                    ritmo=ritmo or Decimal('1.00'),
                    tolerancia=Decimal('0.15'),
                    observacoes=obs
                )
            self.stdout.write(f"Produto {produto.sku} ({produto.nome}): {produto.operacoes.count()} operações criadas com TP total = {produto.tempo_padrao_total_min()} min.")

        self.stdout.write(self.style.SUCCESS("Banco de dados populado com sucesso com dados da planilha!"))
