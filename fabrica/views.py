import calendar
import json
import os
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from .models import (
    Categoria,
    Cliente,
    ConfiguracaoContaAzul,
    ConfiguracaoEngenharia,
    DificuldadeManuseio,
    Faccionista,
    ImportacaoPlanilhaMarketplace,
    ItemConsumoMateriaPrima,
    ItemGradeCorte,
    ItemGradeProducao,
    ItemPedidoProducao,
    OperacaoProduto,
    PedidoProducao,
    ReferenciaMaquinaOperacao,
    TransacaoFinanceira,
    VendaMarketplace,
    CampanhaAds,
    ContaMarketplace,
    LoteCorte,
    LoteProducao,
    Maquina,
    MateriaPrima,
    MedidaProduto,
    Produto,
    ProdutoMarketplace,
    HistoricoCustoProdutoMarketplace,
    espelhar_maquinas_do_estudo,
)
from .conta_azul import ContaAzulService
from .marketplace_importer import (
    importar_planilha_shopee,
    importar_planilha_tiktok,
    detectar_tipo_planilha_marketplace,
)


def admin_required(view_func):
  @login_required(login_url='login')
  def _wrapped_view(request, *args, **kwargs):
    if not request.user.is_superuser:
      messages.error(
          request,
          'Acesso restrito: seu perfil de funcionário possui acesso apenas de visualização. Somente administradores podem alterar ou excluir dados.'
      )
      return redirect(request.META.get('HTTP_REFERER') or 'home')
    return view_func(request, *args, **kwargs)

  return _wrapped_view


def verificar_permissao_adm(request):
  if not request.user.is_superuser:
    messages.error(
        request,
        'Acesso restrito: seu perfil de funcionário possui acesso apenas de visualização. Somente administradores podem cadastrar ou alterar dados.'
    )
    return False
  return True


@login_required(login_url='login')
def home_view(request):
  total_produtos = Produto.objects.count()
  total_faccionistas = Faccionista.objects.filter(ativo=True).count()
  lotes_corte_abertos = LoteCorte.objects.exclude(status='finalizado').count()
  producao_andamento = LoteProducao.objects.exclude(status='concluido').count()

  ultimos_cortes = LoteCorte.objects.select_related('produto').order_by('-id')[
      :5
  ]
  ultimos_producao = (
      LoteProducao.objects.select_related('lote_corte__produto', 'faccionista')
      .order_by('-id')[:5]
  )

  context = {
      'total_produtos': total_produtos,
      'total_faccionistas': total_faccionistas,
      'lotes_corte_abertos': lotes_corte_abertos,
      'producao_andamento': producao_andamento,
      'ultimos_cortes': ultimos_cortes,
      'ultimos_producao': ultimos_producao,
  }
  return render(request, 'fabrica/home.html', context)


@login_required(login_url='login')
def faccionistas_view(request):
  if request.method == 'POST':
    if not verificar_permissao_adm(request):
      return redirect('faccionistas')
    tipo = request.POST.get('tipo', 'faccionista')
    nome = (request.POST.get('nome') or '').strip()
    telefone = request.POST.get('telefone')
    cep = request.POST.get('cep')
    endereco = request.POST.get('endereco')
    ponto_referencia = request.POST.get('ponto_referencia')
    maquinas_ids = request.POST.getlist('maquinas')

    if nome:
      faccionista = Faccionista.objects.create(
          tipo=tipo,
          nome=nome,
          telefone=telefone,
          cep=cep,
          endereco=endereco,
          ponto_referencia=ponto_referencia,
      )
      if maquinas_ids:
        faccionista.maquinas.set(maquinas_ids)
      rotulo = 'Costureira da Fábrica' if tipo == 'costureira_interna' else 'Faccionista'
      messages.success(request, f'{rotulo} "{nome}" cadastrada com sucesso.')
      return redirect('faccionistas')

  faccionistas = Faccionista.objects.prefetch_related('maquinas').all().order_by('tipo', 'nome')
  maquinas_disponiveis = Maquina.objects.all()

  total_faccionistas_externas = faccionistas.filter(tipo='faccionista').count()
  total_costureiras_internas = faccionistas.filter(tipo='costureira_interna').count()

  context = {
      'faccionistas': faccionistas,
      'maquinas_disponiveis': maquinas_disponiveis,
      'total_faccionistas_externas': total_faccionistas_externas,
      'total_costureiras_internas': total_costureiras_internas,
  }
  return render(request, 'fabrica/faccionistas.html', context)


@admin_required
def editar_faccionista(request, pk):
  faccionista = get_object_or_404(Faccionista, pk=pk)

  if request.method == 'POST':
    faccionista.tipo = request.POST.get('tipo', 'faccionista')
    faccionista.nome = (request.POST.get('nome') or '').strip()
    faccionista.telefone = request.POST.get('telefone')
    faccionista.cep = request.POST.get('cep')
    faccionista.endereco = request.POST.get('endereco')
    faccionista.ponto_referencia = request.POST.get('ponto_referencia')
    maquinas_ids = request.POST.getlist('maquinas')

    faccionista.save()
    faccionista.maquinas.set(maquinas_ids)
    messages.success(request, f'Cadastro de "{faccionista.nome}" atualizado com sucesso.')
    return redirect('faccionistas')

  maquinas_disponiveis = Maquina.objects.all()
  context = {
      'faccionista': faccionista,
      'maquinas_disponiveis': maquinas_disponiveis,
  }
  return render(request, 'fabrica/editar_faccionista.html', context)


@admin_required
def excluir_faccionista(request, pk):
  faccionista = get_object_or_404(Faccionista, pk=pk)
  faccionista.delete()
  return redirect('faccionistas')


@login_required(login_url='login')
def produtos_view(request):
  if request.method == 'POST':
    if not verificar_permissao_adm(request):
      return redirect('produtos')
    sku = request.POST.get('sku')
    nome = request.POST.get('nome')
    categoria_id = request.POST.get('categoria')
    descricao = request.POST.get('descricao')

    if sku and nome and categoria_id:
      categoria = get_object_or_404(Categoria, id=categoria_id)
      Produto.objects.create(
          sku=sku, nome=nome, categoria=categoria, descricao=descricao
      )
      return redirect('produtos')

  produtos = Produto.objects.select_related('categoria').prefetch_related('materias_primas_consumo').all()
  categorias = Categoria.objects.all()

  context = {
      'produtos': produtos,
      'categorias': categorias,
  }
  return render(request, 'fabrica/produtos.html', context)


@admin_required
def editar_produto(request, pk):
  produto = get_object_or_404(Produto, pk=pk)
  categorias = Categoria.objects.all()

  if request.method == 'POST':
    produto.sku = request.POST.get('sku')
    produto.nome = request.POST.get('nome')
    produto.categoria_id = request.POST.get('categoria')
    produto.descricao = request.POST.get('descricao')
    produto.save()
    return redirect('produtos')

  context = {'produto': produto, 'categorias': categorias}
  return render(request, 'fabrica/editar_produto.html', context)


@admin_required
def excluir_produto(request, pk):
  produto = get_object_or_404(Produto, pk=pk)
  produto.delete()
  return redirect('produtos')


@login_required(login_url='login')
def categorias_view(request):
  if request.method == 'POST':
    if not verificar_permissao_adm(request):
      return redirect('produtos')
    nome = request.POST.get('nome')
    if nome:
      Categoria.objects.get_or_create(nome=nome)
  return redirect('produtos')


@admin_required
def editar_categoria(request, pk):
  categoria = get_object_or_404(Categoria, pk=pk)
  if request.method == 'POST':
    novo_nome = request.POST.get('nome')
    if novo_nome:
      categoria.nome = novo_nome
      categoria.save()
      return redirect('produtos')
  return render(request, 'fabrica/editar_categoria.html', {'categoria': categoria})


@admin_required
def excluir_categoria(request, pk):
  get_object_or_404(Categoria, pk=pk).delete()
  return redirect('produtos')


@login_required(login_url='login')
def maquinas_view(request):
  if request.method == 'POST':
    if not verificar_permissao_adm(request):
      return redirect('maquinas')
    acao = request.POST.get('acao')
    if acao == 'sincronizar_estudo':
      espelhar_maquinas_do_estudo()
      messages.success(request, 'Máquinas sincronizadas com sucesso com o Estudo de Tempos!')
      return redirect('maquinas')
    nome_maquina = request.POST.get('nome')
    codigo_maquina = request.POST.get('codigo', '').strip().upper()
    if nome_maquina:
      nome_maquina = nome_maquina.strip()
      m, created = Maquina.objects.get_or_create(
          nome=nome_maquina, defaults={'codigo': codigo_maquina}
      )
      if not created and codigo_maquina:
        m.codigo = codigo_maquina
        m.save()
      messages.success(request, f'Máquina "{m.nome}" cadastrada/atualizada com sucesso!')
      return redirect('maquinas')

  maquinas = Maquina.objects.all().select_related('referencia_operacao').order_by('nome')
  if not maquinas.exists() and ReferenciaMaquinaOperacao.objects.filter(ativo=True).exists():
    espelhar_maquinas_do_estudo()
    maquinas = Maquina.objects.all().select_related('referencia_operacao').order_by('nome')

  return render(
      request, 'fabrica/maquinas.html', {'maquinas': maquinas}
  )


@admin_required
def excluir_maquina(request, pk):
  get_object_or_404(Maquina, pk=pk).delete()
  return redirect('maquinas')


@admin_required
def excluir_lote_corte(request, pk):
  lote = get_object_or_404(LoteCorte, pk=pk)
  codigo = lote.codigo_lote
  lote.delete()
  messages.success(request, f'Lote de corte {codigo} excluído com sucesso.')
  return redirect('lotes_corte')


@login_required(login_url='login')
def lotes_corte_view(request):
  if request.method == 'POST':
    if not verificar_permissao_adm(request):
      return redirect('lotes_corte')
    acao = request.POST.get('acao')

    if acao == 'criar':
      codigo_lote = (request.POST.get('codigo_lote') or '').strip()
      produto_id = request.POST.get('produto')
      cortador = request.POST.get('cortador')
      quantidade_tecido_metros = request.POST.get('quantidade_tecido_metros')
      data_envio_cortador = request.POST.get('data_envio_cortador')
      data_prevista_retorno = request.POST.get('data_prevista_retorno')
      valor_unitario_corte = request.POST.get('valor_unitario_corte') or 0.00
      observacoes = request.POST.get('observacoes')

      try:
        qtd_metros_dec = float(quantidade_tecido_metros or 0)
      except (ValueError, TypeError):
        qtd_metros_dec = 0.0

      if qtd_metros_dec <= 0:
        messages.error(request, 'A quantidade de tecido (metros) deve ser maior que zero.')
        return redirect('lotes_corte')

      if codigo_lote and produto_id:
        produto = get_object_or_404(Produto, id=produto_id)
        # Ao enviar tecido para o cortador, a quantidade de peças ainda é desconhecida (0).
        # As peças e a grade serão lançadas quando o corte estiver "Pronto / Aguardando Retirada".
        lote = LoteCorte.objects.create(
            codigo_lote=codigo_lote,
            produto=produto,
            cortador=cortador,
            quantidade_tecido_metros=qtd_metros_dec,
            quantidade_total_pecas=0,
            custo_total_corte=0.00,
            data_envio_cortador=data_envio_cortador or None,
            data_prevista_retorno=data_prevista_retorno or None,
            valor_unitario_corte=valor_unitario_corte,
            status='criado',
            observacoes=observacoes,
        )

        messages.success(
            request,
            f'Demanda de corte {codigo_lote} aberta com sucesso ({qtd_metros_dec} metros enviados). Quando o corte for finalizado pelo cortador, altere o status para "Pronto" para lançar a grade de peças.'
        )
        return redirect('lotes_corte')

    elif acao == 'atualizar_status_grade':
      lote_id = request.POST.get('lote_id')
      lote = get_object_or_404(LoteCorte, id=lote_id)

      lote.status = request.POST.get('status')
      lote.data_envio_cortador = request.POST.get('data_envio_cortador') or None
      lote.data_prevista_retorno = (
          request.POST.get('data_prevista_retorno') or None
      )
      lote.valor_unitario_corte = (
          request.POST.get('valor_unitario_corte') or 0.00
      )

      # A grade de cores e unidades só é acrescentada/atualizada quando o status for "pronto" ou "finalizado"
      if lote.status in ['pronto', 'finalizado']:
        cores = request.POST.getlist('cor[]')
        tamanhos = request.POST.getlist('tamanho[]')
        quantidades = request.POST.getlist('quantidade_pecas[]')

        total_pecas = 0
        novas_grades = []
        for cor, tamanho, qtd in zip(cores, tamanhos, quantidades):
          if cor and tamanho and qtd:
            try:
              qtd_int = int(qtd)
            except ValueError:
              qtd_int = 0
            if qtd_int > 0:
              novas_grades.append((cor, tamanho, qtd_int))
              total_pecas += qtd_int

        if total_pecas <= 0:
          messages.error(
              request,
              'Para definir o status como "Pronto / Aguardando Retirada" ou "Finalizado", lance as cores e quantidades de peças cortadas na grade.'
          )
          return redirect('lotes_corte')

        total_alocado = lote.quantidade_alocada()
        if total_pecas < total_alocado:
          messages.error(
              request,
              f'A soma da grade ({total_pecas} pçs) não pode ser inferior ao total já distribuído em sub-lotes ({total_alocado} pçs).'
          )
          return redirect('lotes_corte')

        lote.grades.all().delete()
        for cor, tamanho, qtd_int in novas_grades:
          ItemGradeCorte.objects.create(
              lote_corte=lote, cor=cor, tamanho=tamanho, quantidade=qtd_int
          )
        lote.quantidade_total_pecas = total_pecas
        lote.custo_total_corte = total_pecas * float(lote.valor_unitario_corte)
      else:
        # Em status criado ou enviado, caso já haja peças, mantém custo sincronizado
        lote.custo_total_corte = lote.quantidade_total_pecas * float(
            lote.valor_unitario_corte
        )

      lote.save()
      messages.success(
          request,
          f'Lote {lote.codigo_lote} atualizado com sucesso. Status: {lote.get_status_display()} ({lote.quantidade_total_pecas} peças cortadas).'
      )
      return redirect('lotes_corte')

  context = {
      'lotes': LoteCorte.objects.all().prefetch_related('grades').order_by('-id'),
      'produtos': Produto.objects.all(),
  }
  return render(request, 'fabrica/lotes_corte.html', context)


def gerar_proximo_codigo_sub_lote(lote_corte, destino):
  prefixo = 'FAC' if destino == 'faccionista' else 'FAB'
  codigo_lote = lote_corte.codigo_lote
  sub_lotes = lote_corte.sub_lotes.all()

  numeros_usados = []
  padrao = re.compile(rf'^(?:FAC|FAB)-{re.escape(codigo_lote)}-(\d+)$', re.IGNORECASE)
  for sub in sub_lotes:
    m = padrao.match(sub.codigo_sub_lote)
    if m:
      numeros_usados.append(int(m.group(1)))

  if numeros_usados:
    proximo_num = max(numeros_usados) + 1
  else:
    proximo_num = sub_lotes.count() + 1

  codigo = f'{prefixo}-{codigo_lote}-{proximo_num:02d}'
  while LoteProducao.objects.filter(codigo_sub_lote=codigo).exists():
    proximo_num += 1
    codigo = f'{prefixo}-{codigo_lote}-{proximo_num:02d}'

  return codigo


