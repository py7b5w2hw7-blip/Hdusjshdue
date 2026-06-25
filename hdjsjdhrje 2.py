import asyncio
import os
from telethon import TelegramClient
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# ================== КОНФИГ ИЗ .ENV ==================
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID', 2040))
API_HASH = os.getenv('API_HASH', 'b18441a1ff607e10a989891a5462e627')
SESSION_NAME = 'user_session'
# =====================================================

# Глобальные переменные
client = None
unread_chats = []
pending_action = {}

# ================== ФУНКЦИИ ДЛЯ РАБОТЫ С АККАУНТОМ ==================
async def login_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вход в аккаунт через Telethon"""
    global client
    chat_id = update.effective_chat.id
    
    if client is None:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    try:
        # Пытаемся авторизоваться (если сессия есть — войдёт автоматически)
        await client.start()
        await context.bot.send_message(chat_id, "✅ Аккаунт уже авторизован! Используй /reply_all")
        return
    except:
        pass
    
    # Если сессии нет — запрашиваем номер телефона
    pending_action[chat_id] = 'awaiting_phone'
    await context.bot.send_message(chat_id, "📱 Введите номер телефона в формате +79991234567")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает сообщения от пользователя (номер, код, сообщение для рассылки)"""
    global client, unread_chats
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    # Если это не личный чат — игнорируем
    if update.effective_chat.type != 'private':
        return
    
    # Проверяем, ждём ли мы номер телефона
    if pending_action.get(chat_id) == 'awaiting_phone':
        pending_action[chat_id] = 'awaiting_code'
        try:
            await client.start(phone=text)
            # Если авторизация прошла без кода (сессия уже есть)
            if await client.is_user_authorized():
                await context.bot.send_message(chat_id, "✅ Аккаунт успешно добавлен! Используй /reply_all")
                pending_action.pop(chat_id, None)
                return
        except Exception as e:
            pass
        await context.bot.send_message(chat_id, "🔑 Введите код подтверждения из Telegram:")
        return
    
    # Проверяем, ждём ли мы код
    if pending_action.get(chat_id) == 'awaiting_code':
        try:
            await client.sign_in(code=text)
            await context.bot.send_message(chat_id, "✅ Аккаунт успешно добавлен! Используй /reply_all")
            pending_action.pop(chat_id, None)
        except Exception as e:
            await context.bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")
            pending_action.pop(chat_id, None)
        return
    
    # Проверяем, ждём ли мы сообщение для рассылки
    if pending_action.get(chat_id) == 'awaiting_message':
        if text.lower() == '/cancel':
            pending_action.pop(chat_id, None)
            await context.bot.send_message(chat_id, "❌ Рассылка отменена.")
            return
        
        # Отправляем рассылку
        await context.bot.send_message(chat_id, f"📤 Начинаю рассылку в {len(unread_chats)} чатов...")
        sent = 0
        for dialog in unread_chats:
            try:
                await client.send_message(dialog, text)
                sent += 1
                await asyncio.sleep(5)  # <----- ЗАДЕРЖКА 5 СЕКУНД
            except Exception as e:
                await context.bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")
        await context.bot.send_message(chat_id, f"✅ Рассылка завершена! Отправлено в {sent} чатов.")
        pending_action.pop(chat_id, None)
        unread_chats = []
        return

# ================== КОМАНДЫ БОТА ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для массового ответа в личные сообщения.\n"
        "🔹 /add_account - добавить аккаунт (вход по номеру и коду)\n"
        "🔹 /reply_all - ответить всем с непрочитанными сообщениями"
    )

async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await login_account(update, context)

async def reply_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global client, unread_chats
    chat_id = update.effective_chat.id
    
    if client is None:
        await context.bot.send_message(chat_id, "❌ Сначала добавьте аккаунт через /add_account")
        return
    
    # Проверяем авторизацию
    if not await client.is_user_authorized():
        await context.bot.send_message(chat_id, "❌ Сессия истекла. Используйте /add_account")
        return
    
    # Собираем чаты с непрочитанными
    await context.bot.send_message(chat_id, "🔍 Сканирую чаты...")
    dialogs = await client.get_dialogs()
    unread_chats = []
    
    for dialog in dialogs:
        if dialog.is_user and dialog.unread_count > 0:
            unread_chats.append(dialog)
    
    if not unread_chats:
        await context.bot.send_message(chat_id, "✅ Нет личных чатов с непрочитанными сообщениями.")
        return
    
    # Отправляем список
    msg = f"📋 Найдено {len(unread_chats)} чатов с непрочитанными:\n\n"
    for i, dialog in enumerate(unread_chats[:15], 1):
        name = dialog.name or "Без имени"
        msg += f"{i}. {name} ({dialog.unread_count} непрочитанных)\n"
    if len(unread_chats) > 15:
        msg += f"... и ещё {len(unread_chats) - 15} чатов"
    
    await context.bot.send_message(chat_id, msg)
    await context.bot.send_message(chat_id, "✏️ Введите сообщение для рассылки (или /cancel для отмены):")
    
    pending_action[chat_id] = 'awaiting_message'

# ================== ЗАПУСК БОТА ==================
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Регистрируем команды
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('add_account', add_account))
    app.add_handler(CommandHandler('reply_all', reply_all))
    
    # Обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Бот запущен!")
    app.run_polling()