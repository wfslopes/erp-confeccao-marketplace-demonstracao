from django.contrib import admin
from .models import (
    Cliente, PedidoProducao, ItemPedidoProducao, TransacaoFinanceira, ConfiguracaoContaAzul,
    ConfiguracaoEngenharia, DificuldadeManuseio, ReferenciaMaquinaOperacao, OperacaoProduto
)

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nome', 'tag', 'telefone', 'cidade', 'uf', 'ativo')
    search_fields = ('nome', 'tag', 'cpf_cnpj', 'telefone', 'cidade')

class ItemPedidoInline(admin.TabularInline):
    model = ItemPedidoProducao
    extra = 1

@admin.register(PedidoProducao)
class PedidoProducaoAdmin(admin.ModelAdmin):
    list_display = ('numero_pedido', 'cliente', 'data_pedido', 'status', 'quantidade_total_pecas', 'valor_total')
    list_filter = ('status', 'data_pedido')
    search_fields = ('numero_pedido', 'cliente__nome')
    inlines = [ItemPedidoInline]

@admin.register(TransacaoFinanceira)
class TransacaoFinanceiraAdmin(admin.ModelAdmin):
    list_display = ('descricao', 'tipo', 'categoria', 'valor', 'data_vencimento', 'status', 'sincronizado_conta_azul')
    list_filter = ('tipo', 'status', 'categoria', 'data_vencimento', 'sincronizado_conta_azul')
    search_fields = ('descricao', 'cliente_fornecedor', 'id_conta_azul')

@admin.register(ConfiguracaoContaAzul)
class ConfiguracaoContaAzulAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'ativo', 'ultima_sincronizacao')

@admin.register(ConfiguracaoEngenharia)
class ConfiguracaoEngenhariaAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'tempo_pacote_min', 'tamanho_pacote', 'jornada_horas_dia', 'custo_minuto_costura')

@admin.register(DificuldadeManuseio)
class DificuldadeManuseioAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'tempo_min', 'ordem', 'ativo')
    list_editable = ('tempo_min', 'ordem', 'ativo')

@admin.register(ReferenciaMaquinaOperacao)
class ReferenciaMaquinaOperacaoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'nome', 'tipo_calculo', 'tempo_base', 'fator_elastico', 'fator_vies', 'ativo')
    list_editable = ('tempo_base', 'ativo')
    search_fields = ('codigo', 'nome')

@admin.register(OperacaoProduto)
class OperacaoProdutoAdmin(admin.ModelAdmin):
    list_display = ('produto', 'ordem', 'titulo', 'maquina_codigo', 'dificuldade', 'comprimento_costura_cm', 'tempo_padrao', 'tempo_padrao_pcte')
    list_filter = ('produto', 'maquina_codigo', 'dificuldade')
    search_fields = ('titulo', 'produto__nome', 'produto__sku')


