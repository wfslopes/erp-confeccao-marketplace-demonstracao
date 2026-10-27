from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path(
    'producao/relatorio/<int:pk>/',
    views.relatorio_faccionista_view,
    name='relatorio_faccionista',
    ),
    path('produtos/', views.produtos_view, name='produtos'),
    path('produtos/editar/<int:pk>/', views.editar_produto, name='editar_produto'),
    path(
        'produtos/excluir/<int:pk>', views.excluir_produto, name='excluir_produto'
    ),
    path(
        'categorias/cadastrar/', views.categorias_view, name='cadastrar_categoria'
    ),
    path(
        'categorias/editar/<int:pk>/',
        views.editar_categoria,
        name='editar_categoria',
    ),
    path(
        'categorias/excluir/<int:pk>/',
        views.excluir_categoria,
        name='excluir_categoria',
    ),
    path('faccionistas/', views.faccionistas_view, name='faccionistas'),
    path(
        'faccionistas/editar/<int:pk>/',
        views.editar_faccionista,
        name='editar_faccionista',
    ),
    path(
        'faccionistas/excluir/<int:pk>/',
        views.excluir_faccionista,
        name='excluir_faccionista',
    ),
    path('producao/', views.producao_view, name='producao'),
    path('lotes-corte/', views.lotes_corte_view, name='lotes_corte'),
    path('lotes-corte/excluir/<int:pk>/', views.excluir_lote_corte, name='excluir_lote_corte'),
    path(
        'financeiro/', views.financeiro_view, name='financeiro'
    ),  # <-- Esta rota faltava!
    path('maquinas/', views.maquinas_view, name='maquinas'),
    path('maquinas/excluir/<int:pk>/', views.excluir_maquina, name='excluir_maquina'),
    path('produtos/<int:pk>/', views.detalhe_produto_view, name='detalhe_produto'),
    path('produtos/<int:pk>/insumo/adicionar/', views.adicionar_insumo_produto, name='adicionar_insumo_produto'),
    path('produtos/insumo/excluir/<int:pk>/', views.excluir_insumo_produto, name='excluir_insumo_produto'),
    path('produtos/<int:pk>/medida/adicionar/', views.adicionar_medida_produto, name='adicionar_medida_produto'),
    path('produtos/medida/excluir/<int:pk>/', views.excluir_medida_produto, name='excluir_medida_produto'),
    path('produtos/<int:pk>/ficha/atualizar/', views.atualizar_ficha_produto, name='atualizar_ficha_produto'),
    path('marketplace/', views.marketplace_dashboard_view, name='marketplace_dashboard'),
    path('marketplace/desempenho-produtos/', views.desempenho_produtos_marketplace_view, name='desempenho_produtos_marketplace'),
    path('marketplace/desempenho-fabrica/', views.desempenho_fabrica_marketplace_view, name='desempenho_fabrica_marketplace'),
    path('marketplace/produtos/', views.produtos_marketplace_view, name='produtos_marketplace'),
    path('marketplace/produtos/<int:pk>/salvar-custo-fabrica/', views.salvar_custo_fabrica_marketplace_view, name='salvar_custo_fabrica_marketplace'),
    path('marketplace/produtos/<int:pk>/atualizar-custo/', views.atualizar_custo_produto_marketplace_view, name='atualizar_custo_produto_marketplace'),
    path('marketplace/vendas/<int:pk>/alterar-kit/', views.alterar_kit_venda_marketplace_view, name='alterar_kit_venda_marketplace'),
    path('marketplace/importar-planilha/', views.importar_planilha_marketplace_view, name='importar_planilha_marketplace'),
    path('marketplace/importar-ads/', views.importar_planilha_ads_view, name='importar_planilha_ads'),
    path('marketplace/venda/adicionar/', views.adicionar_venda_marketplace, name='adicionar_venda_marketplace'),
    path('marketplace/campanha/adicionar/', views.adicionar_campanha_ads, name='adicionar_campanha_ads'),
    path('marketplace/campanha/<int:pk>/distribuir/', views.distribuir_ads_vendas, name='distribuir_ads_vendas'),
    path('marketplace/sincronizar/<str:canal>/', views.sincronizar_marketplace, name='sincronizar_marketplace'),
    path('marketplace/importar-planilha/', views.importar_planilha_marketplace_view, name='importar_planilha_marketplace'),
    path('usuarios/', views.usuarios_view, name='usuarios'),
    # Clientes, Pedidos & Previsão de Insumos
    path('pedidos/', views.pedidos_view, name='pedidos'),
    path('pedidos/<int:pk>/', views.detalhe_pedido_view, name='detalhe_pedido'),
    path('pedidos/<int:pk>/lista-compras/', views.imprimir_lista_compras_view, name='imprimir_lista_compras'),
    path('pedidos/excluir/<int:pk>/', views.excluir_pedido, name='excluir_pedido'),
    path('clientes/', views.clientes_view, name='clientes'),
    path('clientes/editar/<int:pk>/', views.editar_cliente, name='editar_cliente'),
    path('clientes/excluir/<int:pk>/', views.excluir_cliente, name='excluir_cliente'),
    # Calendário Visual de Produção
    path('calendario/', views.calendario_producao_view, name='calendario_producao'),
    # Fluxo de Caixa / Contas a Pagar e Receber & Conta Azul
    path('financeiro/contas/', views.financeiro_contas_view, name='financeiro_contas'),
    # Engenharia de Produto, Operações & Tempo Padrão (TP)
    path('operacoes/', views.operacoes_engenharia_view, name='operacoes_engenharia'),
    # Matérias-Primas & Insumos (Custos e Ficha Técnica)
    path('materias-primas/', views.materias_primas_view, name='materias_primas'),
]