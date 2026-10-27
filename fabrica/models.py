from django.contrib.auth.models import User
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Categoria(models.Model):
  nome = models.CharField(max_length=100, unique=True)

  def __str__(self):
    return self.nome


class Maquina(models.Model):
    nome = models.CharField(max_length=100, unique=True, verbose_name="Nome da Máquina")
    codigo = models.CharField(max_length=20, blank=True, null=True, verbose_name="Código (Estudo de Tempos)")
    referencia_operacao = models.ForeignKey(
        'ReferenciaMaquinaOperacao',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='maquinas_espelhadas',
        verbose_name="Referência Estudo de Tempos"
    )

    class Meta:
        ordering = ['nome']
        verbose_name = "Tipo de Máquina"
        verbose_name_plural = "Tipos de Máquinas"

    def __str__(self):
        if self.codigo:
            return f"{self.nome} ({self.codigo})"
        return self.nome


class Faccionista(models.Model):
  TIPO_CHOICES = [
      ('faccionista', 'Faccionista Externa'),
      ('costureira_interna', 'Costureira da Fábrica'),
  ]
  tipo = models.CharField(
      max_length=25,
      choices=TIPO_CHOICES,
      default='faccionista',
      verbose_name='Tipo de Prestador',
  )
  nome = models.CharField(max_length=150)
  telefone = models.CharField(max_length=20, blank=True, null=True)
  cep = models.CharField(max_length=10, blank=True, null=True)
  endereco = models.CharField(max_length=255, blank=True, null=True)
  ponto_referencia = models.CharField(max_length=255, blank=True, null=True)
  maquinas = models.ManyToManyField(Maquina, blank=True)
  ativo = models.BooleanField(default=True)

  def __str__(self):
    if self.tipo == 'costureira_interna':
      return f'{self.nome} (Costureira Fábrica)'
    return f'{self.nome} (Faccionista)'


class MateriaPrima(models.Model):
    codigo = models.CharField(max_length=50, blank=True, null=True, verbose_name="Grupo / Tipo")  # ex: TECIDO, AVIAMENTO, ACESSÓRIO
    nome = models.CharField(max_length=150, unique=True, verbose_name="Discriminação / Matéria-Prima")
    fornecedor = models.CharField(max_length=150, blank=True, null=True, verbose_name="Fornecedor")
    composicao = models.CharField(max_length=150, blank=True, null=True, verbose_name="Composição")
    gramatura = models.DecimalField(max_digits=8, decimal_places=4, blank=True, null=True, verbose_name="Gramatura (Kg/m²)")
    unidade_medida = models.CharField(max_length=20, default='KG', verbose_name="Unidade")
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000, verbose_name="Preço Unitário (R$)")
    estoque_metros = models.DecimalField(max_digits=12, decimal_places=4, default=0.0000, verbose_name="Estoque Atual")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['codigo', 'nome']
        verbose_name = "Matéria-Prima / Insumo"
        verbose_name_plural = "Matérias-Primas & Insumos"

    def __str__(self):
        return f"{self.nome} ({self.codigo or 'Geral'}) - R$ {self.preco_unitario:.2f}/{self.unidade_medida}"

    def recalcular_produtos(self):
        """Atualiza custo_unitario e custo_total em todos os produtos que utilizam esta matéria-prima."""
        itens = ItemConsumoMateriaPrima.objects.filter(
            Q(materia_prima=self) | Q(materia_prima_nome__iexact=self.nome)
        )
        produtos_afetados = set()
        for item in itens:
            item.materia_prima = self
            item.materia_prima_nome = self.nome
            item.custo_unitario = self.preco_unitario
            if self.unidade_medida:
                item.unidade_medida = self.unidade_medida
            qtd = float(item.quantidade_consumo or 0)
            preco = float(self.preco_unitario or 0)
            item.custo_total = round(qtd * preco, 4)
            item.save(update_fields=['materia_prima', 'materia_prima_nome', 'custo_unitario', 'unidade_medida', 'custo_total'])
            produtos_afetados.add(item.produto)

        for prod in produtos_afetados:
            prod.recalcular_custos()
        return len(produtos_afetados)

    def save(self, *args, **kwargs):
        is_update = self.pk is not None
        super().save(*args, **kwargs)
        if is_update:
            self.recalcular_produtos()


class Produto(models.Model):
    STATUS_CHOICES = [
        ('linha', 'Em Linha'),
        ('fora', 'Fora de Linha'),
    ]
    sku = models.CharField(max_length=50, unique=True)
    nome = models.CharField(max_length=150)
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE)
    descricao = models.TextField(blank=True, null=True)
    composicao = models.TextField(blank=True, null=True, verbose_name="Composição")
    ficha_tecnica = models.TextField(blank=True, null=True, verbose_name="Ficha Técnica")
    observacoes_medidas = models.TextField(blank=True, null=True, verbose_name="Observações de Medidas")
    custo_materia_prima = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000, verbose_name="Custo Total Matéria-Prima (R$)")
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='linha'
    )

    def recalcular_custos(self):
        itens = self.materias_primas_consumo.all()
        total = sum(float(item.custo_total or 0) for item in itens) if itens else 0.0000
        self.custo_materia_prima = round(total, 4)
        self.save(update_fields=['custo_materia_prima'])
        return self.custo_materia_prima

    def custo_materia_prima_total(self):
        if self.custo_materia_prima and float(self.custo_materia_prima) > 0:
            return round(float(self.custo_materia_prima), 4)
        itens = self.materias_primas_consumo.all()
        if not itens:
            return 0.0000
        return round(sum(float(item.custo_total or 0) for item in itens), 4)

    def total_operacoes(self):
        return self.operacoes.count()

    def tempo_padrao_total_min(self):
        ops = self.operacoes.all()
        if not ops:
            return 0.0
        return round(sum(float(op.tempo_padrao or 0) for op in ops), 4)

    def tempo_padrao_pcte_total_min(self):
        ops = self.operacoes.all()
        if not ops:
            return 0.0
        return round(sum(float(op.tempo_padrao_pcte or 0) for op in ops), 4)

    def tempo_padrao_formatado(self):
        total_min = self.tempo_padrao_total_min()
        mins = int(total_min)
        secs = int(round((total_min - mins) * 60))
        return f"{mins}m {secs:02d}s"

    def pecas_por_hora(self):
        tp = self.tempo_padrao_total_min()
        if tp <= 0:
            return 0.0
        return round(60.0 / tp, 1)

    def pecas_por_dia(self):
        return round(self.pecas_por_hora() * 8.0, 0)

    def distribuicao_maquinas(self):
        res = {}
        total = self.tempo_padrao_total_min()
        for op in self.operacoes.all():
            maq = op.maquina_nome or op.maquina_codigo or 'Outros'
            res[maq] = res.get(maq, 0.0) + float(op.tempo_padrao or 0)

        lista = []
        for maq, tempo in sorted(res.items(), key=lambda x: x[1], reverse=True):
            pct = round((tempo / total * 100), 1) if total > 0 else 0
            lista.append({
                'maquina': maq,
                'tempo': round(tempo, 3),
                'percentual': pct
            })
        return lista

    def __str__(self):
        return f'{self.sku} - {self.nome}'