@login_required(login_url='login')
def producao_view(request):
  if request.method == 'POST':
    if not verificar_permissao_adm(request):
      return redirect('producao')
    acao = request.POST.get('acao')

    if acao == 'criar_sub_lote':
      codigo_sub_lote = (request.POST.get('codigo_sub_lote') or '').strip()
      lote_corte_id = request.POST.get('lote_corte')
      destino = request.POST.get('destino')
      faccionista_id = request.POST.get('faccionista')
      processo_faccionista = request.POST.get('processo_faccionista')
      data_envio = request.POST.get('data_envio')

      cores = request.POST.getlist('cor[]')
      tamanhos = request.POST.getlist('tamanho[]')
      quantidades = request.POST.getlist('quantidade_pecas[]')

      if lote_corte_id:
        lote_corte = get_object_or_404(LoteCorte, id=lote_corte_id)

        total_pecas = 0
        itens_para_criar = []
        for cor, tamanho, qtd in zip(cores, tamanhos, quantidades):
          if cor and tamanho and qtd:
            try:
              qtd_int = int(qtd)
            except ValueError:
              qtd_int = 0
            if qtd_int > 0:
              itens_para_criar.append((cor, tamanho, qtd_int))
              total_pecas += qtd_int

        if total_pecas <= 0:
          messages.error(request, 'A quantidade de peças do sub-lote deve ser maior que zero.')
          return redirect('producao')

        # Validação de Saldo: Se existem 100 unidades, só posso distribuir 100 unidades em sub lotes
        saldo_disponivel = lote_corte.quantidade_disponivel()
        if total_pecas > saldo_disponivel:
          messages.error(
              request,
              f'Não é possível distribuir {total_pecas} peças. O saldo disponível do lote {lote_corte.codigo_lote} é de apenas {saldo_disponivel} peças (não pode ficar negativo).'
          )
          return redirect('producao')

        # Se não informou código ou se já existir, gera automaticamente com prefixo FAC/FAB e sequencial do lote
        if not codigo_sub_lote or LoteProducao.objects.filter(codigo_sub_lote=codigo_sub_lote).exists():
          codigo_sub_lote = gerar_proximo_codigo_sub_lote(lote_corte, destino)

        faccionista = None
        status_prod = 'fabrica_interna'

        if destino == 'faccionista':
          if faccionista_id:
            faccionista = get_object_or_404(Faccionista, id=faccionista_id)
          status_prod = 'enviado_faccionista'
        elif destino == 'fabrica_interna':
          costureira_id = request.POST.get('costureira_interna')
          if costureira_id:
            faccionista = get_object_or_404(Faccionista, id=costureira_id)
          status_prod = 'fabrica_interna'

        sub_lote = LoteProducao.objects.create(
            codigo_sub_lote=codigo_sub_lote,
            lote_corte=lote_corte,
            faccionista=faccionista,
            processo_faccionista=processo_faccionista,
            status=status_prod,
            data_envio=data_envio or None,
            quantidade_enviada=total_pecas,
            quantidade_real_costurada=total_pecas,
            quantidade=total_pecas,
        )

        for cor, tamanho, qtd_int in itens_para_criar:
          ItemGradeProducao.objects.create(
              lote_producao=sub_lote, cor=cor, tamanho=tamanho, quantidade=qtd_int
          )

        messages.success(
            request,
            f'Sub-lote {codigo_sub_lote} distribuído com sucesso ({total_pecas} peças). Saldo restante do corte: {lote_corte.quantidade_disponivel()} peças.'
        )
        return redirect('producao')

    elif acao == 'editar_sub_lote':
      sub_lote_id = request.POST.get('sub_lote_id')
      sub_lote = get_object_or_404(LoteProducao, id=sub_lote_id)

      sub_lote.status = request.POST.get('status')
      sub_lote.processo_faccionista = request.POST.get('processo_faccionista')
      sub_lote.data_envio = request.POST.get('data_envio') or None
      sub_lote.data_retorno = request.POST.get('data_retorno') or None

      qtd_real = request.POST.get('quantidade_real_costurada')
      if qtd_real:
        try:
          nova_qtd = int(qtd_real)
        except ValueError:
          nova_qtd = sub_lote.quantidade_real_costurada

        if nova_qtd <= 0:
          messages.error(request, 'A quantidade do sub-lote deve ser maior que zero.')
          return redirect('producao')

        saldo_maximo = sub_lote.lote_corte.quantidade_disponivel() + sub_lote.quantidade
        if nova_qtd > saldo_maximo:
          messages.error(
              request,
              f'Quantidade informada ({nova_qtd} pçs) excede o saldo disponível do lote de corte ({saldo_maximo} pçs).'
          )
          return redirect('producao')

        sub_lote.quantidade_real_costurada = nova_qtd
        sub_lote.quantidade = nova_qtd

      sub_lote.valor_unitario_costura = (
          request.POST.get('valor_unitario_costura') or 0.00
      )
      sub_lote.pago_costura = (
          True if request.POST.get('pago_costura') == 'on' else False
      )

      sub_lote.custo_total_costura = sub_lote.quantidade * float(
          sub_lote.valor_unitario_costura
      )
      sub_lote.save()
      messages.success(request, f'Sub-lote {sub_lote.codigo_sub_lote} atualizado com sucesso.')
      return redirect('producao')

  # Todos os lotes de corte para seleção (identificando os lotes criados e em aberto)
  todos_lotes_corte = (
      LoteCorte.objects.select_related('produto', 'produto__categoria')
      .prefetch_related('grades', 'sub_lotes')
      .order_by('-id')
  )

  lotes_info = {}
  for lc in todos_lotes_corte:
    grades_list = [
        {'cor': g.cor, 'tamanho': g.tamanho, 'quantidade': g.quantidade}
        for g in lc.grades.all()
    ]
    lotes_info[str(lc.id)] = {
        'id': lc.id,
        'codigo': lc.codigo_lote,
        'produto_sku': lc.produto.sku,
        'produto_nome': lc.produto.nome,
        'status_display': lc.get_status_display(),
        'quantidade_total': lc.quantidade_total_pecas,
        'quantidade_disponivel': lc.quantidade_disponivel(),
        'proximo_fac': gerar_proximo_codigo_sub_lote(lc, 'faccionista'),
        'proximo_fab': gerar_proximo_codigo_sub_lote(lc, 'fabrica_interna'),
        'grades': grades_list,
    }

  context = {
      'lotes_producao': (
          LoteProducao.objects.select_related(
              'lote_corte__produto', 'faccionista'
          )
          .prefetch_related('grades')
          .order_by('-id')
      ),
      'lotes_corte_abertos': todos_lotes_corte,
      'lotes_corte_finalizados': todos_lotes_corte,
      'lotes_info_json': json.dumps(lotes_info),
      'faccionistas': Faccionista.objects.filter(ativo=True, tipo='faccionista'),
      'costureiras_internas': Faccionista.objects.filter(ativo=True, tipo='costureira_interna'),
  }
  return render(request, 'fabrica/producao.html', context)


@login_required(login_url='login')
def financeiro_view(request):
  if request.method == 'POST':
    if not verificar_permissao_adm(request):
      return redirect('financeiro')
    tipo = request.POST.get('tipo')
    registro_id = request.POST.get('registro_id')

    if tipo == 'corte':
      lote = get_object_or_404(LoteCorte, id=registro_id)
      lote.valor_unitario_corte = (
          request.POST.get('valor_unitario_corte') or 0.00
      )
      lote.pago_cortador = (
          True if request.POST.get('pago_cortador') == 'on' else False
      )
      lote.data_pagamento_cortador = (
          request.POST.get('data_pagamento_cortador') or None
      )
      lote.custo_total_corte = lote.quantidade_total_pecas * float(
          lote.valor_unitario_corte
      )
      lote.save()

    elif tipo == 'producao':
      sub = get_object_or_404(LoteProducao, id=registro_id)
      sub.valor_unitario_costura = (
          request.POST.get('valor_unitario_costura') or 0.00
      )
      sub.pago_costura = (
          True if request.POST.get('pago_costura') == 'on' else False
      )
      sub.data_pagamento_costura = (
          request.POST.get('data_pagamento_costura') or None
      )
      sub.custo_total_costura = sub.quantidade * float(
          sub.valor_unitario_costura
      )
      sub.save()

    return redirect('financeiro')

  lotes_corte = list(
      LoteCorte.objects.select_related('produto').all().order_by('-id')
  )
  lotes_producao = list(
      LoteProducao.objects.select_related(
          'lote_corte__produto', 'faccionista'
      )
      .all()
      .order_by('-id')
  )

  total_corte = sum(c.custo_total_corte for c in lotes_corte)
  total_costura = sum(p.custo_total_costura for p in lotes_producao)
  total_geral = total_corte + total_costura
  total_pago = sum(
      c.custo_total_corte for c in lotes_corte if c.pago_cortador
  ) + sum(p.custo_total_costura for p in lotes_producao if p.pago_costura)
  total_pendente = total_geral - total_pago

  context = {
      'lotes_corte': lotes_corte,
      'lotes_producao': lotes_producao,
      'total_corte': total_corte,
      'total_costura': total_costura,
      'total_geral': total_geral,
      'total_pago': total_pago,
      'total_pendente': total_pendente,
  }
  return render(request, 'fabrica/financeiro.html', context)

@login_required(login_url='login')
def relatorio_faccionista_view(request, pk):
  sub_lote = get_object_or_404(
      LoteProducao.objects.select_related(
          'lote_corte__produto', 'faccionista'
      ).prefetch_related('grades'),
      pk=pk,
  )

  context = {
      'sub_lote': sub_lote,
  }
  return render(request, 'fabrica/relatorio_faccionista.html', context)



@login_required(login_url='login')
def detalhe_produto_view(request, pk):
  produto = get_object_or_404(
      Produto.objects.select_related('categoria').prefetch_related(
          'materias_primas_consumo', 'medidas', 'operacoes'
      ),
      pk=pk,
  )
  materias_primas = produto.materias_primas_consumo.all()
  medidas = produto.medidas.all()
  operacoes = produto.operacoes.all().order_by('ordem', 'id')
  total_custo_materia_prima = produto.custo_materia_prima_total()
  
  # Engenharia e Tempo Padrão
  tempo_padrao_total = produto.tempo_padrao_total_min()
  tempo_padrao_pcte_total = produto.tempo_padrao_pcte_total_min()
  pecas_por_hora = produto.pecas_por_hora()
  pecas_por_dia = produto.pecas_por_dia()
  distribuicao_maquinas = produto.distribuicao_maquinas()
  
  config_eng = ConfiguracaoEngenharia.objects.first()
  custo_minuto = float(config_eng.custo_minuto_costura if config_eng else 0.35)
  custo_mao_de_obra = round(tempo_padrao_total * custo_minuto, 2)
  custo_producao_total = round(float(total_custo_materia_prima or 0) + custo_mao_de_obra, 2)

  context = {
      'produto': produto,
      'materias_primas': materias_primas,
      'medidas': medidas,
      'operacoes': operacoes,
      'total_custo_materia_prima': total_custo_materia_prima,
      'tempo_padrao_total': tempo_padrao_total,
      'tempo_padrao_pcte_total': tempo_padrao_pcte_total,
      'pecas_por_hora': pecas_por_hora,
      'pecas_por_dia': pecas_por_dia,
      'distribuicao_maquinas': distribuicao_maquinas,
      'config_eng': config_eng,
      'custo_minuto': custo_minuto,
      'custo_mao_de_obra': custo_mao_de_obra,
      'custo_producao_total': custo_producao_total,
      'materias_primas_disponiveis': MateriaPrima.objects.filter(ativo=True).order_by('codigo', 'nome'),
  }
  return render(request, 'fabrica/detalhe_produto.html', context)


@admin_required
def adicionar_insumo_produto(request, pk):
  produto = get_object_or_404(Produto, pk=pk)
  if request.method == 'POST':
    materia_prima_id = request.POST.get('materia_prima_id')
    nome = (request.POST.get('materia_prima_nome') or '').strip()
    quantidade_str = request.POST.get('quantidade_consumo', '0').replace(',', '.')
    unidade = request.POST.get('unidade_medida') or 'UN'
    custo_str = request.POST.get('custo_unitario', '0').replace(',', '.')

    try:
      quantidade = float(quantidade_str or 0)
    except ValueError:
      quantidade = 0.0

    try:
      custo = float(custo_str or 0)
    except ValueError:
      custo = 0.0

    mp = None
    if materia_prima_id:
      mp = MateriaPrima.objects.filter(pk=materia_prima_id).first()
      if mp:
        nome = mp.nome
        unidade = mp.unidade_medida
        if custo <= 0:
          custo = float(mp.preco_unitario)
    elif nome:
      mp = MateriaPrima.objects.filter(nome__iexact=nome).first()
      if mp and custo <= 0:
        custo = float(mp.preco_unitario)
        unidade = mp.unidade_medida

    if (nome or mp) and quantidade > 0:
      ItemConsumoMateriaPrima.objects.create(
          produto=produto,
          materia_prima=mp,
          materia_prima_nome=nome or (mp.nome if mp else ''),
          quantidade_consumo=quantidade,
          unidade_medida=unidade,
          custo_unitario=custo,
      )
      messages.success(request, f'Insumo "{nome}" adicionado com sucesso!')
  return redirect('detalhe_produto', pk=pk)


@admin_required
def excluir_insumo_produto(request, pk):
  insumo = get_object_or_404(ItemConsumoMateriaPrima, pk=pk)
  produto_id = insumo.produto_id
  insumo.delete()
  return redirect('detalhe_produto', pk=produto_id)


@admin_required
def adicionar_medida_produto(request, pk):
  produto = get_object_or_404(Produto, pk=pk)
  if request.method == 'POST':
    tamanho = request.POST.get('tamanho')
    parte_peca = request.POST.get('parte_peca')
    medida_cm = request.POST.get('medida_cm')
    tolerancia = request.POST.get('tolerancia') or '+/- 1.0 cm'

    if tamanho and parte_peca and medida_cm:
      MedidaProduto.objects.create(
          produto=produto,
          tamanho=tamanho,
          parte_peca=parte_peca,
          medida_cm=medida_cm,
          tolerancia=tolerancia,
      )
  return redirect('detalhe_produto', pk=pk)


@admin_required
def excluir_medida_produto(request, pk):
  medida = get_object_or_404(MedidaProduto, pk=pk)
  produto_id = medida.produto_id
  medida.delete()
  return redirect('detalhe_produto', pk=produto_id)


@admin_required
def atualizar_ficha_produto(request, pk):
  produto = get_object_or_404(Produto, pk=pk)
  if request.method == 'POST':
    produto.composicao = request.POST.get('composicao')
    produto.ficha_tecnica = request.POST.get('ficha_tecnica')
    produto.observacoes_medidas = request.POST.get('observacoes_medidas')
    produto.save()
  return redirect('detalhe_produto', pk=pk)



