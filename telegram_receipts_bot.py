"""
Telegram Receipts Bot
File: telegram_receipts_bot.py

Descrição: Bot profissional para cadastro de pedidos, busca por Nome/CPF/ID,
geração de comprovante em PDF profissional e envio pelo Telegram.

Instalação:
    $ python -m venv venv
    $ source venv/bin/activate  # Linux/Mac
    $ venv\\Scripts\\activate     # Windows
    $ pip install --upgrade pip
    $ pip install python-telegram-bot==20.6 python-dotenv reportlab

Arquivo .env (coloque na mesma pasta):
    TELEGRAM_TOKEN=seu_bot_token_aqui
    ADMIN_ID=seu_id_numérico_para_admin

Funcionalidades principais:
    /start - informa comandos
    /add_pedido - inicia diálogo para adicionar pedido
    /buscar - busca por Nome/CPF/ID
    /listar - lista últimos pedidos
    /pdf <id_do_pedido> - gera e envia comprovante em PDF do pedido
"""

import io
import os
import re
import sqlite3
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ========== CONFIGURAÇÃO ==========
load_dotenv()

TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) if os.getenv('ADMIN_ID') else None
DB_PATH = 'receipts.db'

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados da conversação
(
    ASK_ID,
    ASK_CPF,
    ASK_NAME,
    ASK_PRODUCT,
    ASK_VALUE,
    ASK_DISCOUNT,
    ASK_ECONOMY,
    ASK_TRANSID,
    ASK_DATE_CONFIRM
) = range(9)


# ========== VALIDAÇÕES ==========
def validate_cpf(cpf: str) -> bool:
    """Valida formato básico de CPF (apenas números, 11 dígitos)"""
    if not cpf:
        return True  # CPF é opcional
    cpf_numbers = re.sub(r'[^0-9]', '', cpf)
    return len(cpf_numbers) == 11


def validate_value(value_str: str) -> Optional[float]:
    """Valida e converte string para float (valor monetário)"""
    try:
        value = float(value_str.replace(',', '.').replace('R$', '').strip())
        return round(value, 2) if value >= 0 else None
    except (ValueError, AttributeError):
        return None


def validate_date(date_str: str) -> Optional[str]:
    """Valida formato de data DD/MM/YYYY HH:MM:SS"""
    if date_str.lower() == 'agora':
        return datetime.now().strftime('%d/%m/%Y %H:%M:%S')

    try:
        # Tenta parsear a data
        dt = datetime.strptime(date_str, '%d/%m/%Y %H:%M:%S')
        return dt.strftime('%d/%m/%Y %H:%M:%S')
    except ValueError:
        return None


def sanitize_input(text: str, max_length: int = 255) -> str:
    """Sanitiza input do usuário para prevenir SQL injection e XSS"""
    if not text:
        return ""
    # Remove caracteres especiais perigosos
    sanitized = text.strip()[:max_length]
    return sanitized


# ========== DATABASE ==========
def init_db():
    """Inicializa o banco de dados SQLite"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            CREATE TABLE IF NOT EXISTS pedidos (
                id TEXT PRIMARY KEY,
                cpf TEXT,
                nome TEXT NOT NULL,
                produto TEXT NOT NULL,
                valor REAL NOT NULL,
                desconto REAL DEFAULT 0,
                economia REAL DEFAULT 0,
                status TEXT DEFAULT 'pendente',
                created_at TEXT NOT NULL,
                trans_id TEXT,
                updated_at TEXT
            )
        ''')

        # Criar índices para melhor performance
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_cpf ON pedidos(cpf)
        ''')
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_nome ON pedidos(nome)
        ''')
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at ON pedidos(created_at DESC)
        ''')

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise


def add_pedido_db(pedido: Dict) -> bool:
    """Adiciona um novo pedido ao banco de dados"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO pedidos (
                id, cpf, nome, produto, valor, desconto, economia,
                status, created_at, trans_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            pedido['id'],
            pedido.get('cpf', ''),
            pedido.get('nome', ''),
            pedido.get('produto', ''),
            pedido.get('valor', 0.0),
            pedido.get('desconto', 0.0),
            pedido.get('economia', 0.0),
            pedido.get('status', 'pendente'),
            pedido.get('created_at', datetime.now().strftime('%d/%m/%Y %H:%M:%S')),
            pedido.get('trans_id', ''),
            datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ))
        conn.commit()
        conn.close()
        logger.info(f"Order {pedido['id']} added successfully")
        return True
    except Exception as e:
        logger.error(f"Error adding order to database: {e}")
        return False