class ItemConsumoMateriaPrima(models.Model):
    produto = models.ForeignKey(
        Produto, related_name='materias_primas_consumo', on_delete=models.CASCADE
    )
    materia_prima = models.ForeignKey(
        MateriaPrima, null=True, blank=True, on_delete=models.SET_NULL, related_name='itens_consumo'
    )
    materia_prima_nome = models.CharField(max_length=150)
    quantidade_consumo = models.DecimalField(
        max_digits=12, decimal_places=5, default=0.00000, verbose_name="Consumo Unitário"
    )
    unidade_medida = models.CharField(max_length=20, default='m')
    custo_unitario = models.DecimalField(
        max_digits=12, decimal_places=4, default=0.0000, verbose_name="Custo Unitário (R$)"
    )
    custo_total = models.DecimalField(
        max_digits=12, decimal_places=4, default=0.0000, verbose_name="Custo Total (R$)"
    )

    def save(self, *args, **kwargs):
        if self.materia_prima:
            self.materia_prima_nome = self.materia_prima.nome
            if not self.custo_unitario or float(self.custo_unitario) == 0:
                self.custo_unitario = self.materia_prima.preco_unitario
            if not self.unidade_medida or self.unidade_medida == 'm':
                self.unidade_medida = self.materia_prima.unidade_medida
        q = float(self.quantidade_consumo or 0)
        u = float(self.custo_unitario or 0)
        self.custo_total = round(q * u, 4)
        super().save(*args, **kwargs)
        if self.produto_id:
            self.produto.recalcular_custos()

    def delete(self, *args, **kwargs):
        prod = self.produto
        super().delete(*args, **kwargs)
        if prod:
            prod.recalcular_custos()

    def __str__(self):
        return f'{self.materia_prima_nome} ({self.quantidade_consumo} {self.unidade_medida})'


class MedidaProduto(models.Model):
  produto = models.ForeignKey(
      Produto, related_name='medidas', on_delete=models.CASCADE
  )
  tamanho = models.CharField(max_length=10)
  parte_peca = models.CharField(max_length=100)
  medida_cm = models.DecimalField(max_digits=6, decimal_places=2)
  tolerancia = models.CharField(max_length=30, blank=True, null=True, default='+/- 1.0 cm')

  def __str__(self):
    return f'{self.tamanho} - {self.parte_peca}: {self.medida_cm} cm'


class LoteCorte(models.Model):
  STATUS_CORTE = [
      ('criado', 'Criado / Aguardando Envio'),
      ('enviado', 'Enviado para o Cortador'),
      ('pronto', 'Pronto / Aguardando Retirada'),
      ('finalizado', 'Finalizado / Na Confecção'),
  ]

  codigo_lote = models.CharField(max_length=50, unique=True)
  produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
  cortador = models.CharField(max_length=150, blank=True, null=True)
  data_criacao = models.DateField(auto_now_add=True)
  pago_cortador = models.BooleanField(default=False)
  data_pagamento_cortador = models.DateField(blank=True, null=True)  
  data_envio_cortador = models.DateField(blank=True, null=True)
  data_prevista_retorno = models.DateField(blank=True, null=True)
  valor_unitario_corte = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  custo_total_corte = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  pago_cortador = models.BooleanField(default=False)
  quantidade_tecido_metros = models.DecimalField(max_digits=10, decimal_places=2)
  quantidade_total_pecas = models.PositiveIntegerField(default=0)
  status = models.CharField(
      max_length=30, choices=STATUS_CORTE, default='criado'
  )
  observacoes = models.TextField(blank=True, null=True)

  def quantidade_alocada(self):
    return sum(sub.quantidade for sub in self.sub_lotes.all())

  def quantidade_disponivel(self):
    return self.quantidade_total_pecas - self.quantidade_alocada()

  def __str__(self):
    return f'Lote {self.codigo_lote} - Ref: {self.produto.sku}'


class ItemGradeCorte(models.Model):
  lote_corte = models.ForeignKey(
      LoteCorte, related_name='grades', on_delete=models.CASCADE
  )
  cor = models.CharField(max_length=50)
  tamanho = models.CharField(max_length=10)
  quantidade = models.PositiveIntegerField()


class LoteProducao(models.Model):
  STATUS_LOTE = [
      ('fabrica_interna', 'Costura Interna (Fábrica)'),
      ('enviado_faccionista', 'Enviado para Faccionista'),
      ('concluido', 'Concluído / Retornado'),
  ]
  codigo_sub_lote = models.CharField(max_length=50, unique=True)
  lote_corte = models.ForeignKey(
      LoteCorte, on_delete=models.CASCADE, related_name='sub_lotes'
  )
  faccionista = models.ForeignKey(
      Faccionista, on_delete=models.SET_NULL, null=True, blank=True
  )
  processo_faccionista = models.CharField(max_length=150, blank=True, null=True)
  quantidade_enviada = models.PositiveIntegerField(default=0)
  quantidade_real_costurada = models.PositiveIntegerField(default=0)
  quantidade = models.PositiveIntegerField(default=0)
  pago_costura = models.BooleanField(default=False)
  data_pagamento_costura = models.DateField(blank=True, null=True)  # Novo
  status = models.CharField(
      max_length=30, choices=STATUS_LOTE, default='fabrica_interna'
  )

  data_envio = models.DateField(blank=True, null=True)
  data_retorno = models.DateField(blank=True, null=True)

  valor_unitario_costura = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  custo_total_costura = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  pago_costura = models.BooleanField(default=False)

  def __str__(self):
    return f'Sub-lote {self.codigo_sub_lote} ({self.quantidade} pçs)'


class ItemGradeProducao(models.Model):
  lote_producao = models.ForeignKey(
      LoteProducao, related_name='grades', on_delete=models.CASCADE
  )
  cor = models.CharField(max_length=50)
  tamanho = models.CharField(max_length=10)
  quantidade = models.PositiveIntegerField()



class ContaMarketplace(models.Model):
  CANAL_CHOICES = [
      ('shopee', 'Shopee'),
      ('mercadolivre', 'Mercado Livre'),
      ('tiktok', 'TikTok Shop'),
  ]
  STATUS_CONEXAO_CHOICES = [
      ('conectado', 'Conectado via API'),
      ('pendente', 'Aguardando Credenciais'),
      ('manual', 'Modo Lançamento / Planilha'),
  ]
  canal = models.CharField(max_length=30, choices=CANAL_CHOICES)
  nome_conta = models.CharField(max_length=150)
  taxa_comissao_padrao_pct = models.DecimalField(
      max_digits=5, decimal_places=2, default=14.00
  )
  taxa_fixa_padrao = models.DecimalField(
      max_digits=6, decimal_places=2, default=4.50
  )
  status_conexao = models.CharField(
      max_length=30, choices=STATUS_CONEXAO_CHOICES, default='conectado'
  )
  ativo = models.BooleanField(default=True)
  ultima_sincronizacao = models.DateTimeField(auto_now=True)

  def __str__(self):
    return f'{self.get_canal_display()} - {self.nome_conta}'