@login_required(login_url='login')
def marketplace_dashboard_view(request):
  canal_filter = request.GET.get('canal', 'todos')
  periodo_filter = request.GET.get('periodo', 'todos')
  produto_id = request.GET.get('produto', '')
  search = request.GET.get('q', '').strip()

  vendas_qs = (
      VendaMarketplace.objects.select_related(
          'produto', 'conta', 'campanha_ads'
      )
      .all()
  )

  # Filtro por canal
  if canal_filter and canal_filter != 'todos':
    vendas_qs = vendas_qs.filter(canal=canal_filter)

  # Filtro por produto
  if produto_id:
    vendas_qs = vendas_qs.filter(produto_id=produto_id)

  # Filtro de busca
  if search:
    vendas_qs = vendas_qs.filter(
        Q(codigo_pedido__icontains=search)
        | Q(numero_pedido__icontains=search)
        | Q(nome_produto_marketplace__icontains=search)
        | Q(comprador__icontains=search)
        | Q(produto__nome__icontains=search)
        | Q(produto__sku__icontains=search)
    )

  # Filtro por período
  hoje = timezone.now()
  if periodo_filter == '7d':
    vendas_qs = vendas_qs.filter(data_venda__gte=hoje - timedelta(days=7))
  elif periodo_filter == '30d':
    vendas_qs = vendas_qs.filter(data_venda__gte=hoje - timedelta(days=30))
  elif periodo_filter == '90d':
    vendas_qs = vendas_qs.filter(data_venda__gte=hoje - timedelta(days=90))
  elif periodo_filter == 'mes':
    vendas_qs = vendas_qs.filter(
        data_venda__year=hoje.year, data_venda__month=hoje.month
    )

  vendas = list(vendas_qs.order_by('-data_venda', '-codigo_pedido', '-id'))

  # Indicadores Consolidados
  total_faturamento = sum(float(v.valor_bruto_venda or 0) for v in vendas)
  total_cpv = sum(float(v.custo_produto_total or 0) for v in vendas)
  total_taxas = sum(
      float(v.taxa_comissao_marketplace or 0)
      + float(v.taxa_servico_marketplace or 0)
      + float(v.taxa_devolucao_facil or 0)
      + float(v.taxa_afiliados or 0)
      + float(v.taxa_transacao or 0)
      + float(v.taxa_fixa_marketplace or 0)
      for v in vendas
  )
  total_valor_liquido = sum(float(v.valor_liquido_liberado or 0) for v in vendas)
  total_ads = sum(float(v.custo_ads_atribuido or 0) for v in vendas)
  total_prejuizo_ads_cancelados = sum(float(v.custo_ads_pedido_perdido or 0) for v in vendas if v.status == 'cancelado')
  total_cancelados = sum(1 for v in vendas if v.status == 'cancelado')
  total_impostos = sum(float(v.imposto_estimado or 0) for v in vendas)
  total_lucro_liquido = sum(float(v.lucro_liquido or 0) for v in vendas)
  total_pedidos = len(vendas)

  ticket_medio = (total_faturamento / total_pedidos) if total_pedidos > 0 else 0.0
  margem_liquida_consolidada = (
      (total_lucro_liquido / total_faturamento * 100.0)
      if total_faturamento > 0
      else 0.0
  )
  roas_consolidado = (
      (total_faturamento / total_ads) if total_ads > 0 else 0.0
  )

  # Estatísticas por Canal para Gráficos
  canais_stats = {
      'shopee': {
          'nome': 'Shopee',
          'faturamento': 0.0,
          'lucro': 0.0,
          'taxas': 0.0,
          'ads': 0.0,
          'pedidos': 0,
          'cor': '#EE4D2D',
      },
      'mercadolivre': {
          'nome': 'Mercado Livre',
          'faturamento': 0.0,
          'lucro': 0.0,
          'taxas': 0.0,
          'ads': 0.0,
          'pedidos': 0,
          'cor': '#2968C8',
      },
      'tiktok': {
          'nome': 'TikTok Shop',
          'faturamento': 0.0,
          'lucro': 0.0,
          'taxas': 0.0,
          'ads': 0.0,
          'pedidos': 0,
          'cor': '#000000',
      },
  }

  for v in vendas:
    c = v.canal
    if c in canais_stats:
      canais_stats[c]['faturamento'] += float(v.valor_bruto_venda or 0)
      canais_stats[c]['lucro'] += float(v.lucro_liquido or 0)
      canais_stats[c]['taxas'] += float(
          (v.taxa_comissao_marketplace or 0)
          + (v.taxa_servico_marketplace or 0)
          + (v.taxa_devolucao_facil or 0)
          + (v.taxa_afiliados or 0)
          + (v.taxa_transacao or 0)
          + (v.taxa_fixa_marketplace or 0)
      )
      canais_stats[c]['ads'] += float(v.custo_ads_atribuido or 0)
      canais_stats[c]['pedidos'] += 1

  for c_key, stat in canais_stats.items():
    if stat['faturamento'] > 0:
      stat['margem'] = round(
          (stat['lucro'] / stat['faturamento']) * 100.0, 1
      )
    else:
      stat['margem'] = 0.0

  # Paginação do extrato de vendas (20 vendas por página para evitar scroll infinito)
  page_number = request.GET.get('page', 1)
  paginator = Paginator(vendas, 20)
  try:
    vendas_paginadas = paginator.page(page_number)
  except PageNotAnInteger:
    vendas_paginadas = paginator.page(1)
  except EmptyPage:
    vendas_paginadas = paginator.page(paginator.num_pages)

  campanhas = CampanhaAds.objects.select_related('produto').order_by('-id')
  contas = ContaMarketplace.objects.all()
  produtos = Produto.objects.all()
  importacoes = ImportacaoPlanilhaMarketplace.objects.select_related('conta', 'usuario').order_by('-data_importacao')[:20]

  context = {
      'vendas': vendas_paginadas,
      'total_vendas_geral': total_pedidos,
      'total_pedidos': total_pedidos,
      'total_faturamento': total_faturamento,
      'total_cpv': total_cpv,
      'total_taxas': total_taxas,
      'total_valor_liquido': total_valor_liquido,
      'total_ads': total_ads,
      'total_prejuizo_ads_cancelados': total_prejuizo_ads_cancelados,
      'total_cancelados': total_cancelados,
      'total_impostos': total_impostos,
      'total_lucro_liquido': total_lucro_liquido,
      'margem_liquida_consolidada': margem_liquida_consolidada,
      'ticket_medio': ticket_medio,
      'roas_consolidado': roas_consolidado,
      'canais_stats': canais_stats,
      'campanhas': campanhas,
      'contas': contas,
      'produtos': produtos,
      'importacoes': importacoes,
      'canal_filter': canal_filter,
      'periodo_filter': periodo_filter,
      'produto_id': produto_id,
      'search': search,
  }
  return render(request, 'fabrica/marketplace.html', context)


@admin_required
def importar_planilha_marketplace_view(request):
  if request.method == 'POST':
    canal = request.POST.get('canal', 'shopee')
    arquivo = request.FILES.get('arquivo_planilha')
    if not arquivo:
      messages.error(request, 'Por favor, selecione um arquivo de planilha (.xlsx ou .csv) para importar.')
      return redirect('marketplace_dashboard')

    dir_upload = os.path.join(settings.BASE_DIR, 'fabrica', 'planilhas_marketplace')
    os.makedirs(dir_upload, exist_ok=True)
    timestamp_str = str(int(timezone.now().timestamp()))
    nome_limpo = re.sub(r'[^a-zA-Z0-9_.-]', '_', arquivo.name)
    nome_salvo = f"{canal}_{timestamp_str}_{nome_limpo}"
    caminho_salvo = os.path.join(dir_upload, nome_salvo)

    with open(caminho_salvo, 'wb+') as destino:
      for chunk in arquivo.chunks():
        destino.write(chunk)

    try:
      # Detecção inteligente do formato da planilha (Shopee ou TikTok Shop)
      tipo_detectado = detectar_tipo_planilha_marketplace(caminho_salvo, canal_default=canal)
      canal_usado = tipo_detectado if tipo_detectado in ['shopee', 'tiktok'] else canal

      if canal_usado == 'tiktok':
        res = importar_planilha_tiktok(caminho_salvo, usuario=request.user, nome_original=arquivo.name, canal='tiktok')
        canal_label = 'TikTok Shop'
      else:
        res = importar_planilha_shopee(caminho_salvo, usuario=request.user, nome_original=arquivo.name, canal=canal_usado)
        canal_label = 'Shopee' if canal_usado == 'shopee' else 'Mercado Livre'

      messages.success(
          request,
          f"Planilha de Faturamento ({canal_label}) importada com sucesso! "
          f"{res['total_novos']} novos pedidos incluídos no faturamento. "
          f"{res['total_duplicados']} pedidos duplicados foram desconsiderados. "
          f"Faturamento Bruto: R$ {res['receita_bruta']:.2f} | "
          f"Taxas Retidas: R$ {res['taxas_total']:.2f} | "
          f"Líquido Liberado: R$ {res['valor_liquido']:.2f} | "
          f"Lucro Líquido Real Calculado: R$ {res['lucro_liquido']:.2f}"
      )
    except Exception as e:
      messages.error(request, f"Erro ao processar a planilha: {str(e)}")

    return redirect(f"{reverse('marketplace_dashboard')}?canal={canal_usado}&periodo=todos")
  return redirect('marketplace_dashboard')


@admin_required
def importar_planilha_ads_view(request):
  if request.method == 'POST':
    canal = request.POST.get('canal', 'shopee')
    arquivo = request.FILES.get('arquivo_ads')
    if not arquivo:
      messages.error(request, 'Por favor, selecione um arquivo de relatório de Ads (.csv).')
      return redirect('marketplace_dashboard')

    dir_upload = os.path.join(settings.BASE_DIR, 'fabrica', 'planilhas_marketplace')
    os.makedirs(dir_upload, exist_ok=True)
    timestamp_str = str(int(timezone.now().timestamp()))
    nome_limpo = re.sub(r'[^a-zA-Z0-9_.-]', '_', arquivo.name)
    nome_salvo = f"ads_{canal}_{timestamp_str}_{nome_limpo}"
    caminho_salvo = os.path.join(dir_upload, nome_salvo)

    with open(caminho_salvo, 'wb+') as destino:
      for chunk in arquivo.chunks():
        destino.write(chunk)

    try:
      # Auto-detecta se o arquivo é do TikTok Ads ou Shopee Ads
      is_tiktok_ads = (canal == 'tiktok')
      if not is_tiktok_ads:
        try:
          ext_ads = os.path.splitext(caminho_salvo)[1].lower()
          if ext_ads in ['.xlsx', '.xlsm', '.xls']:
            import openpyxl
            wb_check = openpyxl.load_workbook(caminho_salvo, data_only=True)
            ws_check = wb_check.active
            first_rows_text = " ".join([str(ws_check.cell(r, c).value or '') for r in range(1, 6) for c in range(1, 10)]).lower()
            wb_check.close()
            if 'pedidos de sku' in first_rows_text or 'roi (loja atual)' in first_rows_text or 'custo por pedido' in first_rows_text:
              is_tiktok_ads = True
          else:
            with open(caminho_salvo, 'r', encoding='utf-8', errors='ignore') as f:
              first_lines = "".join([f.readline() for _ in range(5)]).lower()
              if 'pedidos de sku' in first_lines or 'roi (loja atual)' in first_lines or 'custo por pedido' in first_lines:
                is_tiktok_ads = True
        except Exception:
          pass

      if is_tiktok_ads:
        from .ads_importer import importar_planilha_ads_tiktok
        res = importar_planilha_ads_tiktok(caminho_salvo, canal='tiktok')
        canal_label = 'TikTok Ads'
      else:
        from .ads_importer import importar_planilha_ads_shopee
        res = importar_planilha_ads_shopee(caminho_salvo, canal=canal)
        canal_label = 'Shopee Ads'

      messages.success(
          request,
          f"Relatório de Ads ({canal_label}) importado com sucesso! "
          f"{res['campanhas_processadas']} campanhas processadas | "
          f"Total Investido: R$ {res['despesas_total']:.2f} | "
          f"Receita Atribuída (GMV): R$ {res['gmv_total']:.2f} | "
          f"ROAS Médio: {res['roas_medio']:.2f}x | "
          f"CAC Médio: R$ {res['cac_medio']:.2f} / venda | "
          f"{res['pedidos_perdidos_cac_count']} cancelamentos identificados (Prejuízo de CAC em Vendas Canceladas: R$ {res['prejuizo_cac_cancelados_total']:.2f})."
      )
    except Exception as e:
      messages.error(request, f"Erro ao processar o relatório de Ads: {str(e)}")

    return redirect('marketplace_dashboard')
  return redirect('marketplace_dashboard')


@login_required(login_url='login')
def produtos_marketplace_view(request):
  canal_filter = request.GET.get('canal', 'todos')
  search = request.GET.get('q', '').strip()

  produtos_qs = (
      ProdutoMarketplace.objects.select_related('produto_fabrica')
      .prefetch_related('historico_custos')
      .all()
  )

  if canal_filter and canal_filter != 'todos':
    produtos_qs = produtos_qs.filter(canal=canal_filter)

  if search:
    produtos_qs = produtos_qs.filter(
        Q(sku_marketplace__icontains=search)
        | Q(nome_marketplace__icontains=search)
        | Q(id_produto_canal__icontains=search)
        | Q(produto_fabrica__nome__icontains=search)
        | Q(produto_fabrica__sku__icontains=search)
    )

  produtos_mkt = list(produtos_qs)

  from django.db.models import Count, Sum
  stats_vendas = {
      item['produto_marketplace_id']: item
      for item in VendaMarketplace.objects.filter(produto_marketplace__isnull=False)
      .values('produto_marketplace_id')
      .annotate(qtd_vendas=Count('id'), total_gmv=Sum('valor_bruto_venda'))
  }

  for p in produtos_mkt:
    st = stats_vendas.get(p.id, {'qtd_vendas': 0, 'total_gmv': 0.0})
    p.total_vendas_count = st['qtd_vendas']
    p.total_gmv_acumulado = float(st['total_gmv'] or 0.0)
    p.ultimo_historico = p.historico_custos.first()

  produtos_fabrica = Produto.objects.filter(status='linha').order_by('nome')

  context = {
      'produtos_mkt': produtos_mkt,
      'produtos_fabrica': produtos_fabrica,
      'canal_filter': canal_filter,
      'search': search,
      'total_produtos': len(produtos_mkt),
  }
  return render(request, 'fabrica/produtos_marketplace.html', context)