def get_pedido_by_id(pid: str) -> Optional[Dict]:
    """Busca um pedido pelo ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('SELECT * FROM pedidos WHERE id = ?', (pid,))
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        keys = [
            'id', 'cpf', 'nome', 'produto', 'valor', 'desconto',
            'economia', 'status', 'created_at', 'trans_id', 'updated_at'
        ]
        return dict(zip(keys, row))
    except Exception as e:
        logger.error(f"Error fetching order {pid}: {e}")
        return None


def search_pedidos(term: str, limit: int = 20) -> List[Dict]:
    """Busca pedidos por termo (ID, CPF ou Nome)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        like_term = f"%{term}%"
        cur.execute('''
            SELECT * FROM pedidos
            WHERE id LIKE ? OR cpf LIKE ? OR nome LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (like_term, like_term, like_term, limit))
        rows = cur.fetchall()
        conn.close()

        keys = [
            'id', 'cpf', 'nome', 'produto', 'valor', 'desconto',
            'economia', 'status', 'created_at', 'trans_id', 'updated_at'
        ]
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        logger.error(f"Error searching orders: {e}")
        return []


def list_recent(limit: int = 10) -> List[Dict]:
    """Lista os pedidos mais recentes"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            'SELECT * FROM pedidos ORDER BY created_at DESC LIMIT ?',
            (limit,)
        )
        rows = cur.fetchall()
        conn.close()

        keys = [
            'id', 'cpf', 'nome', 'produto', 'valor', 'desconto',
            'economia', 'status', 'created_at', 'trans_id', 'updated_at'
        ]
        return [dict(zip(keys, r)) for r in rows]
    except Exception as e:
        logger.error(f"Error listing recent orders: {e}")
        return []


def update_pedido_status(pid: str, status: str) -> bool:
    """Atualiza o status de um pedido"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            'UPDATE pedidos SET status = ?, updated_at = ? WHERE id = ?',
            (status, datetime.now().strftime('%d/%m/%Y %H:%M:%S'), pid)
        )
        conn.commit()
        conn.close()
        logger.info(f"Order {pid} status updated to {status}")
        return True
    except Exception as e:
        logger.error(f"Error updating order status: {e}")
        return False


# ========== PDF GENERATION ==========
def generate_pdf_bytes(pedido: Dict) -> bytes:
    """Gera um PDF profissional com os dados do pedido"""
    buffer = io.BytesIO()

    # Configuração do documento
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm
    )

    styles = getSampleStyleSheet()
    style_normal = styles['Normal']
    style_heading = styles['Heading1']

    style_title = ParagraphStyle(
        'Title',
        parent=style_heading,
        alignment=1,  # Center
        fontSize=18,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12
    )

    style_subtitle = ParagraphStyle(
        'Subtitle',
        parent=style_normal,
        alignment=1,  # Center
        fontSize=10,
        textColor=colors.HexColor('#7f8c8d')
    )

    flow = []

    # Cabeçalho
    flow.append(Paragraph('COMPROVANTE DE PEDIDO', style_title))
    flow.append(Spacer(1, 6 * mm))

    # Data/Hora
    dt = pedido.get('created_at', datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
    flow.append(Paragraph(f'<b>Data/Hora:</b> {dt}', style_subtitle))
    flow.append(Spacer(1, 10 * mm))

    # Tabela com informações do pedido
    data = [
        ['Campo', 'Valor'],
        ['ID do Pedido', pedido.get('id', 'N/A')],
        ['ID da Transação', pedido.get('trans_id', 'N/A')],
        ['Nome do Cliente', pedido.get('nome', 'N/A')],
        ['CPF', pedido.get('cpf', 'N/A')],
        ['Produto', pedido.get('produto', 'N/A')],
        ['Valor Original', f"R$ {pedido.get('valor', 0):.2f}"],
        ['Desconto', f"R$ {pedido.get('desconto', 0):.2f}"],
        ['Economia', f"R$ {pedido.get('economia', 0):.2f}"],
        ['Valor Final', f"R$ {(pedido.get('valor', 0) - pedido.get('desconto', 0)):.2f}"],
        ['Status', pedido.get('status', 'N/A').upper()],
    ]

    table = Table(data, colWidths=[70 * mm, 90 * mm])
    table.setStyle(TableStyle([
        # Cabeçalho
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),

        # Corpo
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#ecf0f1')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ROWBACKGROUNDS', (1, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),

        # Bordas
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))

    flow.append(table)
    flow.append(Spacer(1, 15 * mm))

    # Rodapé
    footer_style = ParagraphStyle(
        'Footer',
        parent=style_normal,
        fontSize=8,
        textColor=colors.HexColor('#95a5a6'),
        alignment=1
    )

    flow.append(Spacer(1, 10 * mm))
    flow.append(Paragraph(
        'Este comprovante foi gerado automaticamente pelo sistema e contém '
        'as informações registradas no momento do cadastro.',
        footer_style
    ))
    flow.append(Spacer(1, 8 * mm))
    flow.append(Paragraph('_' * 50, footer_style))
    flow.append(Paragraph('Assinatura', footer_style))

    # Construir PDF
    doc.build(flow)
    pdf_value = buffer.getvalue()
    buffer.close()

    return pdf_value


# ========== BOT HANDLERS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /start"""
    welcome_text = (
        '🤖 *Bot de Gerenciamento de Pedidos*\n\n'
        '*Comandos disponíveis:*\n'
        '/start - Exibir esta mensagem\n'
        '/add\\_pedido - Cadastrar novo pedido\n'
        '/buscar - Buscar pedido por Nome/CPF/ID\n'
        '/listar - Listar últimos pedidos\n'
        '/pdf <id> - Gerar PDF de um pedido\n'
        '/cancel - Cancelar operação atual\n\n'
        '_Desenvolvido com Python e ReportLab_'
    )
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown'
    )


# ===== CONVERSATION HANDLERS: ADD PEDIDO =====
async def add_pedido_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia o processo de adicionar um novo pedido"""
    # Verificar se é admin (se configurado)
    if ADMIN_ID and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            '❌ Acesso negado. Apenas administradores podem adicionar pedidos.'
        )
        return ConversationHandler.END

    await update.message.reply_text(
        '📝 *Cadastro de Novo Pedido*\n\n'
        'Digite o *ID do pedido* ou envie "gerar" para criar um ID automático:',
        parse_mode='Markdown'
    )
    return ASK_ID


async def add_pedido_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o ID do pedido"""
    text = sanitize_input(update.message.text.strip())

    if text.lower() == 'gerar':
        pid = str(uuid.uuid4())
        await update.message.reply_text(f'✅ ID gerado: `{pid}`', parse_mode='Markdown')
    else:
        # Verificar se o ID já existe
        existing = get_pedido_by_id(text)
        if existing:
            await update.message.reply_text(
                '❌ Este ID já existe no sistema. Digite outro ID ou "gerar":'
            )
            return ASK_ID
        pid = text

    context.user_data['pedido'] = {'id': pid}
    await update.message.reply_text(
        '📋 Digite o *CPF* do cliente (apenas números) ou "pular" para deixar em branco:',
        parse_mode='Markdown'
    )
    return ASK_CPF


async def add_pedido_cpf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o CPF do cliente"""
    text = sanitize_input(update.message.text.strip())

    if text.lower() == 'pular':
        context.user_data['pedido']['cpf'] = ''
    else:
        if not validate_cpf(text):
            await update.message.reply_text(
                '❌ CPF inválido. Digite 11 números ou "pular":'
            )
            return ASK_CPF
        context.user_data['pedido']['cpf'] = re.sub(r'[^0-9]', '', text)

    await update.message.reply_text('👤 Digite o *NOME COMPLETO* do cliente:', parse_mode='Markdown')
    return ASK_NAME


async def add_pedido_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o nome do cliente"""
    text = sanitize_input(update.message.text.strip(), max_length=200)

    if len(text) < 3:
        await update.message.reply_text('❌ Nome muito curto. Digite o nome completo:')
        return ASK_NAME

    context.user_data['pedido']['nome'] = text
    await update.message.reply_text('📦 Digite o *NOME/DESCRIÇÃO* do produto:', parse_mode='Markdown')
    return ASK_PRODUCT


async def add_pedido_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o nome do produto"""
    text = sanitize_input(update.message.text.strip(), max_length=300)

    if len(text) < 3:
        await update.message.reply_text('❌ Descrição muito curta. Digite novamente:')
        return ASK_PRODUCT

    context.user_data['pedido']['produto'] = text
    await update.message.reply_text('💰 Digite o *VALOR* do produto (ex: 89.90 ou 89,90):', parse_mode='Markdown')
    return ASK_VALUE


async def add_pedido_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o valor do produto"""
    value = validate_value(update.message.text)

    if value is None:
        await update.message.reply_text('❌ Valor inválido. Digite um número válido (ex: 89.90):')
        return ASK_VALUE

    context.user_data['pedido']['valor'] = value
    await update.message.reply_text(
        '🏷️ Digite o valor do *DESCONTO* (0 se não houver, ex: 8.99):',
        parse_mode='Markdown'
    )
    return ASK_DISCOUNT


async def add_pedido_discount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o desconto"""
    discount = validate_value(update.message.text)

    if discount is None:
        await update.message.reply_text('❌ Valor inválido. Digite um número válido (ex: 8.99 ou 0):')
        return ASK_DISCOUNT

    valor = context.user_data['pedido']['valor']
    if discount > valor:
        await update.message.reply_text('❌ O desconto não pode ser maior que o valor. Digite novamente:')
        return ASK_DISCOUNT

    context.user_data['pedido']['desconto'] = discount
    context.user_data['pedido']['economia'] = discount

    await update.message.reply_text(
        '🔖 Digite o *ID da transação* (se houver) ou "pular":',
        parse_mode='Markdown'
    )
    return ASK_TRANSID


async def add_pedido_transid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o ID da transação"""
    text = sanitize_input(update.message.text.strip())

    if text.lower() == 'pular':
        context.user_data['pedido']['trans_id'] = ''
    else:
        context.user_data['pedido']['trans_id'] = text

    await update.message.reply_text(
        '📅 Digite a *DATA/HORA* (formato: DD/MM/YYYY HH:MM:SS)\n'
        'ou envie "agora" para usar o horário atual:',
        parse_mode='Markdown'
    )
    return ASK_DATE_CONFIRM


async def add_pedido_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe a data e finaliza o cadastro"""
    text = update.message.text.strip()

    date_validated = validate_date(text)
    if not date_validated:
        await update.message.reply_text(
            '❌ Data inválida. Use o formato DD/MM/YYYY HH:MM:SS ou "agora":'
        )
        return ASK_DATE_CONFIRM

    context.user_data['pedido']['created_at'] = date_validated
    context.user_data['pedido']['status'] = 'pendente'

    # Salvar no banco
    success = add_pedido_db(context.user_data['pedido'])

    if success:
        pedido_id = context.user_data['pedido']['id']
        await update.message.reply_text(
            f'✅ *Pedido cadastrado com sucesso!*\n\n'
            f'ID: `{pedido_id}`\n'
            f'Use /pdf {pedido_id} para gerar o comprovante.',
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            '❌ Erro ao salvar o pedido. Tente novamente mais tarde.'
        )

    # Limpar dados temporários
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancela a operação atual"""
    context.user_data.clear()
    await update.message.reply_text(
        '❌ Operação cancelada.',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ===== BUSCAR PEDIDOS =====
async def buscar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /buscar"""
    args = context.args

    if not args:
        await update.message.reply_text(
            '🔍 *Buscar Pedido*\n\n'
            'Use: /buscar <termo>\n'
            'Exemplo: /buscar João Silva\n\n'
            'Você pode buscar por:\n'
            '• Nome do cliente\n'
            '• CPF\n'
            '• ID do pedido',
            parse_mode='Markdown'
        )
        return

    term = ' '.join(args)
    results = search_pedidos(term)

    if not results:
        await update.message.reply_text('❌ Nenhum pedido encontrado.')
        return

    await update.message.reply_text(f'📋 Encontrados *{len(results)}* pedido(s):', parse_mode='Markdown')

    for p in results[:10]:  # Limitar a 10 resultados
        valor_final = p['valor'] - p['desconto']
        resumo = (
            f"*ID:* `{p['id']}`\n"
            f"*Nome:* {p['nome']}\n"
            f"*CPF:* {p['cpf'] or 'N/A'}\n"
            f"*Produto:* {p['produto']}\n"
            f"*Valor:* R$ {p['valor']:.2f}\n"
            f"*Desconto:* R$ {p['desconto']:.2f}\n"
            f"*Valor Final:* R$ {valor_final:.2f}\n"
            f"*Status:* {p['status'].upper()}\n"
            f"*Data:* {p['created_at']}"
        )

        keyboard = [
            [InlineKeyboardButton('📄 Gerar PDF', callback_data=f"pdf|{p['id']}")],
            [InlineKeyboardButton('✅ Marcar Entregue', callback_data=f"markdel|{p['id']}")]
        ]

        await update.message.reply_text(
            resumo,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )


# ===== LISTAR PEDIDOS =====
async def listar_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /listar"""
    rows = list_recent(10)

    if not rows:
        await update.message.reply_text('📋 Ainda não há pedidos cadastrados.')
        return

    message = '📋 *Últimos 10 pedidos:*\n\n'

    for r in rows:
        valor_final = r['valor'] - r['desconto']
        message += (
            f"• ID: `{r['id'][:8]}...`\n"
            f"  Nome: {r['nome']}\n"
            f"  Valor: R$ {valor_final:.2f}\n"
            f"  Status: {r['status'].upper()}\n"
            f"  Data: {r['created_at']}\n\n"
        )

    await update.message.reply_text(message, parse_mode='Markdown')


# ===== GERAR PDF =====
async def pdf_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para o comando /pdf"""
    args = context.args

    if not args:
        await update.message.reply_text(
            '📄 *Gerar PDF*\n\n'
            'Use: /pdf <id\\_do\\_pedido>\n'
            'Exemplo: /pdf abc123',
            parse_mode='Markdown'
        )
        return

    pid = args[0]
    p = get_pedido_by_id(pid)

    if not p:
        await update.message.reply_text('❌ Pedido não encontrado.')
        return

    try:
        # Gerar PDF
        await update.message.reply_text('⏳ Gerando PDF...')
        pdf_bytes = generate_pdf_bytes(p)

        # Enviar documento
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=io.BytesIO(pdf_bytes),
            filename=f'comprovante_{pid}.pdf',
            caption=f'📄 Comprovante do pedido {pid}'
        )

        logger.info(f"PDF generated for order {pid}")
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        await update.message.reply_text('❌ Erro ao gerar PDF. Tente novamente.')


# ===== CALLBACK QUERIES =====
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para botões inline"""
    query = update.callback_query
    await query.answer()

    data = query.data

    # Gerar PDF
    if data.startswith('pdf|'):
        pid = data.split('|', 1)[1]
        p = get_pedido_by_id(pid)

        if not p:
            await query.edit_message_text('❌ Pedido não encontrado.')
            return

        try:
            pdf_bytes = generate_pdf_bytes(p)
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=io.BytesIO(pdf_bytes),
                filename=f'comprovante_{pid}.pdf',
                caption=f'📄 Comprovante do pedido {pid}'
            )
            await query.edit_message_text(
                f'{query.message.text}\n\n✅ PDF enviado!',
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error in callback PDF generation: {e}")
            await query.edit_message_text('❌ Erro ao gerar PDF.')
        return

    # Marcar como entregue
    if data.startswith('markdel|'):
        pid = data.split('|', 1)[1]
        success = update_pedido_status(pid, 'entregue')

        if success:
            await query.edit_message_text(
                f'{query.message.text.replace("PENDENTE", "ENTREGUE")}\n\n✅ Marcado como entregue!',
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text('❌ Erro ao atualizar status.')
        return


# ===== MAIN =====
def main():
    """Função principal"""
    # Verificar configurações
    if not TOKEN:
        logger.error("TELEGRAM_TOKEN not found in .env file")
        print("❌ Erro: TELEGRAM_TOKEN não encontrado no arquivo .env")
        return

    # Inicializar banco de dados
    try:
        init_db()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        print(f"❌ Erro ao inicializar banco de dados: {e}")
        return

    # Criar aplicação
    app = ApplicationBuilder().token(TOKEN).build()

    # Conversation handler para adicionar pedido
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('add_pedido', add_pedido_start)],
        states={
            ASK_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pedido_id)],
            ASK_CPF: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pedido_cpf)],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pedido_name)],
            ASK_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pedido_product)],
            ASK_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pedido_value)],
            ASK_DISCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pedido_discount)],
            ASK_TRANSID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pedido_transid)],
            ASK_DATE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_pedido_date)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Adicionar handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('buscar', buscar_cmd))
    app.add_handler(CommandHandler('listar', listar_cmd))
    app.add_handler(CommandHandler('pdf', pdf_cmd))
    app.add_handler(CallbackQueryHandler(callbacks))

    # Iniciar bot
    print('✅ Bot iniciado com sucesso!')
    print('📱 Aguardando mensagens...')
    logger.info("Bot started successfully")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