class ProdutoMarketplace(models.Model):
  CANAL_CHOICES = [
      ('shopee', 'Shopee'),
      ('mercadolivre', 'Mercado Livre'),
      ('tiktok', 'TikTok Shop'),
      ('todos', 'Todos os Canais'),
  ]
  sku_marketplace = models.CharField(max_length=120, db_index=True, verbose_name="SKU no Marketplace")
  nome_marketplace = models.CharField(max_length=255, verbose_name="Título / Nome do Anúncio no Marketplace")
  canal = models.CharField(max_length=30, choices=CANAL_CHOICES, default='shopee')
  id_produto_canal = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID do Produto no Canal")
  produto_fabrica = models.ForeignKey(
      Produto, on_delete=models.SET_NULL, null=True, blank=True, related_name='skus_marketplace',
      verbose_name="Modelo Fábrica Vinculado (Opcional)"
  )
  custo_transferencia_padrao = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00, verbose_name="Custo de Transferência Vigente (R$)"
  )
  custo_producao_fabrica = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00, verbose_name="Custo de Produção na Fábrica (R$)"
  )
  preco_venda_unitario_base = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00, verbose_name="Preço de Venda Base 1 Peça (R$)"
  )
  kits_permitidos = models.CharField(
      max_length=100, default="1,3,5", verbose_name="Kits Válidos no Anúncio (separados por vírgula)"
  )
  ativo = models.BooleanField(default=True)
  data_cadastro = models.DateTimeField(auto_now_add=True)
  ultima_atualizacao = models.DateTimeField(auto_now=True)

  class Meta:
    ordering = ['nome_marketplace']
    verbose_name = 'Produto do Marketplace'
    verbose_name_plural = 'Produtos do Marketplace'

  def __str__(self):
    return f"[{self.get_canal_display()}] {self.sku_marketplace or 'Sem SKU'} - {self.nome_marketplace}"

  def estimar_quantidade_pecas(self, valor_venda, nome_item="", variacao=""):
    """
    Calcula a quantidade de peças da variação usando a métrica de proximidade aos tiers permitidos:
    1. Calcula o tier ótimo por proximidade de preço e desconto progressivo de kit.
    2. Usa regex de texto (ex: 'Kit 3', 'Kit 5', '5 peças') como forte pista ou desempate,
       mas valida se o valor de venda é compatível (evitando falso positivo de título de anúncio que vende 3 e 5 peças).
    """
    import re
    p_venda = float(valor_venda or 0)
    p0 = float(self.preco_venda_unitario_base or 0)

    try:
      tiers = [int(x.strip()) for x in str(self.kits_permitidos or '1,3,5').split(',') if x.strip().isdigit()]
    except Exception:
      tiers = [1, 3, 5]
    if not tiers:
      tiers = [1]

    # Desconto progressivo estimado por kit
    def preco_esperado(k):
      if k == 1:
        desc = 0.0
      elif k == 2:
        desc = 0.05
      elif k == 3:
        desc = 0.10
      elif k == 4:
        desc = 0.12
      elif k == 5:
        desc = 0.15
      else:
        desc = 0.20
      return k * p0 * (1.0 - desc)

    # 1. Tier ótimo por distância euclidiana ao preço esperado
    melhor_k_preco = None
    if p0 > 0 and p_venda > 0:
      melhor_k_preco = min(tiers, key=lambda k: abs(p_venda - preco_esperado(k)))

    # 2. Busca menção textual na variação ou no título
    texto = f"{variacao} {nome_item}".lower()
    k_regex = None
    m = re.search(r'kit\s*(?:de\s*)?(\d+)', texto)
    if m:
      try:
        val = int(m.group(1))
        if val in tiers:
          k_regex = val
      except ValueError:
        pass

    if not k_regex:
      m2 = re.search(r'(\d+)\s*(?:unidades|unids?|peças|pecas|pcs)', texto)
      if m2:
        try:
          val = int(m2.group(1))
          if val in tiers:
            k_regex = val
        except ValueError:
          pass

    # 3. Decisão combinada blindada contra falsos positivos:
    if melhor_k_preco is not None:
      if k_regex == melhor_k_preco:
        return melhor_k_preco

      # Se regex sugere um k, mas o preço está distante do esperado para aquele k
      # (ex: anúncio se chama 'Kit 3 Cropped', mas o cliente comprou a opção de 5 peças por R$ 76,50)
      if k_regex is not None:
        esp_regex = preco_esperado(k_regex)
        esp_preco = preco_esperado(melhor_k_preco)
        erro_regex = abs(p_venda - esp_regex) / esp_regex if esp_regex > 0 else 1.0
        erro_preco = abs(p_venda - esp_preco) / esp_preco if esp_preco > 0 else 1.0
        if erro_preco < 0.20 and erro_regex > 0.30:
          return melhor_k_preco
        elif erro_regex <= 0.25:
          return k_regex

      return melhor_k_preco

    # Se não temos preço base cadastrado, usa o regex se existir, senão 1
    return k_regex if k_regex else 1

  def get_custo_para_data(self, data_ref=None):
    """Busca o custo de transferência da fábrica vigente na data da venda"""
    if not data_ref:
      return float(self.custo_transferencia_padrao or 0.0)

    if hasattr(data_ref, 'date'):
      data_busca = data_ref.date()
    else:
      data_busca = data_ref

    hist = (
        self.historico_custos.filter(data_vigencia_inicio__lte=data_busca)
        .filter(Q(data_vigencia_fim__isnull=True) | Q(data_vigencia_fim__gte=data_busca))
        .order_by('-data_vigencia_inicio', '-id')
        .first()
    )
    if hist:
      return float(hist.custo_transferencia)
    return float(self.custo_transferencia_padrao or 0.0)

  def get_custo_fabril_efetivo(self):
    """Retorna o custo fabril de produção informado manualmente ou herdado da ficha técnica da fábrica"""
    if self.custo_producao_fabrica and float(self.custo_producao_fabrica) > 0:
      return float(self.custo_producao_fabrica)
    if self.produto_fabrica:
      try:
        return float(self.produto_fabrica.custo_materia_prima_total() or 0.0)
      except Exception:
        return 0.0
    return 0.0

  def get_lucro_unitario_fabrica(self):
    """Margem bruta que a fábrica embolsa na venda da peça para o canal"""
    return round(float(self.custo_transferencia_padrao or 0.0) - self.get_custo_fabril_efetivo(), 2)

  def get_margem_fabrica_pct(self):
    """Margem percentual de lucro da fábrica sobre o preço de transferência"""
    transf = float(self.custo_transferencia_padrao or 0.0)
    if transf > 0:
      return round((self.get_lucro_unitario_fabrica() / transf) * 100.0, 2)
    return 0.0


class HistoricoCustoProdutoMarketplace(models.Model):
  produto_marketplace = models.ForeignKey(
      ProdutoMarketplace, on_delete=models.CASCADE, related_name='historico_custos'
  )
  custo_transferencia = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Custo de Transferência (R$)")
  data_vigencia_inicio = models.DateField(verbose_name="Válido a Partir de (Data Início)")
  data_vigencia_fim = models.DateField(null=True, blank=True, verbose_name="Válido Até (Data Fim)")
  motivo_ajuste = models.CharField(max_length=255, blank=True, null=True, verbose_name="Motivo do Reajuste")
  data_registro = models.DateTimeField(auto_now_add=True)

  class Meta:
    ordering = ['-data_vigencia_inicio', '-id']
    verbose_name = 'Histórico de Custo de Marketplace'
    verbose_name_plural = 'Histórico de Custos de Marketplace'

  def __str__(self):
    fim_str = self.data_vigencia_fim.strftime('%d/%m/%Y') if self.data_vigencia_fim else 'Atual'
    return f"{self.produto_marketplace.sku_marketplace}: R$ {self.custo_transferencia} (De {self.data_vigencia_inicio.strftime('%d/%m/%Y')} até {fim_str})"