@login_required(login_url='login')
def desempenho_produtos_marketplace_view(request):
  """Painel de Análise Estratégica e Desempenho por Produto do Marketplace"""
  canal_filter = request.GET.get('canal', 'todos')
  status_filter = request.GET.get('status', 'todos')
  search = request.GET.get('q', '').strip()
  periodo_dias = request.GET.get('periodo', 'todos')

  produtos_qs = (
      ProdutoMarketplace.objects.select_related('produto_fabrica')
      .prefetch_related('historico_custos')
      .all()
  )

  if canal_filter and canal_filter != 'todos':
    produtos_qs = produtos_qs.filter(canal=canal_filter)

  if search:
    produtos_qs = produtos_qs.filter(
        Q(sku_marketplace__icontains=search)
        | Q(nome_marketplace__icontains=search)
        | Q(produto_fabrica__nome__icontains=search)
        | Q(produto_fabrica__sku__icontains=search)
    )

  data_limite = None
  if periodo_dias.isdigit():
    data_limite = timezone.now() - timedelta(days=int(periodo_dias))

  produtos_data = []

  total_lucrativos = 0
  lucro_lucrativos = 0.0
  total_equilibrio = 0
  gmv_equilibrio = 0.0
  total_prejuizo = 0
  prejuizo_acumulado = 0.0
  total_cancelados_ads_prejuizo = 0.0

  gmv_geral = 0.0
  lucro_geral = 0.0
  vendas_geral = 0

  for p in produtos_qs:
    vendas_p = VendaMarketplace.objects.filter(produto_marketplace=p)
    if data_limite:
      vendas_p = vendas_p.filter(data_venda__gte=data_limite)

    qtd_vendas = vendas_p.count()
    if qtd_vendas == 0:
      p_data = {
          'produto': p,
          'qtd_vendas': 0,
          'qtd_cancelados': 0,
          'total_gmv': 0.0,
          'total_liquido': 0.0,
          'total_cpv': 0.0,
          'total_taxas': 0.0,
          'total_ads': 0.0,
          'total_ads_perdido': 0.0,
          'lucro_liquido': 0.0,
          'margem_liquida_pct': 0.0,
          'ticket_medio': 0.0,
          'status_class': 'sem_vendas',
          'status_label': 'Sem Vendas no Período',
          'status_badge_class': 'badge-secondary',
          'recomendacao': 'Produto cadastrado sem histórico de vendas recente. Avaliar lançamento e fotos do anúncio.',
      }
      if status_filter in ['todos', 'sem_vendas']:
        produtos_data.append(p_data)
      continue

    aggr = vendas_p.aggregate(
        gmv=Sum('valor_bruto_venda'),
        liquido=Sum('valor_liquido_liberado'),
        cpv=Sum('custo_produto_total'),
        comissao=Sum('taxa_comissao_marketplace'),
        servico=Sum('taxa_servico_marketplace'),
        devolucao=Sum('taxa_devolucao_facil'),
        afiliados=Sum('taxa_afiliados'),
        transacao=Sum('taxa_transacao'),
        taxa_fixa=Sum('taxa_fixa_marketplace'),
        ads=Sum('custo_ads_atribuido'),
        ads_perdido=Sum('custo_ads_pedido_perdido'),
        lucro=Sum('lucro_liquido')
    )

    gmv = float(aggr['gmv'] or 0.0)
    liquido = float(aggr['liquido'] or 0.0)
    cpv = float(aggr['cpv'] or 0.0)
    lucro = float(aggr['lucro'] or 0.0)
    ads = float(aggr['ads'] or 0.0)
    ads_perdido = float(aggr['ads_perdido'] or 0.0)
    taxas = (
        float(aggr['comissao'] or 0.0)
        + float(aggr['servico'] or 0.0)
        + float(aggr['devolucao'] or 0.0)
        + float(aggr['afiliados'] or 0.0)
        + float(aggr['transacao'] or 0.0)
        + float(aggr['taxa_fixa'] or 0.0)
    )

    margem = (lucro / gmv * 100.0) if gmv > 0 else 0.0
    ticket = (gmv / qtd_vendas) if qtd_vendas > 0 else 0.0
    qtd_canc = vendas_p.filter(status='cancelado').count()

    gmv_geral += gmv
    lucro_geral += lucro
    vendas_geral += qtd_vendas
    total_cancelados_ads_prejuizo += ads_perdido

    # Classificação Estratégica:
    if margem >= 5.0 and lucro > 0:
      status_class = 'lucrativo'
      status_label = 'Lucrativo'
      status_badge_class = 'badge-success'
      total_lucrativos += 1
      lucro_lucrativos += lucro
      if margem >= 15.0:
        recomendacao = f"👑 Campeão de Lucro: Margem saudável de {margem:.1f}%. Ação: Escalar tráfego (Ads) e manter estoque prioritário da fábrica."
      else:
        recomendacao = f"✅ Lucrativo: Margem de {margem:.1f}%. Ação: Estimular variações de kits (3 e 5 peças) para diluir a taxa fixa da Shopee (R$ 4,50)."
    elif margem >= 0.0 and lucro >= 0:
      status_class = 'equilibrio'
      status_label = 'Ponto de Equilíbrio / Alerta'
      status_badge_class = 'badge-warning'
      total_equilibrio += 1
      gmv_equilibrio += gmv
      recomendacao = f"⚠️ Ponto de Equilíbrio (Sem Lucro): Faturou R$ {gmv:.2f} com {qtd_vendas} vendas, mas o lucro foi de apenas R$ {lucro:.2f} ({margem:.1f}%). Ação: Subir preço em R$ 2,00 a R$ 3,50 ou cortar cupons de loja para converter esse volume em lucro."
    else:
      status_class = 'prejuizo'
      status_label = 'Prejuízo / Negativo'
      status_badge_class = 'badge-danger'
      total_prejuizo += 1
      prejuizo_acumulado += abs(lucro)
      recomendacao = f"🚨 Prejuízo Ativo: Cada venda consome caixa (prejuízo acumulado de -R$ {abs(lucro):.2f}). Ação: Reajustar preço imediatamente, pausar Ads com CAC alto ou renegociar matéria-prima."

    if ads_perdido > 0:
      recomendacao += f" (Atenção: R$ {ads_perdido:.2f} perdidos em CAC de pedidos cancelados)."

    p_data = {
        'produto': p,
        'qtd_vendas': qtd_vendas,
        'qtd_cancelados': qtd_canc,
        'total_gmv': gmv,
        'total_liquido': liquido,
        'total_cpv': cpv,
        'total_taxas': taxas,
        'total_ads': ads,
        'total_ads_perdido': ads_perdido,
        'lucro_liquido': lucro,
        'margem_liquida_pct': margem,
        'ticket_medio': ticket,
        'status_class': status_class,
        'status_label': status_label,
        'status_badge_class': status_badge_class,
        'recomendacao': recomendacao,
    }

    if status_filter == 'todos' or status_filter == status_class:
      produtos_data.append(p_data)

  # Ordena: Maiores lucros primeiro, seguidos por equilíbrio e maiores prejuízos
  produtos_data.sort(key=lambda x: x['lucro_liquido'], reverse=True)

  total_ativos = total_lucrativos + total_equilibrio + total_prejuizo
  taxa_lucratividade = (total_lucrativos / total_ativos * 100.0) if total_ativos > 0 else 0.0
  margem_media_geral = (lucro_geral / gmv_geral * 100.0) if gmv_geral > 0 else 0.0

  # Dados para o Gráfico de Lucro Líquido
  chart_labels = []
  chart_lucros = []
  chart_colors = []
  chart_borders = []
  for item in sorted(produtos_data, key=lambda x: x['lucro_liquido'], reverse=True):
    if item['qtd_vendas'] > 0:
      sku_curto = item['produto'].sku_marketplace or 'Sem SKU'
      nome_curto = item['produto'].nome_marketplace[:22]
      chart_labels.append(f"{sku_curto} ({nome_curto})")
      chart_lucros.append(round(item['lucro_liquido'], 2))
      if item['lucro_liquido'] > 0:
        chart_colors.append('#1E6E3C')
        chart_borders.append('#14532D')
      elif item['lucro_liquido'] == 0:
        chart_colors.append('#D9822B')
        chart_borders.append('#B26A1B')
      else:
        chart_colors.append('#A32832')
        chart_borders.append('#7F1D1D')

  import json
  context = {
      'produtos_data': produtos_data,
      'canal_filter': canal_filter,
      'status_filter': status_filter,
      'periodo_dias': periodo_dias,
      'search': search,
      'total_lucrativos': total_lucrativos,
      'lucro_lucrativos': lucro_lucrativos,
      'total_equilibrio': total_equilibrio,
      'gmv_equilibrio': gmv_equilibrio,
      'total_prejuizo': total_prejuizo,
      'prejuizo_acumulado': prejuizo_acumulado,
      'total_cancelados_ads_prejuizo': total_cancelados_ads_prejuizo,
      'taxa_lucratividade': taxa_lucratividade,
      'gmv_geral': gmv_geral,
      'lucro_geral': lucro_geral,
      'margem_media_geral': margem_media_geral,
      'vendas_geral': vendas_geral,
      'chart_labels_json': json.dumps(chart_labels),
      'chart_lucros_json': json.dumps(chart_lucros),
      'chart_colors_json': json.dumps(chart_colors),
      'chart_borders_json': json.dumps(chart_borders),
  }
  return render(request, 'fabrica/desempenho_produtos_marketplace.html', context)


@login_required(login_url='login')
def desempenho_fabrica_marketplace_view(request):
  canal_filter = request.GET.get('canal', 'todos')
  periodo_dias = request.GET.get('periodo', 'todos')
  search = request.GET.get('q', '').strip()
  tab_ativa = request.GET.get('tab', 'integrado')

  produtos_qs = (
      ProdutoMarketplace.objects.select_related('produto_fabrica')
      .filter(ativo=True)
      .order_by('nome_marketplace')
  )

  if canal_filter != 'todos':
    produtos_qs = produtos_qs.filter(canal=canal_filter)

  if search:
    produtos_qs = produtos_qs.filter(
        Q(nome_marketplace__icontains=search)
        | Q(sku_marketplace__icontains=search)
        | Q(produto_fabrica__nome__icontains=search)
        | Q(produto_fabrica__sku__icontains=search)
    )

  data_limite = None
  if periodo_dias.isdigit():
    data_limite = timezone.now() - timedelta(days=int(periodo_dias))

  produtos_data = []

  faturamento_mkt_total = 0.0
  lucro_mkt_total = 0.0
  pecas_produzidas_total = 0
  pedidos_total = 0

  faturamento_fabrica_total = 0.0
  custo_fabrica_total = 0.0
  lucro_fabrica_total = 0.0

  chart_labels = []
  chart_lucro_mkt = []
  chart_lucro_fabrica = []
  chart_lucro_integrado = []

  for p in produtos_qs:
    vendas_p = VendaMarketplace.objects.filter(produto_marketplace=p)
    if data_limite:
      vendas_p = vendas_p.filter(data_venda__gte=data_limite)

    qtd_pedidos = vendas_p.count()
    if qtd_pedidos == 0:
      continue

    vendas_list = list(vendas_p)
    pecas_vendidas = sum((v.quantidade or 1) * (v.quantidade_pecas_kit or 1) for v in vendas_list)
    pedidos_total += qtd_pedidos
    pecas_produzidas_total += pecas_vendidas

    gmv_p = sum(float(v.valor_bruto_venda or 0.0) for v in vendas_list)
    lucro_mkt_p = sum(float(v.lucro_liquido or 0.0) for v in vendas_list)
    margem_mkt_pct = (lucro_mkt_p / gmv_p * 100.0) if gmv_p > 0 else 0.0

    faturamento_mkt_total += gmv_p
    lucro_mkt_total += lucro_mkt_p

    custo_transf_unit = float(p.custo_transferencia_padrao or 0.0)
    custo_fabril_unit = p.get_custo_fabril_efetivo()
    lucro_fabril_unit = custo_transf_unit - custo_fabril_unit
    margem_fabrica_pct = (lucro_fabril_unit / custo_transf_unit * 100.0) if custo_transf_unit > 0 else 0.0

    faturamento_fabrica_p = pecas_vendidas * custo_transf_unit
    custo_fabrica_p = pecas_vendidas * custo_fabril_unit
    lucro_fabrica_p = faturamento_fabrica_p - custo_fabrica_p

    faturamento_fabrica_total += faturamento_fabrica_p
    custo_fabrica_total += custo_fabrica_p
    lucro_fabrica_total += lucro_fabrica_p

    lucro_integrado_p = lucro_mkt_p + lucro_fabrica_p
    margem_integrada_pct = (lucro_integrado_p / gmv_p * 100.0) if gmv_p > 0 else 0.0

    if lucro_mkt_p > 0 and lucro_fabrica_p > 0:
      status_label = "Dupla Lucratividade"
      status_badge = "badge-success"
      diagnostico = "Alta Rentabilidade: gera lucro no marketplace e margem industrial saudável na fábrica."
    elif lucro_fabrica_p > 0 and lucro_mkt_p <= 0:
      status_label = "Tracionador da Fábrica"
      status_badge = "badge-warning"
      diagnostico = "Estratégico: opera no zero a zero no canal, mas gera excelente lucro e escala para a fábrica."
    elif lucro_integrado_p < 0:
      status_label = "Prejuízo Consolidado"
      status_badge = "badge-danger"
      diagnostico = "Atenção: o lucro da fábrica não é suficiente para cobrir os prejuízos do marketplace."
    else:
      status_label = "Equilíbrio Integrado"
      status_badge = "badge-secondary"
      diagnostico = "Operação cobre todos os custos com margem líquida próxima a zero."

    produtos_data.append({
        'produto': p,
        'qtd_pedidos': qtd_pedidos,
        'pecas_vendidas': pecas_vendidas,
        'gmv_marketplace': gmv_p,
        'lucro_marketplace': lucro_mkt_p,
        'margem_mkt_pct': margem_mkt_pct,
        'custo_transf_unit': custo_transf_unit,
        'custo_fabril_unit': custo_fabril_unit,
        'lucro_fabril_unit': lucro_fabril_unit,
        'margem_fabrica_pct': margem_fabrica_pct,
        'faturamento_fabrica': faturamento_fabrica_p,
        'custo_fabrica_total': custo_fabrica_p,
        'lucro_fabrica_total': lucro_fabrica_p,
        'lucro_integrado': lucro_integrado_p,
        'margem_integrada_pct': margem_integrada_pct,
        'status_label': status_label,
        'status_badge': status_badge,
        'diagnostico': diagnostico,
    })

  produtos_data.sort(key=lambda x: x['lucro_integrado'], reverse=True)

  for item in produtos_data[:8]:
    label_short = (item['produto'].nome_marketplace[:18] + '...') if len(item['produto'].nome_marketplace) > 18 else item['produto'].nome_marketplace
    chart_labels.append(label_short)
    chart_lucro_mkt.append(round(item['lucro_marketplace'], 2))
    chart_lucro_fabrica.append(round(item['lucro_fabrica_total'], 2))
    chart_lucro_integrado.append(round(item['lucro_integrado'], 2))

  lucro_integrado_total = lucro_mkt_total + lucro_fabrica_total
  margem_integrada_total = (lucro_integrado_total / faturamento_mkt_total * 100.0) if faturamento_mkt_total > 0 else 0.0
  margem_mkt_total = (lucro_mkt_total / faturamento_mkt_total * 100.0) if faturamento_mkt_total > 0 else 0.0
  margem_fabrica_total = (lucro_fabrica_total / faturamento_fabrica_total * 100.0) if faturamento_fabrica_total > 0 else 0.0

  context = {
      'produtos_data': produtos_data,
      'canal_filter': canal_filter,
      'periodo_dias': periodo_dias,
      'search': search,
      'tab_ativa': tab_ativa,
      'faturamento_mkt_total': faturamento_mkt_total,
      'lucro_mkt_total': lucro_mkt_total,
      'margem_mkt_total': margem_mkt_total,
      'pecas_produzidas_total': pecas_produzidas_total,
      'pedidos_total': pedidos_total,
      'faturamento_fabrica_total': faturamento_fabrica_total,
      'custo_fabrica_total': custo_fabrica_total,
      'lucro_fabrica_total': lucro_fabrica_total,
      'margem_fabrica_total': margem_fabrica_total,
      'lucro_integrado_total': lucro_integrado_total,
      'margem_integrada_total': margem_integrada_total,
      'chart_labels_json': json.dumps(chart_labels),
      'chart_lucro_mkt_json': json.dumps(chart_lucro_mkt),
      'chart_lucro_fabrica_json': json.dumps(chart_lucro_fabrica),
      'chart_lucro_integrado_json': json.dumps(chart_lucro_integrado),
  }
  return render(request, 'fabrica/desempenho_fabrica_marketplace.html', context)


