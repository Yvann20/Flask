# Telegram Receipts Bot

Bot profissional para gerenciamento de pedidos via Telegram com geração de comprovantes em PDF.

## Características

- ✅ Cadastro completo de pedidos com validação de dados
- 🔍 Busca avançada por Nome, CPF ou ID
- 📄 Geração de comprovantes em PDF profissional
- 🔐 Controle de acesso por admin
- 💾 Banco de dados SQLite
- 📊 Listagem de pedidos recentes
- ⚡ Interface com botões interativos

## Instalação

### 1. Requisitos

- Python 3.8 ou superior
- pip (gerenciador de pacotes Python)

### 2. Configuração

```bash
# Clone ou baixe o projeto
cd telegram_receipts_bot

# Crie um ambiente virtual (recomendado)
python -m venv venv

# Ative o ambiente virtual
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt
```

### 3. Configuração do Bot

1. Abra o Telegram e procure por `@BotFather`
2. Envie `/newbot` e siga as instruções
3. Copie o token gerado

4. Crie o arquivo `.env` na pasta do projeto:

```bash
cp .env.example .env
```

5. Edite o arquivo `.env` e adicione seu token:

```
TELEGRAM_TOKEN=seu_token_aqui
ADMIN_ID=seu_id_telegram
```

**Para descobrir seu ID do Telegram:**
- Envie uma mensagem para `@userinfobot` no Telegram

## Uso

### Iniciar o Bot

```bash
python telegram_receipts_bot.py
```

### Comandos Disponíveis

- `/start` - Exibe mensagem de boas-vindas e lista de comandos
- `/add_pedido` - Inicia processo de cadastro de pedido (somente admin)
- `/buscar <termo>` - Busca pedidos por nome, CPF ou ID
- `/listar` - Lista os 10 últimos pedidos
- `/pdf <id>` - Gera e envia PDF de um pedido específico
- `/cancel` - Cancela operação atual

### Exemplo de Uso

1. **Cadastrar pedido:**
   ```
   /add_pedido
   ```
   O bot irá guiá-lo através de um diálogo interativo.

2. **Buscar pedido:**
   ```
   /buscar João Silva
   /buscar 123.456.789-00
   /buscar abc-123-xyz
   ```

3. **Gerar PDF:**
   ```
   /pdf abc-123-xyz
   ```

## Estrutura do Banco de Dados

O bot utiliza SQLite para armazenar os dados. A tabela `pedidos` contém:

- `id` - ID único do pedido (PRIMARY KEY)
- `cpf` - CPF do cliente
- `nome` - Nome completo do cliente
- `produto` - Nome/descrição do produto
- `valor` - Valor original
- `desconto` - Valor do desconto aplicado
- `economia` - Economia total
- `status` - Status do pedido (pendente/entregue)
- `created_at` - Data/hora de criação
- `trans_id` - ID da transação (opcional)
- `updated_at` - Data/hora da última atualização

## Segurança

✅ **Implementado:**
- Validação de CPF
- Sanitização de inputs
- Controle de acesso por admin
- Logging de operações
- Prevenção de SQL injection
- Validação de valores monetários

⚠️ **Recomendações:**
- Mantenha o arquivo `.env` seguro (não compartilhe)
- Use apenas em servidores confiáveis
- Faça backup regular do arquivo `receipts.db`

## Manutenção

### Backup do Banco de Dados

```bash
cp receipts.db receipts.db.backup
```

### Logs

O bot registra todas as operações importantes no console e pode ser configurado para salvar em arquivo.

## Troubleshooting

### Erro: "TELEGRAM_TOKEN not found"
- Verifique se o arquivo `.env` existe
- Confirme que o token está correto

### Erro: "Database locked"
- Certifique-se de que apenas uma instância do bot está rodando
- Feche qualquer conexão aberta ao banco de dados

### Erro ao gerar PDF
- Verifique se o ReportLab está instalado corretamente
- Execute: `pip install --upgrade reportlab`

## Desenvolvimento

### Estrutura do Código

```
telegram_receipts_bot.py
├── Configuração e imports
├── Validações (validate_cpf, validate_value, etc.)
├── Funções de banco de dados (init_db, add_pedido_db, etc.)
├── Geração de PDF (generate_pdf_bytes)
├── Handlers de comandos (/start, /add_pedido, etc.)
├── Handlers de conversação (add_pedido_*)
└── Main (inicialização e polling)
```

### Melhorias Futuras

- [ ] Exportação em Excel
- [ ] Envio de notificações automáticas
- [ ] Dashboard web
- [ ] Relatórios estatísticos
- [ ] Integração com APIs de pagamento
- [ ] Múltiplos idiomas

## Licença

Este projeto é fornecido "como está" para fins educacionais e profissionais.

## Suporte

Para questões e suporte, abra uma issue no repositório ou entre em contato.

---

**Desenvolvido com ❤️ usando Python, python-telegram-bot e ReportLab**