class CampanhaAds(models.Model):
  CANAL_CHOICES = [
      ('shopee', 'Shopee Ads'),
      ('mercadolivre', 'Mercado Livre Ads'),
      ('tiktok', 'TikTok Ads'),
  ]
  canal = models.CharField(max_length=30, choices=CANAL_CHOICES)
  nome_campanha = models.CharField(max_length=150)
  id_produto_anuncio = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID do Produto no Canal")
  produto_marketplace = models.ForeignKey(
      ProdutoMarketplace,
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
      related_name='campanhas_ads',
  )
  produto = models.ForeignKey(
      Produto,
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
      related_name='campanhas_ads',
  )
  data_inicio = models.DateField(null=True, blank=True)
  data_fim = models.DateField(null=True, blank=True)
  impressoes = models.PositiveIntegerField(default=0)
  cliques = models.PositiveIntegerField(default=0)
  itens_vendidos = models.PositiveIntegerField(default=0)
  valor_investido = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  receita_atribuida = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  conversoes = models.PositiveIntegerField(default=0)
  roas_informado = models.DecimalField(
      max_digits=6, decimal_places=2, default=0.00
  )

  def roas_real(self):
    if self.valor_investido and self.valor_investido > 0:
      return round(float(self.receita_atribuida or 0) / float(self.valor_investido), 2)
    return float(self.roas_informado or 0.00)

  def custo_por_conversao(self):
    if self.conversoes and self.conversoes > 0 and self.valor_investido:
      return round(float(self.valor_investido) / int(self.conversoes), 2)
    return 0.00

  def __str__(self):
    return f'{self.get_canal_display()} - {self.nome_campanha}'


class ImportacaoPlanilhaMarketplace(models.Model):
  CANAL_CHOICES = [
      ('shopee', 'Shopee'),
      ('mercadolivre', 'Mercado Livre'),
      ('tiktok', 'TikTok Shop'),
  ]
  canal = models.CharField(max_length=30, choices=CANAL_CHOICES)
  conta = models.ForeignKey(
      ContaMarketplace,
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
      related_name='importacoes',
  )
  nome_arquivo = models.CharField(max_length=255)
  arquivo = models.FileField(upload_to='planilhas_marketplace/', blank=True, null=True)
  usuario = models.ForeignKey(
      User, on_delete=models.SET_NULL, null=True, blank=True
  )
  data_importacao = models.DateTimeField(auto_now_add=True)
  periodo_de = models.DateField(null=True, blank=True)
  periodo_ate = models.DateField(null=True, blank=True)
  total_pedidos = models.IntegerField(default=0)
  total_itens = models.IntegerField(default=0)
  total_novos = models.IntegerField(default=0)
  total_duplicados = models.IntegerField(default=0)
  receita_bruta_total = models.DecimalField(
      max_digits=12, decimal_places=2, default=0.00
  )
  taxas_total = models.DecimalField(
      max_digits=12, decimal_places=2, default=0.00
  )
  valor_liquido_total = models.DecimalField(
      max_digits=12, decimal_places=2, default=0.00
  )
  lucro_liquido_total = models.DecimalField(
      max_digits=12, decimal_places=2, default=0.00
  )
  observacoes = models.TextField(blank=True, null=True)

  class Meta:
    ordering = ['-data_importacao']
    verbose_name = 'Importação de Planilha de Faturamento'
    verbose_name_plural = 'Importações de Planilhas de Faturamento'

  def __str__(self):
    return f'{self.get_canal_display()} - {self.nome_arquivo} ({self.total_novos} novos / {self.total_duplicados} dupl.)'