@admin_required
def salvar_custo_fabrica_marketplace_view(request, pk):
  if request.method == 'POST':
    prod_mkt = get_object_or_404(ProdutoMarketplace, pk=pk)
    custo_fabrica_str = request.POST.get('custo_producao_fabrica', '').replace('R$', '').replace(',', '.').strip()
    custo_transf_str = request.POST.get('custo_transferencia_padrao', '').replace('R$', '').replace(',', '.').strip()
    recalcular = request.POST.get('recalcular_vendas') == '1'

    try:
      if custo_fabrica_str:
        prod_mkt.custo_producao_fabrica = Decimal(custo_fabrica_str)
    except Exception:
      pass

    try:
      if custo_transf_str:
        prod_mkt.custo_transferencia_padrao = Decimal(custo_transf_str)
    except Exception:
      pass

    prod_mkt.save()

    if recalcular:
      vendas = VendaMarketplace.objects.filter(produto_marketplace=prod_mkt)
      for v in vendas:
        v.save()

    messages.success(request, f'Custos da fábrica para "{prod_mkt.nome_marketplace[:35]}" atualizados com sucesso!')
    next_url = request.POST.get('next_url')
    if next_url:
      return redirect(next_url)
    return redirect('desempenho_fabrica_marketplace')
  return redirect('desempenho_fabrica_marketplace')


@admin_required
def atualizar_custo_produto_marketplace_view(request, pk):
  if request.method == 'POST':
    prod_mkt = get_object_or_404(ProdutoMarketplace, pk=pk)

    novo_custo_str = request.POST.get('novo_custo', '').replace('R$', '').replace(',', '.').strip()
    preco_base_str = request.POST.get('preco_venda_unitario_base', '').replace('R$', '').replace(',', '.').strip()
    kits_permitidos_str = request.POST.get('kits_permitidos', '').strip()
    data_inicio_str = request.POST.get('data_vigencia_inicio', '').strip()
    motivo = request.POST.get('motivo_ajuste', '').strip()
    produto_fabrica_id = request.POST.get('produto_fabrica_id') or None

    try:
      novo_custo = Decimal(novo_custo_str) if novo_custo_str else Decimal('0.00')
    except Exception:
      messages.error(request, 'Valor de custo inválido.')
      return redirect('produtos_marketplace')

    if preco_base_str:
      try:
        prod_mkt.preco_venda_unitario_base = Decimal(preco_base_str)
      except Exception:
        pass

    if kits_permitidos_str:
      prod_mkt.kits_permitidos = kits_permitidos_str

    if data_inicio_str:
      try:
        data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
      except Exception:
        data_inicio = timezone.now().date()
    else:
      data_inicio = timezone.now().date()

    # Atualiza vínculo com produto da fábrica se informado
    if produto_fabrica_id:
      prod_mkt.produto_fabrica_id = int(produto_fabrica_id)
    elif 'limpar_vinculo' in request.POST:
      prod_mkt.produto_fabrica = None

    # Encerra data fim do histórico anterior que estava em aberto
    anterior = prod_mkt.historico_custos.filter(
        data_vigencia_inicio__lt=data_inicio,
        data_vigencia_fim__isnull=True
    ).first()
    if anterior:
      anterior.data_vigencia_fim = data_inicio - timedelta(days=1)
      anterior.save(update_fields=['data_vigencia_fim'])

    # Registra o novo histórico
    HistoricoCustoProdutoMarketplace.objects.create(
        produto_marketplace=prod_mkt,
        custo_transferencia=novo_custo,
        data_vigencia_inicio=data_inicio,
        motivo_ajuste=motivo or f"Reajuste de Custo para R$ {novo_custo:.2f}",
    )

    # Atualiza custo padrão vigente
    prod_mkt.custo_transferencia_padrao = novo_custo
    prod_mkt.save()

    # Recalcula todas as vendas deste produto:
    # 1. Quantidade de peças do kit estimada pelos novos parâmetros de tiers
    # 2. Custo unitário de transferência vigente na data da venda
    vendas = VendaMarketplace.objects.filter(produto_marketplace=prod_mkt)
    qtd_recalculadas = 0
    for v in vendas:
      v.quantidade_pecas_kit = prod_mkt.estimar_quantidade_pecas(
          v.valor_bruto_venda, nome_item=v.nome_produto_marketplace
      )
      v.custo_produto_unitario = prod_mkt.get_custo_para_data(v.data_venda)
      v.save()
      qtd_recalculadas += 1

    messages.success(
        request,
        f"Custo do produto '{prod_mkt.sku_marketplace}' atualizado para R$ {novo_custo:.2f} "
        f"com vigência a partir de {data_inicio.strftime('%d/%m/%Y')}! "
        f"({qtd_recalculadas} vendas foram recalculadas considerando as variações de kit)."
    )

  return redirect('produtos_marketplace')


@admin_required
def alterar_kit_venda_marketplace_view(request, pk):
  """Permite ao usuário alternar a quantidade de peças do kit em uma venda específica no Extrato"""
  if request.method == 'POST':
    venda = get_object_or_404(VendaMarketplace, pk=pk)
    nova_qtd = request.POST.get('quantidade_pecas_kit')
    if nova_qtd:
      try:
        venda.quantidade_pecas_kit = max(1, int(nova_qtd))
        venda.save()
        messages.success(
            request,
            f"Pedido #{venda.numero_pedido or venda.codigo_pedido}: Quantidade de peças atualizada para {venda.quantidade_pecas_kit} un (Custo Total: R$ {venda.custo_produto_total:.2f})."
        )
      except Exception as e:
        messages.error(request, f"Erro ao atualizar peças do pedido: {e}")

  next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'marketplace_dashboard'
  return redirect(next_url)


@admin_required
def adicionar_venda_marketplace(request):
  if request.method == 'POST':
    codigo_pedido = request.POST.get('codigo_pedido')
    if not codigo_pedido:
      import time
      codigo_pedido = f'PED-{int(time.time())}'

    canal = request.POST.get('canal')
    produto_id = request.POST.get('produto')
    quantidade = request.POST.get('quantidade') or 1
    valor_bruto = request.POST.get('valor_bruto_venda') or 0.00
    custo_unitario = request.POST.get('custo_produto_unitario') or 0.00
    taxa_comissao = request.POST.get('taxa_comissao_marketplace') or 0.00
    taxa_fixa = request.POST.get('taxa_fixa_marketplace') or 0.00
    custo_ads = request.POST.get('custo_ads_atribuido') or 0.00
    imposto = request.POST.get('imposto_estimado') or 0.00
    campanha_id = request.POST.get('campanha_ads') or None
    data_venda = request.POST.get('data_venda') or timezone.now()

    conta = ContaMarketplace.objects.filter(canal=canal, ativo=True).first()

    if produto_id and valor_bruto:
      produto = get_object_or_404(Produto, id=produto_id)
      VendaMarketplace.objects.create(
          codigo_pedido=codigo_pedido,
          canal=canal,
          conta=conta,
          produto=produto,
          campanha_ads_id=campanha_id,
          quantidade=quantidade,
          valor_bruto_venda=valor_bruto,
          custo_produto_unitario=custo_unitario,
          taxa_comissao_marketplace=taxa_comissao,
          taxa_fixa_marketplace=taxa_fixa,
          custo_ads_atribuido=custo_ads,
          imposto_estimado=imposto,
          data_venda=data_venda,
      )
  return redirect('marketplace_dashboard')


@admin_required
def adicionar_campanha_ads(request):
  if request.method == 'POST':
    canal = request.POST.get('canal')
    nome_campanha = request.POST.get('nome_campanha')
    produto_id = request.POST.get('produto') or None
    valor_investido = request.POST.get('valor_investido') or 0.00
    receita_atribuida = request.POST.get('receita_atribuida') or 0.00
    conversoes = request.POST.get('conversoes') or 0
    roas_informado = request.POST.get('roas_informado') or 0.00
    data_inicio = request.POST.get('data_inicio') or None

    if nome_campanha and canal:
      CampanhaAds.objects.create(
          canal=canal,
          nome_campanha=nome_campanha,
          produto_id=produto_id,
          valor_investido=valor_investido,
          receita_atribuida=receita_atribuida,
          conversoes=conversoes,
          roas_informado=roas_informado,
          data_inicio=data_inicio,
      )
  return redirect('marketplace_dashboard')


@admin_required
def distribuir_ads_vendas(request, pk):
  campanha = get_object_or_404(CampanhaAds, pk=pk)
  if request.method == 'POST':
    vendas_campanha = VendaMarketplace.objects.filter(campanha_ads=campanha)
    qtd_vendas = vendas_campanha.count()
    if qtd_vendas > 0 and campanha.valor_investido > 0:
      custo_por_venda = round(float(campanha.valor_investido) / qtd_vendas, 2)
      for v in vendas_campanha:
        v.custo_ads_atribuido = custo_por_venda
        v.save()
  return redirect('marketplace_dashboard')


@admin_required
def sincronizar_marketplace(request, canal):
  conta = ContaMarketplace.objects.filter(canal=canal).first()
  if conta:
    conta.ultima_sincronizacao = timezone.now()
    conta.status_conexao = 'conectado'
    conta.save()
  return redirect('marketplace_dashboard')


@admin_required
def usuarios_view(request):
  if request.method == 'POST':
    acao = request.POST.get('acao')
    if acao == 'criar':
      username = (request.POST.get('username') or '').strip()
      password = request.POST.get('password')
      tipo_usuario = request.POST.get('tipo_usuario')
      is_super = (tipo_usuario == 'admin')

      if username and password:
        if User.objects.filter(username=username).exists():
          messages.error(request, f'O usuário "{username}" já existe.')
        else:
          User.objects.create_user(
              username=username,
              password=password,
              is_superuser=is_super,
              is_staff=is_super,
          )
          tipo_label = 'Administrador' if is_super else 'Funcionário (Apenas Visualização)'
          messages.success(request, f'Usuário "{username}" criado com sucesso como {tipo_label}.')
      else:
        messages.error(request, 'Preencha o nome de usuário e a senha.')
      return redirect('usuarios')

    elif acao == 'alterar_senha':
      user_id = request.POST.get('user_id')
      nova_senha = request.POST.get('nova_senha')
      u = get_object_or_404(User, id=user_id)
      if nova_senha:
        u.set_password(nova_senha)
        u.save()
        messages.success(request, f'Senha do usuário "{u.username}" alterada com sucesso.')
      return redirect('usuarios')

    elif acao == 'toggle_status':
      user_id = request.POST.get('user_id')
      u = get_object_or_404(User, id=user_id)
      if u == request.user:
        messages.error(request, 'Você não pode desativar o seu próprio usuário.')
      else:
        u.is_active = not u.is_active
        u.save()
        status_txt = 'ativado' if u.is_active else 'desativado'
        messages.success(request, f'Usuário "{u.username}" {status_txt} com sucesso.')
      return redirect('usuarios')

    elif acao == 'excluir':
      user_id = request.POST.get('user_id')
      u = get_object_or_404(User, id=user_id)
      if u == request.user:
        messages.error(request, 'Você não pode excluir o seu próprio usuário.')
      else:
        u_nome = u.username
        u.delete()
        messages.success(request, f'Usuário "{u_nome}" excluído com sucesso.')
      return redirect('usuarios')

  context = {
      'usuarios': User.objects.all().order_by('-is_superuser', 'username')
  }
  return render(request, 'fabrica/usuarios.html', context)


# ==========================================
# PAINEL DE CLIENTES, PEDIDOS & PREVISÃO DE MATÉRIA-PRIMA
# ==========================================

@login_required(login_url='login')
def pedidos_view(request):
    status_filter = request.GET.get('status', 'todos')
    cliente_id = request.GET.get('cliente', '')
    search = request.GET.get('q', '').strip()

    if request.method == 'POST':
        if not verificar_permissao_adm(request):
            return redirect('pedidos')

        acao = request.POST.get('acao')
        if acao == 'criar_pedido':
            numero_pedido = request.POST.get('numero_pedido', '').strip()
            cliente_id_form = request.POST.get('cliente')
            data_pedido = request.POST.get('data_pedido') or timezone.now().date()
            data_entrega = request.POST.get('data_entrega_prevista') or None
            status_val = request.POST.get('status', 'confirmado')
            observacoes = request.POST.get('observacoes', '')

            cliente = get_object_or_404(Cliente, id=cliente_id_form)

            pedido = PedidoProducao(
                numero_pedido=numero_pedido,
                cliente=cliente,
                data_pedido=data_pedido,
                data_entrega_prevista=data_entrega,
                status=status_val,
                observacoes=observacoes,
            )
            pedido.save()

            produto_ids = request.POST.getlist('produto[]')
            quantidades = request.POST.getlist('quantidade[]')
            precos = request.POST.getlist('preco_unitario[]')
            grades = request.POST.getlist('grade[]')

            total_pedido = 0.0
            for i in range(len(produto_ids)):
                p_id = produto_ids[i]
                if not p_id:
                    continue
                prod = get_object_or_404(Produto, id=p_id)
                try:
                    qtd = int(quantidades[i]) if i < len(quantidades) and quantidades[i] else 1
                except (ValueError, TypeError):
                    qtd = 1

                try:
                    preco = float(precos[i]) if i < len(precos) and precos[i] else 0.0
                except (ValueError, TypeError):
                    preco = 0.0

                grade_txt = grades[i] if i < len(grades) else ''

                ItemPedidoProducao.objects.create(
                    pedido=pedido,
                    produto=prod,
                    quantidade=qtd,
                    preco_unitario=preco,
                    grade_cores_tamanhos=grade_txt
                )
                total_pedido += (preco * qtd)

            pedido.valor_total = total_pedido
            pedido.save()

            messages.success(request, f'Pedido {pedido.numero_pedido} registrado com sucesso para {cliente.nome}!')
            return redirect('detalhe_pedido', pk=pedido.pk)

        elif acao == 'atualizar_status':
            pedido_id = request.POST.get('pedido_id')
            novo_status = request.POST.get('status')
            data_entrega = request.POST.get('data_entrega_prevista') or None
            ped = get_object_or_404(PedidoProducao, id=pedido_id)
            ped.status = novo_status
            if data_entrega:
                ped.data_entrega_prevista = data_entrega
            ped.save()
            messages.success(request, f'Status do pedido {ped.numero_pedido} atualizado com sucesso.')
            return redirect('pedidos')

    pedidos_qs = PedidoProducao.objects.select_related('cliente').prefetch_related('itens__produto').all()

    if status_filter and status_filter != 'todos':
        pedidos_qs = pedidos_qs.filter(status=status_filter)

    if cliente_id:
        pedidos_qs = pedidos_qs.filter(cliente_id=cliente_id)

    if search:
        pedidos_qs = pedidos_qs.filter(
            Q(numero_pedido__icontains=search) |
            Q(cliente__nome__icontains=search) |
            Q(cliente__cidade__icontains=search) |
            Q(itens__produto__nome__icontains=search) |
            Q(itens__produto__sku__icontains=search)
        ).distinct()

    total_pedidos = pedidos_qs.count()
    pedidos_ativos = pedidos_qs.filter(status__in=['confirmado', 'em_producao']).count()
    total_pecas = sum(p.quantidade_total_pecas() for p in pedidos_qs)
    total_faturamento = sum(float(p.valor_total or 0) for p in pedidos_qs)

    context = {
        'pedidos': pedidos_qs,
        'clientes': Cliente.objects.filter(ativo=True).order_by('nome'),
        'produtos': Produto.objects.filter(status='linha').order_by('sku'),
        'status_filter': status_filter,
        'cliente_id': cliente_id,
        'search': search,
        'total_pedidos': total_pedidos,
        'pedidos_ativos': pedidos_ativos,
        'total_pecas': total_pecas,
        'total_faturamento': total_faturamento,
    }
    return render(request, 'fabrica/pedidos.html', context)


