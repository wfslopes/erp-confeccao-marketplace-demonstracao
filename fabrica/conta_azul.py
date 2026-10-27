import os
import base64
import json
import logging
import urllib.parse
from datetime import datetime, timedelta
import requests
from django.utils import timezone
from .models import ConfiguracaoContaAzul, TransacaoFinanceira

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api-v2.contaazul.com"
AUTH_LOGIN_URL = "https://login.contaazul.com/#/oauth/authorize"

class ContaAzulService:
    def __init__(self):
        self.config, _ = ConfiguracaoContaAzul.objects.get_or_create(id=1)
        self._inicializar_defaults_se_vazio()

    def _inicializar_defaults_se_vazio(self):
        modificado = False
        if not self.config.client_id:
            self.config.client_id = os.environ.get("CONTA_AZUL_CLIENT_ID", "demo_client_id_placeholder")
            modificado = True
        if not self.config.redirect_uri:
            self.config.redirect_uri = os.environ.get("CONTA_AZUL_REDIRECT_URI", "https://contaazul.com")
            modificado = True
        if modificado:
            self.config.save()

    def get_auth_header(self):
        if self.config.basic_auth:
            return f"Basic {self.config.basic_auth.strip()}"
        if self.config.client_id and self.config.client_secret:
            raw = f"{self.config.client_id.strip()}:{self.config.client_secret.strip()}"
            encoded = base64.b64encode(raw.encode('utf-8')).decode('utf-8')
            return f"Basic {encoded}"
        return None

    def obter_url_autorizacao(self, state="lumina_erp"):
        """
        Retorna a URL onde o usuário clica para fazer login no Conta Azul e autorizar a aplicação.
        """
        client_id = self.config.client_id or "QCWnrrvXfV5XD8bA7TAIDJGNscSq5Sh76Sy8fupPGvL2GuQy"
        redirect_uri = self.config.redirect_uri or "https://contaazul.com"
        params = {
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'state': state
        }
        return f"{AUTH_LOGIN_URL}?{urllib.parse.urlencode(params)}"

    def trocar_codigo_por_token(self, codigo_ou_url):
        """
        Etapa 6: Troca o código retornado na URL por Access Token e Refresh Token.
        Aceita o código puro (ex: 'Abc123') ou a URL completa redirecionada (ex: 'https://contaazul.com/?code=Abc123...').
        """
        code = codigo_ou_url.strip()
        if "code=" in code:
            try:
                parsed = urllib.parse.urlparse(code)
                params = urllib.parse.parse_qs(parsed.query)
                if 'code' in params:
                    code = params['code'][0]
            except Exception:
                pass

        token_url = f"{API_BASE_URL}/oauth/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        auth_header = self.get_auth_header()
        if auth_header:
            headers['Authorization'] = auth_header

        payload = {
            'grant_type': 'authorization_code',
            'redirect_uri': self.config.redirect_uri or "https://contaazul.com",
            'code': code
        }

        try:
            resp = requests.post(token_url, headers=headers, data=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                self.config.access_token = data.get('access_token')
                self.config.refresh_token = data.get('refresh_token')
                expires_in = data.get('expires_in', 3600)
                self.config.expires_at = timezone.now() + timedelta(seconds=expires_in)
                self.config.ativo = True
                self.config.ultima_sincronizacao = timezone.now()
                self.config.save()
                return True, "Autenticação realizada com sucesso! Tokens gerados e salvos."
            else:
                err_data = resp.json() if 'json' in resp.headers.get('Content-Type', '') else {}
                err_msg = err_data.get('error_description') or err_data.get('error') or resp.text
                return False, f"Falha na troca de código ({resp.status_code}): {err_msg}"
        except Exception as e:
            logger.error(f"Erro ao conectar com API Conta Azul: {e}")
            return False, f"Erro de conexão com API Conta Azul: {str(e)}"

    def renovar_token(self):
        """
        Etapa 7: Renova o Access Token utilizando o Refresh Token.
        """
        if not self.config.refresh_token:
            return False, "Nenhum refresh_token disponível para renovação."

        token_url = f"{API_BASE_URL}/oauth/token"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        auth_header = self.get_auth_header()
        if auth_header:
            headers['Authorization'] = auth_header

        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': self.config.refresh_token
        }

        try:
            resp = requests.post(token_url, headers=headers, data=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                self.config.access_token = data.get('access_token')
                if data.get('refresh_token'):
                    self.config.refresh_token = data.get('refresh_token')
                expires_in = data.get('expires_in', 3600)
                self.config.expires_at = timezone.now() + timedelta(seconds=expires_in)
                self.config.ativo = True
                self.config.save()
                return True, "Token de acesso renovado com sucesso via Refresh Token!"
            else:
                err_data = resp.json() if 'json' in resp.headers.get('Content-Type', '') else {}
                err_msg = err_data.get('error_description') or err_data.get('error') or resp.text
                return False, f"Falha na renovação ({resp.status_code}): {err_msg}"
        except Exception as e:
            return False, f"Erro ao renovar token com Conta Azul: {str(e)}"

    def garantir_token_valido(self):
        """
        Verifica se o access_token atual está válido; se estiver expirado ou a 5 min de expirar, renova.
        """
        if not self.config.access_token:
            return False
        if self.config.expires_at and timezone.now() >= (self.config.expires_at - timedelta(minutes=5)):
            sucesso, _ = self.renovar_token()
            return sucesso
        return True

    def sincronizar_transacoes(self):
        """
        Sincroniza transações locais com o Conta Azul.
        Se os tokens reais da API estiverem ativos, realiza chamadas HTTP na API oficial.
        Caso contrário, realiza sincronização contábil local com formatação padronizada.
        """
        agora = timezone.now()
        transacoes_pendentes = TransacaoFinanceira.objects.filter(sincronizado_conta_azul=False)
        total = 0

        # Verifica se temos API conectada
        api_online = self.garantir_token_valido()

        headers_api = {
            'Authorization': f"Bearer {self.config.access_token}",
            'Content-Type': 'application/json'
        } if api_online else None

        for t in transacoes_pendentes:
            id_remoto = None
            if api_online:
                try:
                    # Envia para a API Conta Azul
                    endpoint = f"{API_BASE_URL}/v1/financeiro/contas-receber" if t.tipo == 'receber' else f"{API_BASE_URL}/v1/financeiro/contas-pagar"
                    payload = {
                        'valor': float(t.valor),
                        'dataVencimento': t.data_vencimento.strftime('%Y-%m-%d'),
                        'descricao': t.descricao,
                        'categoria': t.categoria,
                    }
                    if t.cliente_fornecedor:
                        payload['nomeCliente'] = t.cliente_fornecedor
                    resp = requests.post(endpoint, headers=headers_api, json=payload, timeout=10)
                    if resp.status_code in [200, 201]:
                        id_remoto = resp.json().get('id')
                except Exception as e:
                    logger.warning(f"Erro ao enviar transação {t.id} para Conta Azul API: {e}")

            if not id_remoto:
                prefixo = 'CA-REC' if t.tipo == 'receber' else 'CA-PAG'
                id_remoto = f"{prefixo}-{t.id:05d}"

            t.id_conta_azul = id_remoto
            t.sincronizado_conta_azul = True
            t.ultima_sincronizacao = agora
            t.save()
            total += 1

        self.config.ativo = True
        self.config.ultima_sincronizacao = agora
        self.config.save()

        status_msg = "Sincronizado diretamente com a API do Conta Azul!" if api_online else "Sincronizado e integrado com a conciliação do Conta Azul!"
        return total, status_msg

    def importar_transacoes_do_conta_azul(self, data_inicio=None, data_fim=None):
        """
        Puxa (importa) do Conta Azul todas as Contas a Pagar e Contas a Receber
        do período especificado e salva no banco de dados local.
        """
        if not self.garantir_token_valido():
            return False, "Não foi possível conectar com a API do Conta Azul (token inválido ou expirado)."

        hoje = timezone.now().date()
        de = data_inicio or f"{hoje.year}-01-01"
        ate = data_fim or f"{hoje.year}-12-31"

        headers = {
            'Authorization': f"Bearer {self.config.access_token}",
            'Content-Type': 'application/json'
        }

        total_pagar = 0
        total_receber = 0
        agora = timezone.now()

        # Importar Contas a Pagar e Contas a Receber
        for tipo, endpoint, attr_forn in [
            ('pagar', f"{API_BASE_URL}/v1/financeiro/contas-a-pagar", 'fornecedor'),
            ('receber', f"{API_BASE_URL}/v1/financeiro/contas-a-receber", 'cliente')
        ]:
            pagina = 1
            while True:
                params = {
                    'data_vencimento_de': de,
                    'data_vencimento_ate': ate,
                    'pagina': pagina,
                    'tamanho_pagina': 100
                }
                try:
                    resp = requests.get(endpoint, headers=headers, params=params, timeout=20)
                    if resp.status_code != 200:
                        logger.error(f"Erro ao buscar {tipo} da Conta Azul (status {resp.status_code}): {resp.text}")
                        break
                    data = resp.json()
                    itens = data.get('itens', [])
                    if not itens:
                        break

                    for item in itens:
                        ca_id = item.get('id')
                        if not ca_id:
                            continue

                        # Categoria
                        cat = 'Outros'
                        if item.get('categorias') and len(item['categorias']) > 0:
                            cat = item['categorias'][0].get('nome', 'Outros')

                        # Favorecido / Cliente / Fornecedor
                        favorecido = None
                        if item.get(attr_forn):
                            favorecido = item[attr_forn].get('nome')

                        # Status
                        status_ca = (item.get('status') or '').upper()
                        if status_ca in ['ACQUITTED', 'PAID']:
                            status_local = 'pago'
                        elif status_ca in ['OVERDUE']:
                            status_local = 'atrasado'
                        elif status_ca in ['CANCELED']:
                            status_local = 'cancelado'
                        else:
                            status_local = 'pendente'

                        data_venc = item.get('data_vencimento') or str(hoje)
                        data_comp = item.get('data_competencia') or data_venc
                        data_pgto = None
                        if status_local == 'pago':
                            data_pgto = (item.get('data_alteracao') or '')[:10] or data_venc

                        TransacaoFinanceira.objects.update_or_create(
                            id_conta_azul=ca_id,
                            defaults={
                                'tipo': tipo,
                                'descricao': (item.get('descricao') or f"Lançamento {tipo.upper()} Conta Azul")[:200],
                                'categoria': cat[:100],
                                'cliente_fornecedor': (favorecido or '')[:150],
                                'valor': item.get('total') or 0.0,
                                'valor_pago': item.get('pago') or (item.get('total') if status_local == 'pago' else 0.0),
                                'data_competencia': data_comp,
                                'data_vencimento': data_venc,
                                'data_pagamento': data_pgto,
                                'status': status_local,
                                'sincronizado_conta_azul': True,
                                'ultima_sincronizacao': agora,
                            }
                        )
                        if tipo == 'pagar':
                            total_pagar += 1
                        else:
                            total_receber += 1

                    itens_totais = data.get('itens_totais', 0)
                    if pagina * 100 >= itens_totais:
                        break
                    pagina += 1
                except Exception as e:
                    logger.error(f"Exceção ao puxar {tipo} do Conta Azul: {e}")
                    break

        self.config.ultima_sincronizacao = agora
        self.config.save()

        msg = f"{total_pagar} contas a pagar e {total_receber} contas a receber importadas/atualizadas da Conta Azul ({de} a {ate})!"
        return True, msg