class VendaMarketplace(models.Model):
  CANAL_CHOICES = [
      ('shopee', 'Shopee'),
      ('mercadolivre', 'Mercado Livre'),
      ('tiktok', 'TikTok Shop'),
  ]
  STATUS_PEDIDO = [
      ('aprovado', 'Aprovado / Pago'),
      ('enviado', 'Em Trânsito'),
      ('entregue', 'Entregue / Concluído'),
      ('cancelado', 'Cancelado / Devolvido'),
  ]

  numero_pedido = models.CharField(max_length=100, db_index=True, blank=True, null=True, verbose_name="Número do Pedido")
  codigo_pedido = models.CharField(max_length=120, unique=True, verbose_name="Código Único do Item/Pedido")
  canal = models.CharField(max_length=30, choices=CANAL_CHOICES)
  conta = models.ForeignKey(
      ContaMarketplace,
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
      related_name='vendas',
  )
  importacao = models.ForeignKey(
      ImportacaoPlanilhaMarketplace,
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
      related_name='vendas',
  )
  campanha_ads = models.ForeignKey(
      CampanhaAds,
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
      related_name='vendas',
  )
  produto = models.ForeignKey(
      Produto, on_delete=models.SET_NULL, null=True, blank=True, related_name='vendas_marketplace'
  )
  produto_marketplace = models.ForeignKey(
      ProdutoMarketplace,
      on_delete=models.SET_NULL,
      null=True,
      blank=True,
      related_name='vendas',
      verbose_name="Produto Marketplace Mapeado",
  )
  nome_produto_marketplace = models.CharField(
      max_length=255, blank=True, null=True, verbose_name="Nome no Marketplace"
  )
  sku_marketplace = models.CharField(
      max_length=100, blank=True, null=True, verbose_name="SKU no Marketplace"
  )
  quantidade = models.PositiveIntegerField(default=1)
  quantidade_pecas_kit = models.PositiveIntegerField(
      default=1, verbose_name="Peças por Kit / Variação"
  )
  data_venda = models.DateTimeField()
  data_pagamento = models.DateField(null=True, blank=True, verbose_name="Data Conclusão Pagamento")
  comprador = models.CharField(max_length=100, blank=True, null=True, verbose_name="Comprador")
  metodo_pagamento = models.CharField(max_length=50, blank=True, null=True, verbose_name="Método Pagamento")

  # Composição Financeira da Venda
  valor_bruto_venda = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
  valor_liquido_liberado = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00, verbose_name="Valor Líquido Liberado"
  )
  custo_produto_unitario = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  custo_produto_total = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  taxa_comissao_marketplace = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  taxa_servico_marketplace = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  taxa_devolucao_facil = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  taxa_afiliados = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  taxa_transacao = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  taxa_fixa_marketplace = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  custo_ads_atribuido = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  custo_ads_pedido_perdido = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00, verbose_name="Prejuízo de Ads (Venda Cancelada)"
  )
  imposto_estimado = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  outros_custos = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )

  lucro_liquido = models.DecimalField(
      max_digits=10, decimal_places=2, default=0.00
  )
  margem_liquida_pct = models.DecimalField(
      max_digits=6, decimal_places=2, default=0.00
  )
  status = models.CharField(
      max_length=30, choices=STATUS_PEDIDO, default='aprovado'
  )

  @property
  def total_taxas_marketplace(self):
    return (
        float(self.taxa_comissao_marketplace or 0)
        + float(self.taxa_servico_marketplace or 0)
        + float(self.taxa_devolucao_facil or 0)
        + float(self.taxa_afiliados or 0)
        + float(self.taxa_transacao or 0)
        + float(self.taxa_fixa_marketplace or 0)
    )

  def save(self, *args, **kwargs):
    # 1. Custo do produto: busca primeiro o custo de transferência do ProdutoMarketplace por vigência de data
    if self.produto_marketplace:
      custo_vigente = self.produto_marketplace.get_custo_para_data(self.data_venda)
      if custo_vigente > 0:
        self.custo_produto_unitario = custo_vigente

    # Se ainda não informado, tenta puxar do custo de matéria-prima cadastrado na fábrica
    elif (not self.custo_produto_unitario or float(self.custo_produto_unitario) == 0.0) and self.produto_id:
      custo_fabrica = self.produto.custo_materia_prima_total()
      if custo_fabrica:
        self.custo_produto_unitario = custo_fabrica

    qtd_itens = int(self.quantidade or 1)
    qtd_pecas = int(self.quantidade_pecas_kit or 1)
    self.custo_produto_total = round(float(self.custo_produto_unitario or 0) * qtd_itens * qtd_pecas, 2)

    # 2. Cálculo da taxa do marketplace caso não informada
    qtd = int(self.quantidade or 1)
    if self.canal == 'shopee':
      if (not self.taxa_comissao_marketplace or float(self.taxa_comissao_marketplace) == 0.0) and self.conta:
        pct = float(self.conta.taxa_comissao_padrao_pct or 0) / 100.0
        self.taxa_comissao_marketplace = round(float(self.valor_bruto_venda or 0) * pct, 2)
      if not self.taxa_fixa_marketplace or float(self.taxa_fixa_marketplace) == 0.0:
        data_ref = self.data_venda.date() if hasattr(self.data_venda, 'date') else self.data_venda
        from datetime import date
        taxa_item = 4.00 if (data_ref and data_ref < date(2024, 10, 1)) else 4.50
        self.taxa_fixa_marketplace = round(taxa_item * qtd, 2)

    elif self.canal == 'tiktok':
      data_ref = self.data_venda.date() if hasattr(self.data_venda, 'date') else self.data_venda
      from datetime import date
      preco_item = float(self.valor_bruto_venda or 0) / qtd if qtd > 0 else float(self.valor_bruto_venda or 0)

      # Regras oficiais TikTok Shop (Vigente a partir de 15/07/2026):
      # < R$ 50,00 -> Comissão: 10% | Taxa fixa: R$ 4,00 por item
      # >= R$ 50,00 -> Comissão: 6% | Taxa fixa: R$ 6,00 por item
      # Antes de 15/07/2026 -> Comissão: 6% | Taxa fixa: R$ 4,00 por item
      if data_ref and data_ref >= date(2026, 7, 15):
        if preco_item >= 50.00:
          pct_comissao = 0.06
          taxa_fixa_un = 6.00
        else:
          pct_comissao = 0.10
          taxa_fixa_un = 4.00
      else:
        pct_comissao = 0.06
        taxa_fixa_un = 4.00

      if not self.taxa_comissao_marketplace or float(self.taxa_comissao_marketplace) == 0.0:
        self.taxa_comissao_marketplace = round(float(self.valor_bruto_venda or 0) * pct_comissao, 2)

      if not self.taxa_fixa_marketplace or float(self.taxa_fixa_marketplace) == 0.0:
        self.taxa_fixa_marketplace = round(taxa_fixa_un * qtd, 2)

      # Taxa de serviço da campanha de frete (SFP): 6% limitado a R$ 50 por item
      if (not self.taxa_servico_marketplace or float(self.taxa_servico_marketplace) == 0.0) and self.status != 'cancelado':
        self.taxa_servico_marketplace = round(min(50.00 * qtd, float(self.valor_bruto_venda or 0) * 0.06), 2)

    else:
      if (not self.taxa_comissao_marketplace or float(self.taxa_comissao_marketplace) == 0.0) and self.conta:
        pct = float(self.conta.taxa_comissao_padrao_pct or 0) / 100.0
        self.taxa_comissao_marketplace = round(float(self.valor_bruto_venda or 0) * pct, 2)
      if not self.taxa_fixa_marketplace or float(self.taxa_fixa_marketplace) == 0.0:
        taxa_padrao = float(self.conta.taxa_fixa_padrao or 0) if self.conta else 4.00
        self.taxa_fixa_marketplace = round(taxa_padrao * qtd, 2)

    # 3. Atribuição de Custo de Ads se houver campanha vinculada
    if (not self.custo_ads_atribuido or float(self.custo_ads_atribuido) == 0.0) and self.campanha_ads:
      if self.campanha_ads.roas_informado and float(self.campanha_ads.roas_informado) > 0:
        self.custo_ads_atribuido = round(float(self.valor_bruto_venda) / float(self.campanha_ads.roas_informado), 2)
      elif self.campanha_ads.conversoes > 0 and self.campanha_ads.valor_investido > 0:
        self.custo_ads_atribuido = round(float(self.campanha_ads.valor_investido) / int(self.campanha_ads.conversoes), 2)

    # 4. Tratamento especial para Pedidos Cancelados / Devolvidos
    if self.status == 'cancelado':
      if self.custo_ads_atribuido and float(self.custo_ads_atribuido) > 0:
        self.custo_ads_pedido_perdido = self.custo_ads_atribuido
      # Prejuízo real = valor liberado residual (geralmente negativo por taxa de frete) menos o CAC perdido do Ads
      self.lucro_liquido = round(
          float(self.valor_liquido_liberado or 0) - float(self.custo_ads_pedido_perdido or 0), 2
      )
    else:
      # 5. Cálculo final do Lucro Líquido para pedidos normais
      if self.valor_liquido_liberado and float(self.valor_liquido_liberado) > 0:
        total_custos_internos = (
            float(self.custo_produto_total or 0)
            + float(self.custo_ads_atribuido or 0)
            + float(self.imposto_estimado or 0)
            + float(self.outros_custos or 0)
        )
        self.lucro_liquido = round(float(self.valor_liquido_liberado) - total_custos_internos, 2)
      else:
        total_deducoes = (
            float(self.custo_produto_total or 0)
            + float(self.taxa_comissao_marketplace or 0)
            + float(self.taxa_servico_marketplace or 0)
            + float(self.taxa_devolucao_facil or 0)
            + float(self.taxa_afiliados or 0)
            + float(self.taxa_transacao or 0)
            + float(self.taxa_fixa_marketplace or 0)
            + float(self.custo_ads_atribuido or 0)
            + float(self.imposto_estimado or 0)
            + float(self.outros_custos or 0)
        )
        self.lucro_liquido = round(float(self.valor_bruto_venda or 0) - total_deducoes, 2)

    if float(self.valor_bruto_venda or 0) > 0:
      self.margem_liquida_pct = round((self.lucro_liquido / float(self.valor_bruto_venda)) * 100.0, 2)
    else:
      self.margem_liquida_pct = 0.00

    super().save(*args, **kwargs)

  class Meta:
    ordering = ['-data_venda', '-codigo_pedido', '-id']
    verbose_name = 'Venda do Marketplace'
    verbose_name_plural = 'Vendas do Marketplace'

  def __str__(self):
    return f'{self.codigo_pedido} ({self.get_canal_display()}) - R$ {self.valor_bruto_venda}'


class Cliente(models.Model):
    nome = models.CharField(max_length=150, verbose_name="Nome / Razão Social")
    nome_fantasia = models.CharField(max_length=150, blank=True, null=True, verbose_name="Nome Fantasia / Contato")
    cpf_cnpj = models.CharField(max_length=30, blank=True, null=True, verbose_name="CPF / CNPJ")
    tag = models.CharField(max_length=150, blank=True, null=True, verbose_name="TAG da Peça / Marca", help_text="Qual tag/etiqueta personalizada deve ser colocada na peça deste cliente")
    telefone = models.CharField(max_length=30, blank=True, null=True, verbose_name="Telefone / WhatsApp")
    email = models.EmailField(blank=True, null=True, verbose_name="E-mail")
    cidade = models.CharField(max_length=100, blank=True, null=True, verbose_name="Cidade")
    uf = models.CharField(max_length=2, blank=True, null=True, verbose_name="UF")
    endereco = models.CharField(max_length=255, blank=True, null=True, verbose_name="Endereço Completo")
    observacoes = models.TextField(blank=True, null=True, verbose_name="Observações")
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nome']

    def __str__(self):
        if self.cidade and self.uf:
            return f"{self.nome} ({self.cidade}/{self.uf})"
        return self.nome

    def total_pedidos(self):
        return self.pedidos.count()