@login_required(login_url='login')
def detalhe_pedido_view(request, pk):
    pedido = get_object_or_404(
        PedidoProducao.objects.select_related('cliente').prefetch_related('itens__produto__materias_primas_consumo'),
        pk=pk
    )

    if request.method == 'POST':
        if not verificar_permissao_adm(request):
            return redirect('detalhe_pedido', pk=pk)

        acao = request.POST.get('acao')
        if acao == 'adicionar_item':
            produto_id = request.POST.get('produto')
            try:
                quantidade = int(request.POST.get('quantidade') or 1)
            except (ValueError, TypeError):
                quantidade = 1

            try:
                preco = float(request.POST.get('preco_unitario') or 0.0)
            except (ValueError, TypeError):
                preco = 0.0

            grade = request.POST.get('grade_cores_tamanhos', '')
            obs = request.POST.get('observacoes', '')

            prod = get_object_or_404(Produto, id=produto_id)
            ItemPedidoProducao.objects.create(
                pedido=pedido,
                produto=prod,
                quantidade=quantidade,
                preco_unitario=preco,
                grade_cores_tamanhos=grade,
                observacoes=obs
            )
            pedido.valor_total = sum(item.subtotal_venda() for item in pedido.itens.all())
            pedido.save()
            messages.success(request, f'Produto {prod.sku} adicionado ao pedido!')
            return redirect('detalhe_pedido', pk=pk)

        elif acao == 'remover_item':
            item_id = request.POST.get('item_id')
            item = get_object_or_404(ItemPedidoProducao, id=item_id, pedido=pedido)
            item.delete()
            pedido.valor_total = sum(i.subtotal_venda() for i in pedido.itens.all())
            pedido.save()
            messages.success(request, 'Item removido do pedido com sucesso.')
            return redirect('detalhe_pedido', pk=pk)

        elif acao == 'editar_pedido':
            pedido.status = request.POST.get('status', pedido.status)
            pedido.data_pedido = request.POST.get('data_pedido') or pedido.data_pedido
            pedido.data_entrega_prevista = request.POST.get('data_entrega_prevista') or None
            pedido.observacoes = request.POST.get('observacoes', '')
            pedido.save()
            messages.success(request, 'Dados do pedido atualizados com sucesso.')
            return redirect('detalhe_pedido', pk=pk)

    previsao_insumos = pedido.calcular_previsao_insumos()
    custo_total_insumos = pedido.custo_total_insumos_previsto()
    produtos_sem_ficha = pedido.produtos_sem_ficha()

    context = {
        'pedido': pedido,
        'itens': pedido.itens.select_related('produto').all(),
        'produtos_disponiveis': Produto.objects.filter(status='linha').order_by('sku'),
        'previsao_insumos': previsao_insumos,
        'custo_total_insumos': custo_total_insumos,
        'produtos_sem_ficha': produtos_sem_ficha,
        'total_pecas': pedido.quantidade_total_pecas(),
    }
    return render(request, 'fabrica/detalhe_pedido.html', context)


@login_required(login_url='login')
def imprimir_lista_compras_view(request, pk):
    pedido = get_object_or_404(
        PedidoProducao.objects.select_related('cliente').prefetch_related('itens__produto__materias_primas_consumo'),
        pk=pk
    )
    previsao_insumos = pedido.calcular_previsao_insumos()
    custo_total_insumos = pedido.custo_total_insumos_previsto()
    produtos_sem_ficha = pedido.produtos_sem_ficha()

    context = {
        'pedido': pedido,
        'cliente': pedido.cliente,
        'itens': pedido.itens.select_related('produto').all(),
        'insumos': previsao_insumos,
        'custo_total_insumos': custo_total_insumos,
        'produtos_sem_ficha': produtos_sem_ficha,
        'total_pecas': pedido.quantidade_total_pecas(),
        'data_emissao': timezone.now(),
    }
    return render(request, 'fabrica/lista_compras_impressao.html', context)


@admin_required
def excluir_pedido(request, pk):
    pedido = get_object_or_404(PedidoProducao, pk=pk)
    num = pedido.numero_pedido
    pedido.delete()
    messages.success(request, f'Pedido {num} excluído com sucesso.')
    return redirect('pedidos')


@login_required(login_url='login')
def clientes_view(request):
    search = request.GET.get('q', '').strip()

    if request.method == 'POST':
        if not verificar_permissao_adm(request):
            return redirect('clientes')

        acao = request.POST.get('acao')
        if acao == 'criar_cliente':
            nome = request.POST.get('nome', '').strip()
            nome_fantasia = request.POST.get('nome_fantasia', '').strip()
            cpf_cnpj = request.POST.get('cpf_cnpj', '').strip()
            tag = request.POST.get('tag', '').strip()
            telefone = request.POST.get('telefone', '').strip()
            email = request.POST.get('email', '').strip()
            cidade = request.POST.get('cidade', '').strip()
            uf = request.POST.get('uf', '').strip().upper()
            endereco = request.POST.get('endereco', '').strip()
            observacoes = request.POST.get('observacoes', '').strip()

            Cliente.objects.create(
                nome=nome,
                nome_fantasia=nome_fantasia,
                cpf_cnpj=cpf_cnpj,
                tag=tag,
                telefone=telefone,
                email=email,
                cidade=cidade,
                uf=uf,
                endereco=endereco,
                observacoes=observacoes,
            )
            messages.success(request, f'Cliente "{nome}" cadastrado com sucesso!')
            return redirect('clientes')

    clientes_qs = Cliente.objects.all().order_by('nome')
    if search:
        clientes_qs = clientes_qs.filter(
            Q(nome__icontains=search) |
            Q(nome_fantasia__icontains=search) |
            Q(cpf_cnpj__icontains=search) |
            Q(tag__icontains=search) |
            Q(telefone__icontains=search) |
            Q(cidade__icontains=search)
        )

    context = {
        'clientes': clientes_qs,
        'search': search,
        'total_clientes': Cliente.objects.count(),
        'clientes_ativos': Cliente.objects.filter(ativo=True).count(),
    }
    return render(request, 'fabrica/clientes.html', context)


@admin_required
def editar_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    if request.method == 'POST':
        cliente.nome = request.POST.get('nome', cliente.nome).strip()
        cliente.nome_fantasia = request.POST.get('nome_fantasia', '').strip()
        cliente.cpf_cnpj = request.POST.get('cpf_cnpj', '').strip()
        cliente.tag = request.POST.get('tag', '').strip()
        cliente.telefone = request.POST.get('telefone', '').strip()
        cliente.email = request.POST.get('email', '').strip()
        cliente.cidade = request.POST.get('cidade', '').strip()
        cliente.uf = request.POST.get('uf', '').strip().upper()
        cliente.endereco = request.POST.get('endereco', '').strip()
        cliente.observacoes = request.POST.get('observacoes', '').strip()
        cliente.ativo = bool(request.POST.get('ativo'))
        cliente.save()
        messages.success(request, f'Cliente "{cliente.nome}" atualizado com sucesso!')
        return redirect('clientes')

    return render(request, 'fabrica/editar_cliente.html', {'cliente': cliente})


@admin_required
def excluir_cliente(request, pk):
    cliente = get_object_or_404(Cliente, pk=pk)
    nome = cliente.nome
    cliente.delete()
    messages.success(request, f'Cliente "{nome}" excluído com sucesso.')
    return redirect('clientes')


# ==========================================
# CALENDÁRIO VISUAL DE PRODUÇÃO & EXECUÇÃO
# ==========================================