class PedidoProducao(models.Model):
    STATUS_CHOICES = [
        ('orcamento', 'Orçamento / Em Análise'),
        ('confirmado', 'Confirmado / Aguardando Insumos'),
        ('em_producao', 'Em Produção'),
        ('concluido', 'Concluído / Entregue'),
        ('cancelado', 'Cancelado'),
    ]

    numero_pedido = models.CharField(max_length=50, unique=True, verbose_name="Nº do Pedido")
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='pedidos', verbose_name="Cliente")
    data_pedido = models.DateField(default=timezone.now, verbose_name="Data do Pedido")
    data_entrega_prevista = models.DateField(blank=True, null=True, verbose_name="Previsão de Entrega")
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='confirmado', verbose_name="Status")
    observacoes = models.TextField(blank=True, null=True, verbose_name="Observações do Pedido")
    valor_total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Valor Total (R$)")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-data_pedido', '-id']

    def __str__(self):
        return f"{self.numero_pedido} - {self.cliente.nome}"

    def save(self, *args, **kwargs):
        if not self.numero_pedido:
            total_existente = PedidoProducao.objects.count() + 1
            self.numero_pedido = f"PED-{total_existente:04d}"
        super().save(*args, **kwargs)

    def quantidade_total_pecas(self):
        return sum(item.quantidade for item in self.itens.all())

    def calcular_previsao_insumos(self):
        """
        Calcula a previsão consolidada de matéria-prima e insumos necessários
        para produzir todos os itens deste pedido, baseado nas Fichas Técnicas dos Produtos.
        """
        insumos_map = {}
        for item in self.itens.select_related('produto').all():
            qtd_pecas = item.quantidade or 0
            consumos = item.produto.materias_primas_consumo.all()
            for c in consumos:
                chave = (c.materia_prima_nome.strip().lower(), c.unidade_medida.strip().lower())
                consumo_unit = float(c.quantidade_consumo or 0)
                consumo_item = consumo_unit * qtd_pecas
                custo_unit = float(c.custo_unitario or 0)
                custo_item = round(consumo_item * custo_unit, 2)

                if chave not in insumos_map:
                    insumos_map[chave] = {
                        'nome': c.materia_prima_nome.strip(),
                        'unidade': c.unidade_medida.strip(),
                        'quantidade_total': 0.0,
                        'custo_unitario': custo_unit,
                        'custo_total_estimado': 0.0,
                        'produtos_detalhe': []
                    }
                insumos_map[chave]['quantidade_total'] += consumo_item
                insumos_map[chave]['custo_total_estimado'] += custo_item
                insumos_map[chave]['produtos_detalhe'].append({
                    'produto': item.produto,
                    'quantidade_pecas': qtd_pecas,
                    'consumo_unitario': consumo_unit,
                    'subtotal': round(consumo_item, 4),
                    'custo_subtotal': custo_item
                })

        resultado = []
        for dado in insumos_map.values():
            dado['quantidade_total'] = round(dado['quantidade_total'], 4)
            dado['custo_total_estimado'] = round(dado['custo_total_estimado'], 2)
            resultado.append(dado)

        resultado.sort(key=lambda x: x['nome'].lower())
        return resultado

    def custo_total_insumos_previsto(self):
        previsao = self.calcular_previsao_insumos()
        return round(sum(item['custo_total_estimado'] for item in previsao), 2)

    def produtos_sem_ficha(self):
        """Retorna produtos do pedido que ainda não possuem matérias-primas cadastradas na ficha técnica."""
        produtos_sem = []
        for item in self.itens.select_related('produto').all():
            if not item.produto.materias_primas_consumo.exists():
                produtos_sem.append(item.produto)
        return produtos_sem


class ItemPedidoProducao(models.Model):
    pedido = models.ForeignKey(PedidoProducao, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='itens_pedido')
    quantidade = models.PositiveIntegerField(default=1, verbose_name="Qtd a Produzir (Peças)")
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, blank=True, null=True, verbose_name="Preço Unit. Venda (R$)")
    grade_cores_tamanhos = models.CharField(max_length=255, blank=True, null=True, verbose_name="Grade / Cores / Tamanhos")
    observacoes = models.TextField(blank=True, null=True, verbose_name="Observações do Item")

    def subtotal_venda(self):
        p = float(self.preco_unitario or 0)
        q = int(self.quantidade or 0)
        return round(p * q, 2)

    def __str__(self):
        return f"{self.quantidade}x {self.produto.sku} ({self.pedido.numero_pedido})"


class TransacaoFinanceira(models.Model):
    TIPO_CHOICES = [
        ('pagar', 'Conta a Pagar / Despesa'),
        ('receber', 'Conta a Receber / Receita'),
    ]
    STATUS_CHOICES = [
        ('pendente', 'Pendente / A Vencer'),
        ('pago', 'Quitado / Pago / Recebido'),
        ('atrasado', 'Vencido / Atrasado'),
        ('cancelado', 'Cancelado'),
    ]
    CATEGORIA_CHOICES = [
        ('Materia-Prima', 'Matéria-Prima / Tecidos'),
        ('Aviamentos', 'Aviamentos / Elásticos / Rendas'),
        ('Faccao', 'Mão de Obra (Facção Externa)'),
        ('Costura-Fabrica', 'Mão de Obra (Costureiras Fábrica)'),
        ('Corte', 'Mão de Obra (Cortador)'),
        ('Salarios', 'Salários & Encargos'),
        ('Fixos', 'Custos Fixos (Aluguel, Luz, Água)'),
        ('Manutencao', 'Manutenção & Peças de Máquinas'),
        ('Vendas-Atacado', 'Receita de Pedidos (Atacado)'),
        ('Marketplace', 'Receita de Marketplaces (Shopee / ML / TikTok)'),
        ('Outros', 'Outros'),
    ]

    tipo = models.CharField(max_length=15, choices=TIPO_CHOICES, verbose_name="Tipo de Conta")
    descricao = models.CharField(max_length=200, verbose_name="Descrição do Lançamento")
    categoria = models.CharField(max_length=100, default='Outros', verbose_name="Categoria")
    cliente_fornecedor = models.CharField(max_length=150, blank=True, null=True, verbose_name="Cliente / Fornecedor / Favorecido")
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Valor Nominal (R$)")
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, verbose_name="Valor Pago / Recebido (R$)")
    data_competencia = models.DateField(default=timezone.now, verbose_name="Data de Competência")
    data_vencimento = models.DateField(verbose_name="Data de Vencimento")
    data_pagamento = models.DateField(blank=True, null=True, verbose_name="Data de Pagamento / Liquidação")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pendente', verbose_name="Status")
    forma_pagamento = models.CharField(max_length=50, blank=True, null=True, default='PIX', verbose_name="Forma de Pagamento")
    conta_bancaria = models.CharField(max_length=100, default='Banco Principal', verbose_name="Conta Bancária")
    observacoes = models.TextField(blank=True, null=True, verbose_name="Observações")

    # Vínculos com o fluxo produtivo
    pedido = models.ForeignKey(PedidoProducao, null=True, blank=True, on_delete=models.SET_NULL, related_name='transacoes', verbose_name="Pedido Vinculado")
    sub_lote = models.ForeignKey('LoteProducao', null=True, blank=True, on_delete=models.SET_NULL, related_name='transacoes', verbose_name="Sub-lote de Costura")
    lote_corte = models.ForeignKey('LoteCorte', null=True, blank=True, on_delete=models.SET_NULL, related_name='transacoes', verbose_name="Lote de Corte")

    # Campos de Integração Conta Azul
    id_conta_azul = models.CharField(max_length=100, blank=True, null=True, verbose_name="ID no Conta Azul")
    sincronizado_conta_azul = models.BooleanField(default=False, verbose_name="Sincronizado com Conta Azul")
    ultima_sincronizacao = models.DateTimeField(blank=True, null=True, verbose_name="Data da Última Sincronização")

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['data_vencimento', '-id']

    def __str__(self):
        sinal = "+" if self.tipo == 'receber' else "-"
        return f"[{self.get_tipo_display()}] {self.descricao} - {sinal}R$ {self.valor}"

    def saldo_pendente(self):
        return round(float(self.valor or 0) - float(self.valor_pago or 0), 2)


class ConfiguracaoContaAzul(models.Model):
    client_id = models.CharField(max_length=200, blank=True, null=True, verbose_name="Client ID Conta Azul")
    client_secret = models.CharField(max_length=200, blank=True, null=True, verbose_name="Client Secret Conta Azul")
    basic_auth = models.CharField(max_length=500, blank=True, null=True, verbose_name="Header Authorization Basic")
    redirect_uri = models.CharField(max_length=255, default="https://contaazul.com", verbose_name="Redirect URI")
    usuario_erp = models.CharField(max_length=150, blank=True, null=True, verbose_name="Usuário ERP Sandbox")
    senha_erp = models.CharField(max_length=150, blank=True, null=True, verbose_name="Senha ERP Sandbox")
    access_token = models.TextField(blank=True, null=True, verbose_name="Access Token")
    refresh_token = models.TextField(blank=True, null=True, verbose_name="Refresh Token")
    expires_at = models.DateTimeField(blank=True, null=True, verbose_name="Expiração do Access Token")
    ativo = models.BooleanField(default=False, verbose_name="Integração Ativa")
    ultima_sincronizacao = models.DateTimeField(blank=True, null=True, verbose_name="Última Sincronização")

    def __str__(self):
        status_txt = "Ativo" if self.ativo else "Inativo"
        return f"Configuração Conta Azul ({status_txt})"


# ==============================================================================
# MÓDULO DE ENGENHARIA DO PRODUTO: OPERAÇÕES & TEMPO PADRÃO (TP)
# ==============================================================================

class ConfiguracaoEngenharia(models.Model):
    tempo_pacote_min = models.DecimalField(max_digits=6, decimal_places=4, default=0.7000, verbose_name="Tempo Padrão Pacote (min)")
    tamanho_pacote = models.IntegerField(default=50, verbose_name="Tamanho do Pacote (peças)")
    jornada_horas_dia = models.DecimalField(max_digits=4, decimal_places=2, default=8.00, verbose_name="Jornada Padrão Diária (horas)")
    tolerancia_padrao = models.DecimalField(max_digits=4, decimal_places=2, default=0.15, verbose_name="Tolerância Fadiga/Necessidades (%)")
    custo_minuto_costura = models.DecimalField(max_digits=8, decimal_places=4, default=0.3500, verbose_name="Custo Estimado por Minuto de Costura (R$)")

    def adicional_pacote_min(self):
        if self.tamanho_pacote and self.tamanho_pacote > 0:
            return float(self.tempo_pacote_min) / float(self.tamanho_pacote)
        return 0.014

    def __str__(self):
        return f"Configuração de Engenharia (Pcte: {self.tamanho_pacote} un / {self.tempo_pacote_min} min)"


class DificuldadeManuseio(models.Model):
    codigo = models.CharField(max_length=10, unique=True, verbose_name="Código da Dificuldade")
    nome = models.CharField(max_length=50, verbose_name="Grau de Dificuldade")
    tempo_min = models.DecimalField(max_digits=6, decimal_places=4, verbose_name="Tempo em Minutos")
    ordem = models.IntegerField(default=1, verbose_name="Ordem de Exibição")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['ordem', 'codigo']
        verbose_name = "Dificuldade de Manuseio"
        verbose_name_plural = "Dificuldades de Manuseio"

    def __str__(self):
        return f"{self.codigo} - {self.nome} ({self.tempo_min} min)"


class ReferenciaMaquinaOperacao(models.Model):
    TIPO_CALCULO_CHOICES = [
        ('10cm', 'A cada 10 cm de costura'),
        ('unidade', 'Por Batida / Peça / Unidade'),
    ]

    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código da Máquina/Operação")
    nome = models.CharField(max_length=100, verbose_name="Nome da Máquina / Processo")
    tipo_calculo = models.CharField(max_length=20, choices=TIPO_CALCULO_CHOICES, default='10cm', verbose_name="Tipo de Cálculo")
    tempo_base = models.DecimalField(max_digits=8, decimal_places=4, default=0.0700, verbose_name="Tempo Base s/ Aviamento (min)")
    fator_elastico = models.DecimalField(max_digits=6, decimal_places=4, default=0.0500, verbose_name="Acréscimo Elástico (+5%)")
    fator_vies = models.DecimalField(max_digits=6, decimal_places=4, default=0.0500, verbose_name="Acréscimo Viés (+5%)")
    fator_2vies = models.DecimalField(max_digits=6, decimal_places=4, default=0.1000, verbose_name="Acréscimo 2 Viés (+10%)")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ['codigo']
        verbose_name = "Referência de Operação / Máquina"
        verbose_name_plural = "Referências de Operações / Máquinas"

    def __str__(self):
        unidade_txt = "/10cm" if self.tipo_calculo == '10cm' else "/un"
        return f"{self.codigo} - {self.nome} ({self.tempo_base} min{unidade_txt})"