MESES_PT = [
    '', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

@login_required(login_url='login')
def calendario_producao_view(request):
    hoje = timezone.now().date()
    try:
        ano = int(request.GET.get('ano', hoje.year))
        mes = int(request.GET.get('mes', hoje.month))
    except (ValueError, TypeError):
        ano = hoje.year
        mes = hoje.month

    if mes < 1:
        mes = 12
        ano -= 1
    elif mes > 12:
        mes = 1
        ano += 1

    mes_anterior = 12 if mes == 1 else mes - 1
    ano_anterior = ano - 1 if mes == 1 else ano
    mes_proximo = 1 if mes == 12 else mes + 1
    ano_proximo = ano + 1 if mes == 12 else ano

    tipo_filtro = request.GET.get('tipo', 'todos')

    primeiro_dia_mes = date(ano, mes, 1)
    ultimo_dia_mes = date(ano, mes, calendar.monthrange(ano, mes)[1])

    # 1. Pedidos de Produção
    pedidos_qs = PedidoProducao.objects.select_related('cliente').prefetch_related('itens__produto').filter(
        data_pedido__lte=ultimo_dia_mes
    ).filter(
        Q(data_entrega_prevista__gte=primeiro_dia_mes) | Q(data_entrega_prevista__isnull=True)
    ).exclude(status='cancelado')

    # 2. Sub-lotes em Produção
    sublotes_qs = LoteProducao.objects.select_related('lote_corte', 'faccionista').filter(
        data_envio__lte=ultimo_dia_mes
    ).filter(
        Q(data_retorno__gte=primeiro_dia_mes) | Q(data_retorno__isnull=True)
    )

    # 3. Lotes de Corte
    cortes_qs = LoteCorte.objects.select_related('produto').filter(
        data_criacao__lte=ultimo_dia_mes
    ).filter(
        Q(data_prevista_retorno__gte=primeiro_dia_mes) | Q(data_prevista_retorno__isnull=True)
    )

    pedidos_mes_ativos = [p for p in pedidos_qs if p.status in ['confirmado', 'em_producao']]
    sublotes_fabrica_mes = [s for s in sublotes_qs if not s.faccionista or s.faccionista.tipo == 'costureira_interna']
    sublotes_faccao_mes = [s for s in sublotes_qs if s.faccionista and s.faccionista.tipo == 'faccionista']

    total_pecas_pedidos_mes = sum(p.quantidade_total_pecas() for p in pedidos_mes_ativos)
    total_pecas_fabrica_mes = sum(s.quantidade_enviada or 0 for s in sublotes_fabrica_mes)
    total_pecas_faccao_mes = sum(s.quantidade_enviada or 0 for s in sublotes_faccao_mes)
    total_entregas_mes = sum(1 for p in pedidos_qs if p.data_entrega_prevista and p.data_entrega_prevista.month == mes and p.data_entrega_prevista.year == ano)

    cal = calendar.Calendar(firstweekday=0)
    mes_dias = cal.monthdatescalendar(ano, mes)

    semanas = []
    for semana in mes_dias:
        dias_semana = []
        for d in semana:
            pertence_ao_mes = (d.month == mes)
            eh_hoje = (d == hoje)

            eventos_dia = []

            # Pedidos
            if tipo_filtro in ['todos', 'pedidos']:
                for ped in pedidos_qs:
                    data_inicio = ped.data_pedido
                    data_fim = ped.data_entrega_prevista or ped.data_pedido
                    if data_inicio <= d <= data_fim or d == data_fim:
                        eh_entrega = (ped.data_entrega_prevista == d)
                        eventos_dia.append({
                            'id': ped.id,
                            'tipo': 'pedido',
                            'tipo_label': 'Pedido de Cliente',
                            'titulo': f"{ped.numero_pedido} - {ped.cliente.nome}" + (f" [TAG: {ped.cliente.tag}]" if ped.cliente.tag else ""),
                            'subtitulo': f"{ped.quantidade_total_pecas()} pçs",
                            'eh_entrega': eh_entrega,
                            'status': ped.get_status_display(),
                            'status_cod': ped.status,
                            'detalhes': f"Cliente: {ped.cliente.nome}" + (f" | TAG da Peça: {ped.cliente.tag}" if ped.cliente.tag else "") + f" | Entrega: {ped.data_entrega_prevista.strftime('%d/%m/%Y') if ped.data_entrega_prevista else 'A definir'}",
                            'url': reverse('detalhe_pedido', args=[ped.id]),
                            'cor_badge': 'badge-cal-pedido',
                        })

            # Sub-lotes
            for sub in sublotes_qs:
                is_costureira_fabrica = (not sub.faccionista or sub.faccionista.tipo == 'costureira_interna')
                if is_costureira_fabrica and tipo_filtro not in ['todos', 'fabrica']:
                    continue
                if not is_costureira_fabrica and tipo_filtro not in ['todos', 'faccionistas']:
                    continue

                d_ini = sub.data_envio or primeiro_dia_mes
                d_fim = sub.data_retorno or (d_ini + timedelta(days=7))
                if d_ini <= d <= d_fim:
                    if is_costureira_fabrica:
                        tipo_label = 'Costura Fábrica'
                        resp = sub.faccionista.nome if sub.faccionista else 'Costura Geral'
                        cor_classe = 'badge-cal-fabrica'
                    else:
                        tipo_label = 'Facção Externa'
                        resp = sub.faccionista.nome if sub.faccionista else 'Facção'
                        cor_classe = 'badge-cal-faccao'

                    eventos_dia.append({
                        'id': sub.id,
                        'tipo': 'sublote',
                        'tipo_label': tipo_label,
                        'titulo': f"{sub.codigo_sub_lote} ({resp})",
                        'subtitulo': f"{sub.quantidade_enviada} pçs",
                        'eh_entrega': (sub.data_retorno == d),
                        'status': sub.get_status_display(),
                        'status_cod': sub.status,
                        'detalhes': f"Destino: {tipo_label} | Responsável: {resp} | Qtd: {sub.quantidade_enviada} pçs",
                        'url': reverse('producao'),
                        'cor_badge': cor_classe,
                    })

            # Cortes
            if tipo_filtro in ['todos', 'cortes']:
                for c in cortes_qs:
                    c_ini = c.data_envio_cortador or c.data_criacao
                    c_fim = c.data_prevista_retorno or c_ini
                    if c_ini <= d <= c_fim or d == c_ini:
                        eventos_dia.append({
                            'id': c.id,
                            'tipo': 'corte',
                            'tipo_label': 'Lote de Corte',
                            'titulo': f"Lote {c.codigo_lote} ({c.produto.sku})",
                            'subtitulo': f"{c.quantidade_total_pecas} pçs",
                            'eh_entrega': (c.data_prevista_retorno == d),
                            'status': c.get_status_display(),
                            'status_cod': c.status,
                            'detalhes': f"Corte: {c.produto.sku} - {c.produto.nome} | Cortador: {c.cortador or 'Interno'}",
                            'url': reverse('lotes_corte'),
                            'cor_badge': 'badge-cal-corte',
                        })

            dias_semana.append({
                'data': d,
                'dia_numero': d.day,
                'pertence_ao_mes': pertence_ao_mes,
                'eh_hoje': eh_hoje,
                'total_eventos': len(eventos_dia),
                'eventos': eventos_dia,
            })
        semanas.append(dias_semana)

    context = {
        'ano': ano,
        'mes': mes,
        'mes_nome': MESES_PT[mes],
        'ano_anterior': ano_anterior,
        'mes_anterior': mes_anterior,
        'ano_proximo': ano_proximo,
        'mes_proximo': mes_proximo,
        'tipo_filtro': tipo_filtro,
        'semanas': semanas,
        'total_pedidos_mes': len(pedidos_mes_ativos),
        'total_pecas_pedidos_mes': total_pecas_pedidos_mes,
        'total_pecas_fabrica_mes': total_pecas_fabrica_mes,
        'total_pecas_faccao_mes': total_pecas_faccao_mes,
        'total_entregas_mes': total_entregas_mes,
    }
    return render(request, 'fabrica/calendario_producao.html', context)


# ==========================================
# FLUXO DE CAIXA: CONTAS A PAGAR / RECEBER & CONTA AZUL
# ==========================================

@login_required(login_url='login')
def financeiro_contas_view(request):
    tipo_filtro = request.GET.get('tipo', 'todos')
    status_filtro = request.GET.get('status', 'todos')
    categoria_filtro = request.GET.get('categoria', 'todos')
    periodo_filtro = request.GET.get('periodo', 'mes')
    search = request.GET.get('q', '').strip()

    hoje = timezone.now().date()

    if request.method == 'POST':
        if not verificar_permissao_adm(request):
            return redirect('financeiro_contas')

        acao = request.POST.get('acao')
        if acao == 'criar_transacao':
            tipo = request.POST.get('tipo', 'pagar')
            descricao = request.POST.get('descricao', '').strip()
            categoria = request.POST.get('categoria', 'Outros')
            cliente_fornecedor = request.POST.get('cliente_fornecedor', '').strip()
            try:
                valor = float(request.POST.get('valor') or 0.0)
            except (ValueError, TypeError):
                valor = 0.0

            data_competencia = request.POST.get('data_competencia') or hoje
            data_vencimento = request.POST.get('data_vencimento') or hoje
            forma_pagamento = request.POST.get('forma_pagamento', 'PIX')
            conta_bancaria = request.POST.get('conta_bancaria', 'Banco Principal')
            observacoes = request.POST.get('observacoes', '')

            status_val = 'pago' if request.POST.get('ja_pago') else 'pendente'
            data_pagamento_val = hoje if status_val == 'pago' else None
            valor_pago_val = valor if status_val == 'pago' else 0.0

            TransacaoFinanceira.objects.create(
                tipo=tipo,
                descricao=descricao,
                categoria=categoria,
                cliente_fornecedor=cliente_fornecedor,
                valor=valor,
                valor_pago=valor_pago_val,
                data_competencia=data_competencia,
                data_vencimento=data_vencimento,
                data_pagamento=data_pagamento_val,
                status=status_val,
                forma_pagamento=forma_pagamento,
                conta_bancaria=conta_bancaria,
                observacoes=observacoes
            )
            messages.success(request, f'Lançamento "{descricao}" cadastrado com sucesso!')
            return redirect('financeiro_contas')

        elif acao == 'dar_baixa':
            transacao_id = request.POST.get('transacao_id')
            t = get_object_or_404(TransacaoFinanceira, id=transacao_id)
            t.status = 'pago'
            t.valor_pago = t.valor
            t.data_pagamento = request.POST.get('data_pagamento') or hoje
            t.save()
            msg = 'Recebimento confirmado!' if t.tipo == 'receber' else 'Pagamento registrado com sucesso!'
            messages.success(request, msg)
            return redirect('financeiro_contas')

        elif acao == 'importar_producao':
            criados = 0
            # 1. Sub-lotes
            for sub in LoteProducao.objects.filter(valor_unitario_costura__gt=0):
                custo = sub.custo_total_costura or (float(sub.valor_unitario_costura) * (sub.quantidade_real_costurada or sub.quantidade_enviada or 0))
                if custo and float(custo) > 0 and not TransacaoFinanceira.objects.filter(sub_lote=sub).exists():
                    resp = sub.faccionista.nome if sub.faccionista else "Costura Geral"
                    cat = 'Costura-Fabrica' if (not sub.faccionista or sub.faccionista.tipo == 'costureira_interna') else 'Faccao'
                    desc = f"Costura Sub-lote {sub.codigo_sub_lote} ({resp})"
                    venc = sub.data_retorno or sub.data_envio or hoje
                    TransacaoFinanceira.objects.create(
                        tipo='pagar',
                        descricao=desc,
                        categoria=cat,
                        cliente_fornecedor=resp,
                        valor=custo,
                        valor_pago=custo if sub.pago_costura else 0.0,
                        data_competencia=sub.data_envio or hoje,
                        data_vencimento=venc,
                        data_pagamento=sub.data_pagamento_costura if sub.pago_costura else None,
                        status='pago' if sub.pago_costura else 'pendente',
                        sub_lote=sub,
                        conta_bancaria='Banco Principal'
                    )
                    criados += 1

            # 2. Cortes
            for corte in LoteCorte.objects.filter(valor_unitario_corte__gt=0):
                custo = corte.custo_total_corte or (float(corte.valor_unitario_corte) * (corte.quantidade_total_pecas or 0))
                if custo and float(custo) > 0 and not TransacaoFinanceira.objects.filter(lote_corte=corte).exists():
                    resp = corte.cortador or "Cortador Externo"
                    desc = f"Corte Lote {corte.codigo_lote} ({corte.produto.sku})"
                    venc = corte.data_prevista_retorno or corte.data_criacao or hoje
                    TransacaoFinanceira.objects.create(
                        tipo='pagar',
                        descricao=desc,
                        categoria='Corte',
                        cliente_fornecedor=resp,
                        valor=custo,
                        valor_pago=custo if corte.pago_cortador else 0.0,
                        data_competencia=corte.data_criacao or hoje,
                        data_vencimento=venc,
                        data_pagamento=corte.data_pagamento_cortador if corte.pago_cortador else None,
                        status='pago' if corte.pago_cortador else 'pendente',
                        lote_corte=corte,
                        conta_bancaria='Banco Principal'
                    )
                    criados += 1

            # 3. Pedidos de Clientes
            for ped in PedidoProducao.objects.filter(valor_total__gt=0).exclude(status='cancelado'):
                if not TransacaoFinanceira.objects.filter(pedido=ped).exists():
                    TransacaoFinanceira.objects.create(
                        tipo='receber',
                        descricao=f"Pedido {ped.numero_pedido} - {ped.cliente.nome}",
                        categoria='Vendas-Atacado',
                        cliente_fornecedor=ped.cliente.nome,
                        valor=ped.valor_total,
                        valor_pago=ped.valor_total if ped.status == 'concluido' else 0.0,
                        data_competencia=ped.data_pedido,
                        data_vencimento=ped.data_entrega_prevista or ped.data_pedido,
                        status='pago' if ped.status == 'concluido' else 'pendente',
                        pedido=ped,
                        conta_bancaria='Banco Principal'
                    )
                    criados += 1

            messages.success(request, f'Sincronização interna concluída! {criados} novos lançamentos gerados a partir da produção e pedidos.')
            return redirect('financeiro_contas')

        elif acao == 'sincronizar_conta_azul':
            service = ContaAzulService()
            count, msg = service.sincronizar_transacoes()
            sucesso_imp, msg_imp = service.importar_transacoes_do_conta_azul()
            if sucesso_imp:
                messages.success(request, f'Sincronização concluída! {count} locais enviados e {msg_imp}')
            else:
                messages.success(request, f'Conta Azul Sincronizado! {count} lançamentos foram sincronizados ({msg}).')
            return redirect('financeiro_contas')

        elif acao == 'importar_conta_azul':
            service = ContaAzulService()
            data_inicio = request.POST.get('data_inicio') or None
            data_fim = request.POST.get('data_fim') or None
            sucesso, msg = service.importar_transacoes_do_conta_azul(data_inicio=data_inicio, data_fim=data_fim)
            if sucesso:
                messages.success(request, f'📥 Importação concluída: {msg}')
            else:
                messages.error(request, f'Erro ao importar: {msg}')
            return redirect('financeiro_contas')

        elif acao == 'trocar_codigo_conta_azul':
            service = ContaAzulService()
            codigo = request.POST.get('codigo_autorizacao', '').strip()
            if codigo:
                sucesso, msg = service.trocar_codigo_por_token(codigo)
                if sucesso:
                    messages.success(request, msg)
                else:
                    messages.error(request, msg)
            else:
                messages.error(request, 'Por favor, informe o código de autorização retornado na URL.')
            return redirect('financeiro_contas')

        elif acao == 'renovar_token_conta_azul':
            service = ContaAzulService()
            sucesso, msg = service.renovar_token()
            if sucesso:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return redirect('financeiro_contas')

        elif acao == 'salvar_config_conta_azul':
            service = ContaAzulService()
            config = service.config
            config.client_id = request.POST.get('client_id', '').strip()
            config.client_secret = request.POST.get('client_secret', '').strip()
            config.basic_auth = request.POST.get('basic_auth', '').strip()
            config.redirect_uri = request.POST.get('redirect_uri', 'https://contaazul.com').strip()
            config.usuario_erp = request.POST.get('usuario_erp', '').strip()
            config.senha_erp = request.POST.get('senha_erp', '').strip()
            config.access_token = request.POST.get('access_token', '').strip()
            config.refresh_token = request.POST.get('refresh_token', '').strip()
            config.ativo = bool(request.POST.get('ativo'))
            config.save()
            messages.success(request, 'Configurações de integração com Conta Azul salvas com sucesso!')
            return redirect('financeiro_contas')

        elif acao == 'excluir_transacao':
            transacao_id = request.POST.get('transacao_id')
            t = get_object_or_404(TransacaoFinanceira, id=transacao_id)
            desc = t.descricao
            t.delete()
            messages.success(request, f'Lançamento "{desc}" excluído com sucesso.')
            return redirect('financeiro_contas')

    # QuerySet de Transações
    transacoes_qs = TransacaoFinanceira.objects.all()

    # Atualizar pendentes vencidos para atrasado
    transacoes_qs.filter(status='pendente', data_vencimento__lt=hoje).update(status='atrasado')

    if tipo_filtro and tipo_filtro != 'todos':
        transacoes_qs = transacoes_qs.filter(tipo=tipo_filtro)

    if status_filtro and status_filtro != 'todos':
        transacoes_qs = transacoes_qs.filter(status=status_filtro)

    if categoria_filtro and categoria_filtro != 'todos':
        transacoes_qs = transacoes_qs.filter(categoria=categoria_filtro)

    if periodo_filtro == 'mes':
        transacoes_qs = transacoes_qs.filter(data_vencimento__year=hoje.year, data_vencimento__month=hoje.month)
    elif periodo_filtro == 'semana':
        inicio_sem = hoje - timedelta(days=hoje.weekday())
        fim_sem = inicio_sem + timedelta(days=6)
        transacoes_qs = transacoes_qs.filter(data_vencimento__range=[inicio_sem, fim_sem])
    elif periodo_filtro == 'hoje':
        transacoes_qs = transacoes_qs.filter(data_vencimento=hoje)
    elif periodo_filtro == 'atrasados':
        transacoes_qs = transacoes_qs.filter(status='atrasado')

    if search:
        transacoes_qs = transacoes_qs.filter(
            Q(descricao__icontains=search) |
            Q(cliente_fornecedor__icontains=search) |
            Q(categoria__icontains=search) |
            Q(id_conta_azul__icontains=search)
        )

    todas_mes = TransacaoFinanceira.objects.filter(data_vencimento__year=hoje.year, data_vencimento__month=hoje.month).exclude(status='cancelado')
    total_receber_mes = sum(float(t.valor) for t in todas_mes if t.tipo == 'receber')
    total_recebido_mes = sum(float(t.valor_pago) for t in todas_mes if t.tipo == 'receber' and t.status == 'pago')

    total_pagar_mes = sum(float(t.valor) for t in todas_mes if t.tipo == 'pagar')
    total_pago_mes = sum(float(t.valor_pago) for t in todas_mes if t.tipo == 'pagar' and t.status == 'pago')

    saldo_projetado_mes = total_receber_mes - total_pagar_mes
    saldo_realizado_mes = total_recebido_mes - total_pago_mes

    total_atrasadas = TransacaoFinanceira.objects.filter(status='atrasado').count()
    valor_atrasado = sum(float(t.valor) for t in TransacaoFinanceira.objects.filter(status='atrasado'))

    service = ContaAzulService()
    config_ca = service.config
    url_autorizacao_ca = service.obter_url_autorizacao()

    context = {
        'transacoes': transacoes_qs,
        'tipo_filtro': tipo_filtro,
        'status_filtro': status_filtro,
        'categoria_filtro': categoria_filtro,
        'periodo_filtro': periodo_filtro,
        'search': search,
        'total_receber_mes': total_receber_mes,
        'total_recebido_mes': total_recebido_mes,
        'total_pagar_mes': total_pagar_mes,
        'total_pago_mes': total_pago_mes,
        'saldo_projetado_mes': saldo_projetado_mes,
        'saldo_realizado_mes': saldo_realizado_mes,
        'total_atrasadas': total_atrasadas,
        'valor_atrasado': valor_atrasado,
        'config_ca': config_ca,
        'url_autorizacao_ca': url_autorizacao_ca,
        'hoje': hoje,
    }
    return render(request, 'fabrica/financeiro_contas.html', context)


# ==============================================================================
# ENGENHARIA DE PRODUTO: OPERAÇÕES & TEMPO PADRÃO (TP)
# ==============================================================================

@login_required(login_url='login')
def operacoes_engenharia_view(request):
    """
    Painel de Engenharia de Produto, Cadastro de Operações e Cálculo de Tempo Padrão (TP).
    Calcula TP por operação, TP total da peça, peças/hora, custo estimado de mão de obra
    e balanceamento de máquinas.
    """
    produtos = Produto.objects.select_related('categoria').prefetch_related('operacoes').all().order_by('nome')
    referencias_maquinas = ReferenciaMaquinaOperacao.objects.filter(ativo=True).order_by('codigo')
    dificuldades = DificuldadeManuseio.objects.filter(ativo=True).order_by('ordem')
    config_eng, _ = ConfiguracaoEngenharia.objects.get_or_create(id=1)

    # Processamento de Ações POST
    if request.method == 'POST':
        if not verificar_permissao_adm(request):
            return redirect('operacoes_engenharia')

        action = request.POST.get('action')
        produto_id_post = request.POST.get('produto_id')

        if action == 'adicionar_operacao':
            produto = get_object_or_404(Produto, id=produto_id_post)
            proxima_ordem = (produto.operacoes.count() + 1)
            ordem_val = int(request.POST.get('ordem') or proxima_ordem)
            
            titulo = request.POST.get('titulo', '').strip()
            parte_peca = request.POST.get('parte_peca', '').strip()
            maquina_codigo = request.POST.get('maquina_codigo', '').strip()
            condicao = request.POST.get('condicao', 'sem_aviamento')
            aparelho = request.POST.get('aparelho', '').strip()
            destino = request.POST.get('destino', '').strip()
            qtde_manuseio = int(request.POST.get('qtde_manuseio') or 1)
            dificuldade = request.POST.get('dificuldade', 'F2')
            comp = request.POST.get('comprimento_costura_cm') or 0.0
            pot_seg = request.POST.get('pot_seg') or None
            ritmo = request.POST.get('ritmo') or 1.00
            tolerancia = request.POST.get('tolerancia') or 0.15
            obs = request.POST.get('observacoes', '').strip()

            OperacaoProduto.objects.create(
                produto=produto,
                ordem=ordem_val,
                titulo=titulo,
                parte_peca=parte_peca,
                maquina_codigo=maquina_codigo,
                condicao=condicao,
                aparelho=aparelho,
                destino=destino,
                qtde_manuseio=qtde_manuseio,
                dificuldade=dificuldade,
                comprimento_costura_cm=comp,
                pot_seg=pot_seg if pot_seg else None,
                ritmo=ritmo,
                tolerancia=tolerancia,
                observacoes=obs
            )
            messages.success(request, f'Operação "{titulo}" cadastrada com sucesso!')
            return redirect(f"{reverse('operacoes_engenharia')}?produto={produto.id}")

        elif action == 'editar_operacao':
            op_id = request.POST.get('operacao_id')
            op = get_object_or_404(OperacaoProduto, id=op_id)
            
            op.ordem = int(request.POST.get('ordem') or op.ordem)
            op.titulo = request.POST.get('titulo', op.titulo).strip()
            op.parte_peca = request.POST.get('parte_peca', '').strip()
            op.maquina_codigo = request.POST.get('maquina_codigo', op.maquina_codigo).strip()
            op.maquina_nome = request.POST.get('maquina_nome', '').strip() or None
            op.condicao = request.POST.get('condicao', op.condicao)
            op.aparelho = request.POST.get('aparelho', '').strip()
            op.destino = request.POST.get('destino', '').strip()
            op.qtde_manuseio = int(request.POST.get('qtde_manuseio') or 1)
            op.dificuldade = request.POST.get('dificuldade', op.dificuldade)
            op.comprimento_costura_cm = request.POST.get('comprimento_costura_cm') or 0.0
            
            pot_seg = request.POST.get('pot_seg')
            op.pot_seg = pot_seg if pot_seg else None
            op.ritmo = request.POST.get('ritmo') or 1.00
            op.tolerancia = request.POST.get('tolerancia') or 0.15
            op.observacoes = request.POST.get('observacoes', '').strip()
            op.save()

            messages.success(request, f'Operação #{op.ordem} atualizada e recalculada!')
            return redirect(f"{reverse('operacoes_engenharia')}?produto={op.produto_id}")

        elif action == 'excluir_operacao':
            op_id = request.POST.get('operacao_id')
            op = get_object_or_404(OperacaoProduto, id=op_id)
            prod_id = op.produto_id
            titulo_rem = op.titulo
            op.delete()
            messages.success(request, f'Operação "{titulo_rem}" removida com sucesso.')
            return redirect(f"{reverse('operacoes_engenharia')}?produto={prod_id}")

        elif action == 'duplicar_operacoes':
            origem_id = request.POST.get('origem_produto_id')
            destino_id = request.POST.get('destino_produto_id')
            if origem_id and destino_id and origem_id != destino_id:
                origem = get_object_or_404(Produto, id=origem_id)
                destino = get_object_or_404(Produto, id=destino_id)
                ops_origem = origem.operacoes.all().order_by('ordem')
                copiadas = 0
                for op in ops_origem:
                    OperacaoProduto.objects.create(
                        produto=destino,
                        ordem=op.ordem,
                        titulo=op.titulo,
                        parte_peca=op.parte_peca,
                        maquina_codigo=op.maquina_codigo,
                        maquina_nome=op.maquina_nome,
                        condicao=op.condicao,
                        aparelho=op.aparelho,
                        destino=op.destino,
                        qtde_manuseio=op.qtde_manuseio,
                        dificuldade=op.dificuldade,
                        comprimento_costura_cm=op.comprimento_costura_cm,
                        pot_seg=op.pot_seg,
                        ritmo=op.ritmo,
                        tolerancia=op.tolerancia,
                        observacoes=op.observacoes
                    )
                    copiadas += 1
                messages.success(request, f'{copiadas} operações copiadas com sucesso de {origem.nome} para {destino.nome}!')
                return redirect(f"{reverse('operacoes_engenharia')}?produto={destino.id}")

        elif action == 'salvar_config_engenharia':
            config_eng.tempo_pacote_min = request.POST.get('tempo_pacote_min', 0.70)
            config_eng.tamanho_pacote = int(request.POST.get('tamanho_pacote') or 50)
            config_eng.jornada_horas_dia = request.POST.get('jornada_horas_dia', 8.0)
            config_eng.tolerancia_padrao = request.POST.get('tolerancia_padrao', 0.15)
            config_eng.custo_minuto_costura = request.POST.get('custo_minuto_costura', 0.35)
            config_eng.save()

            # Recalcula operações de todos os produtos para atualizar cota de pacote
            for op in OperacaoProduto.objects.all():
                op.save()

            messages.success(request, 'Parâmetros globais de engenharia e tempos de pacote atualizados!')
            return redirect('operacoes_engenharia')

        elif action == 'salvar_referencia_maquina':
            cod = request.POST.get('codigo', '').strip().upper()
            nome = request.POST.get('nome', '').strip()
            tipo_calc = request.POST.get('tipo_calculo', '10cm')
            tempo_base = request.POST.get('tempo_base', 0.07)
            fator_el = request.POST.get('fator_elastico', 0.05)
            fator_vi = request.POST.get('fator_vies', 0.05)
            fator_2vi = request.POST.get('fator_2vies', 0.10)

            if cod and nome:
                ReferenciaMaquinaOperacao.objects.update_or_create(
                    codigo=cod,
                    defaults={
                        'nome': nome,
                        'tipo_calculo': tipo_calc,
                        'tempo_base': tempo_base,
                        'fator_elastico': fator_el,
                        'fator_vies': fator_vi,
                        'fator_2vies': fator_2vi,
                        'ativo': True
                    }
                )
                messages.success(request, f'Máquina/Operação "{cod} - {nome}" salva na tabela de referência!')
            return redirect('operacoes_engenharia')

    # Seleção de Produto
    produto_id_filtro = request.GET.get('produto', '').strip()
    produto_selecionado = None
    if produto_id_filtro:
        produto_selecionado = Produto.objects.filter(id=produto_id_filtro).first()
    
    if not produto_selecionado:
        # Pega o primeiro produto com operações ou primeiro do banco
        prod_com_ops = Produto.objects.filter(operacoes__isnull=False).distinct().first()
        produto_selecionado = prod_com_ops or produtos.first()

    operacoes_selecionado = []
    distribuicao_maquinas = []
    tempo_padrao_total = 0.0
    tempo_padrao_pcte_total = 0.0
    pecas_hora = 0.0
    pecas_dia = 0.0
    custo_mao_obra = 0.0

    if produto_selecionado:
        operacoes_selecionado = produto_selecionado.operacoes.all().order_by('ordem', 'id')
        tempo_padrao_total = produto_selecionado.tempo_padrao_total_min()
        tempo_padrao_pcte_total = produto_selecionado.tempo_padrao_pcte_total_min()
        pecas_hora = produto_selecionado.pecas_por_hora()
        pecas_dia = produto_selecionado.pecas_por_dia()
        distribuicao_maquinas = produto_selecionado.distribuicao_maquinas()
        custo_mao_obra = round(tempo_padrao_total * float(config_eng.custo_minuto_costura or 0.35), 2)

    # Indicadores Globais da Fábrica (Tempo Médio Padrão Geral)
    produtos_com_ops = [p for p in produtos if p.operacoes.exists()]
    total_modelos_estudados = len(produtos_com_ops)
    total_operacoes_fabrica = OperacaoProduto.objects.count()
    
    if produtos_com_ops:
        tempo_medio_geral = round(sum(p.tempo_padrao_total_min() for p in produtos_com_ops) / total_modelos_estudados, 2)
        capacidade_media_geral = round(60.0 / tempo_medio_geral, 1) if tempo_medio_geral > 0 else 0
    else:
        tempo_medio_geral = 0.0
        capacidade_media_geral = 0.0

    # Identificação da Máquina Gargalo Geral
    tempo_por_maquina_geral = {}
    for op in OperacaoProduto.objects.all():
        maq = op.maquina_nome or op.maquina_codigo or 'Outras'
        tempo_por_maquina_geral[maq] = tempo_por_maquina_geral.get(maq, 0.0) + float(op.tempo_padrao or 0)
    
    maquina_gargalo = "Nenhuma"
    if tempo_por_maquina_geral:
        maquina_gargalo = max(tempo_por_maquina_geral.items(), key=lambda x: x[1])[0]

    context = {
        'produtos': produtos,
        'produto_selecionado': produto_selecionado,
        'operacoes': operacoes_selecionado,
        'distribuicao_maquinas': distribuicao_maquinas,
        'tempo_padrao_total': tempo_padrao_total,
        'tempo_padrao_pcte_total': tempo_padrao_pcte_total,
        'pecas_hora': pecas_hora,
        'pecas_dia': pecas_dia,
        'custo_mao_obra': custo_mao_obra,
        'referencias_maquinas': referencias_maquinas,
        'dificuldades': dificuldades,
        'config_eng': config_eng,
        'total_modelos_estudados': total_modelos_estudados,
        'total_operacoes_fabrica': total_operacoes_fabrica,
        'tempo_medio_geral': tempo_medio_geral,
        'capacidade_media_geral': capacidade_media_geral,
        'maquina_gargalo': maquina_gargalo,
    }
    return render(request, 'fabrica/operacoes_engenharia.html', context)


@login_required(login_url='login')
def materias_primas_view(request):
    if request.method == 'POST':
        if not verificar_permissao_adm(request):
            messages.error(request, 'Apenas administradores podem gerenciar matérias-primas.')
            return redirect('materias_primas')

        acao = request.POST.get('acao')

        if acao == 'cadastrar':
            nome = (request.POST.get('nome') or '').strip()
            codigo = (request.POST.get('codigo') or '').strip().upper()
            fornecedor = (request.POST.get('fornecedor') or '').strip()
            composicao = (request.POST.get('composicao') or '').strip()
            unidade = (request.POST.get('unidade_medida') or 'KG').strip().upper()
            preco_str = request.POST.get('preco_unitario', '0').replace(',', '.')
            estoque_str = request.POST.get('estoque_metros', '0').replace(',', '.')

            try:
                preco_val = float(preco_str or 0)
            except ValueError:
                preco_val = 0.0

            try:
                estoque_val = float(estoque_str or 0)
            except ValueError:
                estoque_val = 0.0

            if nome:
                mp, created = MateriaPrima.objects.update_or_create(
                    nome=nome,
                    defaults={
                        'codigo': codigo,
                        'fornecedor': fornecedor,
                        'composicao': composicao,
                        'unidade_medida': unidade,
                        'preco_unitario': preco_val,
                        'estoque_metros': estoque_val,
                        'ativo': True,
                    }
                )
                if created:
                    messages.success(request, f'Matéria-prima "{nome}" cadastrada com sucesso! Preço: R$ {preco_val:.4f}/{unidade}')
                else:
                    afetados = mp.recalcular_produtos()
                    messages.success(request, f'Matéria-prima "{nome}" atualizada! Preço: R$ {preco_val:.4f}/{unidade}. O custo de {afetados} produto(s) foi recalculado automaticamente!')
            return redirect('materias_primas')

        elif acao == 'editar':
            mp_id = request.POST.get('mp_id')
            mp = get_object_or_404(MateriaPrima, pk=mp_id)
            novo_nome = (request.POST.get('nome') or '').strip()
            codigo = (request.POST.get('codigo') or '').strip().upper()
            fornecedor = (request.POST.get('fornecedor') or '').strip()
            composicao = (request.POST.get('composicao') or '').strip()
            unidade = (request.POST.get('unidade_medida') or mp.unidade_medida).strip().upper()
            preco_str = request.POST.get('preco_unitario', '0').replace(',', '.')
            estoque_str = request.POST.get('estoque_metros', '0').replace(',', '.')

            try:
                preco_val = float(preco_str or 0)
            except ValueError:
                preco_val = float(mp.preco_unitario)

            try:
                estoque_val = float(estoque_str or 0)
            except ValueError:
                estoque_val = float(mp.estoque_metros)

            if novo_nome:
                mp.nome = novo_nome
            mp.codigo = codigo
            mp.fornecedor = fornecedor
            mp.composicao = composicao
            mp.unidade_medida = unidade
            mp.preco_unitario = preco_val
            mp.estoque_metros = estoque_val
            mp.save()

            afetados = mp.recalcular_produtos()
            messages.success(
                request,
                f'Matéria-prima "{mp.nome}" alterada! Preço: R$ {preco_val:.4f}/{unidade}. O custo de {afetados} produto(s) foi recalculado automaticamente!'
            )
            return redirect('materias_primas')

        elif acao == 'atualizar_preco_rapido':
            mp_id = request.POST.get('mp_id')
            mp = get_object_or_404(MateriaPrima, pk=mp_id)
            preco_str = request.POST.get('preco_unitario', '0').replace(',', '.')
            try:
                preco_val = float(preco_str or 0)
            except ValueError:
                preco_val = float(mp.preco_unitario)

            preco_antigo = float(mp.preco_unitario)
            mp.preco_unitario = preco_val
            mp.save()
            afetados = mp.recalcular_produtos()
            messages.success(
                request,
                f'Preço de "{mp.nome}" atualizado de R$ {preco_antigo:.4f} para R$ {preco_val:.4f}/{mp.unidade_medida}. O custo de {afetados} produto(s) foi recalculado!'
            )
            return redirect('materias_primas')

        elif acao == 'excluir':
            mp_id = request.POST.get('mp_id')
            mp = get_object_or_404(MateriaPrima, pk=mp_id)
            nome = mp.nome
            em_uso = mp.itens_consumo.count()
            if em_uso > 0:
                messages.warning(
                    request,
                    f'Atenção: A matéria-prima "{nome}" está sendo utilizada em {em_uso} ficha(s) técnica(s). Foi marcada como inativa.'
                )
                mp.ativo = False
                mp.save()
            else:
                mp.delete()
                messages.success(request, f'Matéria-prima "{nome}" excluída com sucesso.')
            return redirect('materias_primas')

        elif acao == 'recalcular_todos':
            total_prods = 0
            for p in Produto.objects.all():
                p.recalcular_custos()
                total_prods += 1
            messages.success(request, f'Custos de matéria-prima de todos os {total_prods} produtos foram recalculados com sucesso!')
            return redirect('materias_primas')

    # GET
    filtro_grupo = request.GET.get('grupo', 'todos').strip()
    busca = request.GET.get('q', '').strip()

    mps_qs = MateriaPrima.objects.filter(ativo=True)
    if filtro_grupo and filtro_grupo != 'todos':
        mps_qs = mps_qs.filter(codigo__iexact=filtro_grupo)

    if busca:
        mps_qs = mps_qs.filter(
            Q(nome__icontains=busca) |
            Q(codigo__icontains=busca) |
            Q(fornecedor__icontains=busca) |
            Q(composicao__icontains=busca)
        )

    materias_primas = list(mps_qs.order_by('codigo', 'nome'))

    # Anexa dados de relacionamento para cada matéria-prima
    for mp in materias_primas:
        itens = mp.itens_consumo.select_related('produto').all()
        mp.produtos_afetados = [it.produto for it in itens]
        mp.produtos_count = len(mp.produtos_afetados)

    # Métricas KPIs
    total_mps = MateriaPrima.objects.filter(ativo=True).count()
    total_tecidos = MateriaPrima.objects.filter(ativo=True, codigo__iexact='TECIDO').count()
    total_aviamentos = MateriaPrima.objects.filter(ativo=True).filter(
        Q(codigo__icontains='AVIAMENTO') | Q(codigo__icontains='ACESSÓRIO') | Q(codigo__icontains='ACESSORIO')
    ).count()
    grupos_disponiveis = MateriaPrima.objects.filter(ativo=True).values_list('codigo', flat=True).distinct().order_by('codigo')
    grupos = [g for g in grupos_disponiveis if g]

    context = {
        'materias_primas': materias_primas,
        'total_mps': total_mps,
        'total_tecidos': total_tecidos,
        'total_aviamentos': total_aviamentos,
        'grupos': grupos,
        'filtro_grupo': filtro_grupo,
        'busca': busca,
    }
    return render(request, 'fabrica/materias_primas.html', context)