class OperacaoProduto(models.Model):
    CONDICAO_CHOICES = [
        ('sem_aviamento', 'Costura s/ Aviamento (Base)'),
        ('com_elastico', 'Costura c/ Elástico (+5%)'),
        ('com_vies', 'Costura c/ Viés (+5%)'),
        ('com_2vies', 'Costura c/ 2 Viés (+10%)'),
    ]

    DIFICULDADE_CHOICES = [
        ('F1', 'F1 - Muito Fácil (0.03 min)'),
        ('F2', 'F2 - Fácil (0.05 min)'),
        ('M1', 'M1 - Médio (0.07 min)'),
        ('M2', 'M2 - Médio Difícil (0.09 min)'),
        ('D1', 'D1 - Difícil (0.11 min)'),
        ('D2', 'D2 - Muito Difícil (0.13 min)'),
    ]

    produto = models.ForeignKey(Produto, related_name='operacoes', on_delete=models.CASCADE, verbose_name="Produto")
    ordem = models.IntegerField(default=1, verbose_name="Nº Sequência")
    titulo = models.CharField(max_length=250, verbose_name="O que fazer / Operação")
    parte_peca = models.CharField(max_length=100, blank=True, null=True, verbose_name="Parte da Peça")
    maquina_codigo = models.CharField(max_length=20, verbose_name="Código Máq/Operação")
    maquina_nome = models.CharField(max_length=100, blank=True, null=True, verbose_name="Máquina / Processo")
    condicao = models.CharField(max_length=30, choices=CONDICAO_CHOICES, default='sem_aviamento', verbose_name="Condição de Aviamento")
    aparelho = models.CharField(max_length=100, blank=True, null=True, verbose_name="Aparelho / Acessório")
    destino = models.CharField(max_length=100, blank=True, null=True, verbose_name="Destino / Posto")
    
    # Manuseio
    qtde_manuseio = models.IntegerField(default=1, verbose_name="Qtde Manuseios")
    dificuldade = models.CharField(max_length=5, choices=DIFICULDADE_CHOICES, default='F2', verbose_name="Dificuldade de Manuseio")
    comprimento_costura_cm = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name="Comprimento Costura (cm) ou Qtde Repetições")
    
    # Tempos Calculados Padrão
    tempo_manuseio = models.DecimalField(max_digits=8, decimal_places=4, default=0.0000, verbose_name="Tempo de Manuseio (min)")
    tempo_costura = models.DecimalField(max_digits=8, decimal_places=4, default=0.0000, verbose_name="Tempo de Costura (min)")
    tempo_padrao = models.DecimalField(max_digits=8, decimal_places=4, default=0.0000, verbose_name="Tempo Padrão TP (min)")
    tempo_padrao_pcte = models.DecimalField(max_digits=8, decimal_places=4, default=0.0000, verbose_name="TP com Pacote (min)")

    # Cronometragem Real / Estudo de Vídeo (Engenharia de Métodos)
    pot_seg = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="Cronometragem Segundos (POT SEG)")
    pot_min = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name="Cronometragem Minutos (POT MIN)")
    ritmo = models.DecimalField(max_digits=5, decimal_places=2, default=1.00, verbose_name="Ritmo do Operador (%)")
    tolerancia = models.DecimalField(max_digits=5, decimal_places=2, default=0.15, verbose_name="Tolerância (%)")
    tp_min_video = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name="TP Cronometrado Vídeo (min)")
    tp_min_video_pcte = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True, verbose_name="TP Vídeo c/ Pacote (min)")
    
    observacoes = models.TextField(blank=True, null=True, verbose_name="Observações Operacionais / Instrução de Trabalho")

    class Meta:
        ordering = ['ordem', 'id']
        verbose_name = "Operação de Fabricação"
        verbose_name_plural = "Operações de Fabricação"

    def save(self, *args, **kwargs):
        # 1. Obter fator de dificuldade de manuseio
        fatores_dificuldade = {
            'F1': 0.03,
            'F2': 0.05,
            'M1': 0.07,
            'M2': 0.09,
            'D1': 0.11,
            'D2': 0.13,
        }
        fator_dif = fatores_dificuldade.get(self.dificuldade, 0.05)
        try:
            dif_obj = DificuldadeManuseio.objects.filter(codigo=self.dificuldade).first()
            if dif_obj:
                fator_dif = float(dif_obj.tempo_min)
        except Exception:
            pass

        self.tempo_manuseio = round(float(self.qtde_manuseio or 0) * fator_dif, 4)

        # 2. Obter referência da máquina / operação
        tempo_base = 0.0700
        tipo_calc = '10cm'
        fator_elastico = 0.0500
        fator_vies = 0.0500
        fator_2vies = 0.1000

        ref = None
        if self.maquina_codigo:
            try:
                ref = ReferenciaMaquinaOperacao.objects.filter(codigo=self.maquina_codigo).first()
                if not ref and len(self.maquina_codigo) >= 3:
                    # Tenta sem sufixos de aviamento (ex: COLV -> COL, OVLE -> OVL)
                    cod_base = self.maquina_codigo
                    for suf in ['VV', 'V', 'E']:
                        if cod_base.endswith(suf) and len(cod_base) > len(suf):
                            cod_base = cod_base[:-len(suf)]
                            break
                    ref = ReferenciaMaquinaOperacao.objects.filter(codigo=cod_base).first()
            except Exception:
                pass

        if ref:
            tempo_base = float(ref.tempo_base)
            tipo_calc = ref.tipo_calculo
            fator_elastico = float(ref.fator_elastico)
            fator_vies = float(ref.fator_vies)
            fator_2vies = float(ref.fator_2vies)
            if not self.maquina_nome:
                self.maquina_nome = ref.nome

        # Ajuste por aviamento
        # Se o próprio código já indicava aviamento (ex: COLV, 2AGV, 3ZZE), ajusta a condição
        if self.maquina_codigo and self.maquina_codigo.endswith('VV') and self.condicao == 'sem_aviamento':
            self.condicao = 'com_2vies'
        elif self.maquina_codigo and self.maquina_codigo.endswith('V') and not self.maquina_codigo.endswith('REV') and self.condicao == 'sem_aviamento':
            self.condicao = 'com_vies'
        elif self.maquina_codigo and self.maquina_codigo.endswith('E') and self.condicao == 'sem_aviamento':
            self.condicao = 'com_elastico'

        if self.condicao == 'com_elastico':
            tempo_unit = tempo_base * (1.0 + fator_elastico)
        elif self.condicao == 'com_vies':
            tempo_unit = tempo_base * (1.0 + fator_vies)
        elif self.condicao == 'com_2vies':
            tempo_unit = tempo_base * (1.0 + fator_2vies)
        else:
            tempo_unit = tempo_base

        comp = float(self.comprimento_costura_cm or 0)
        if tipo_calc == '10cm':
            self.tempo_costura = round((comp / 10.0) * tempo_unit, 4)
        else:
            self.tempo_costura = round(comp * tempo_unit, 4)

        # 3. Tempo Padrão TP (Manuseio + Costura)
        self.tempo_padrao = round(float(self.tempo_manuseio) + float(self.tempo_costura), 4)

        # 4. Adicional de pacote (default 0.70 min / 50 peças = 0.014 min/peça)
        adicional_pcte = 0.0140
        try:
            cfg = ConfiguracaoEngenharia.objects.first()
            if cfg and cfg.tamanho_pacote:
                adicional_pcte = float(cfg.tempo_pacote_min) / float(cfg.tamanho_pacote)
        except Exception:
            pass

        self.tempo_padrao_pcte = round(float(self.tempo_padrao) + adicional_pcte, 4)

        # 5. Cronometragem Real Vídeo (POT SEG, RITMO, TOLERANCIA)
        if self.pot_seg and float(self.pot_seg) > 0:
            p_seg = float(self.pot_seg)
            if p_seg < 1.0 and p_seg > 0:
                segundos = p_seg * 100.0 if p_seg < 0.60 else p_seg * 60.0
            else:
                segundos = p_seg
            self.pot_min = round(segundos / 60.0, 4)
            ritmo_val = float(self.ritmo or 1.0)
            tol_val = float(self.tolerancia or 0.15)
            self.tp_min_video = round(float(self.pot_min) * ritmo_val * (1.0 + tol_val), 4)
            self.tp_min_video_pcte = round(float(self.tp_min_video) + adicional_pcte, 4)
        else:
            self.pot_min = None
            self.tp_min_video = None
            self.tp_min_video_pcte = None

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Op {self.ordem}: {self.titulo} ({self.maquina_codigo}) - TP: {self.tempo_padrao}m"


# Sinais para espelhamento automático das máquinas do estudo de tempos
from django.db.models.signals import post_save
from django.dispatch import receiver


def espelhar_maquinas_do_estudo():
    """Garante que todas as referências de máquinas do estudo de tempos estejam espelhadas em Maquina."""
    referencias = ReferenciaMaquinaOperacao.objects.filter(ativo=True)
    for ref in referencias:
        maq = Maquina.objects.filter(referencia_operacao=ref).first()
        if not maq:
            maq = Maquina.objects.filter(nome__iexact=ref.nome).first()
        if maq:
            maq.nome = ref.nome
            maq.codigo = ref.codigo
            maq.referencia_operacao = ref
            maq.save()
        else:
            Maquina.objects.create(
                nome=ref.nome,
                codigo=ref.codigo,
                referencia_operacao=ref,
            )


@receiver(post_save, sender=ReferenciaMaquinaOperacao)
def espelhar_referencia_maquina(sender, instance, created, **kwargs):
    if instance.ativo:
        maq = Maquina.objects.filter(referencia_operacao=instance).first()
        if not maq:
            maq = Maquina.objects.filter(nome__iexact=instance.nome).first()
        if maq:
            maq.nome = instance.nome
            maq.codigo = instance.codigo
            maq.referencia_operacao = instance
            maq.save()
        else:
            Maquina.objects.create(
                nome=instance.nome,
                codigo=instance.codigo,
                referencia_operacao=instance,
            )

