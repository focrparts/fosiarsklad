import os
import json
import pandas as pd
import datetime
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler, ConversationHandler

# --- Настройки ---
TOKEN = "7651891622:AAHT4Tgs8E5DByxGGTfzaMaFCrWc_WX3DGo"
STOCK_FILE = "stock.xlsx"
STATS_FILE = "stats.xlsx"
ROLES_FILE = "user_roles.json"  # Файл для хранения ролей

# --- Клавиатура ---
reply_markup = ReplyKeyboardMarkup([['Поиск']], resize_keyboard=True)

# --- Роли и админ ---
ADMIN_ID = 1303430775  # Ваш Telegram ID админа (замените на свой)
MARKUP_PERCENTAGE = 30

# --- Состояния для ConversationHandler ---
ORDER_ARTICLE, ORDER_QUANTITY, ORDER_FIO, ORDER_PHONE, ORDER_ADDRESS = range(5)

# --- Работа с ролями ---
if os.path.exists(ROLES_FILE):
    with open(ROLES_FILE, "r", encoding="utf-8") as f:
        user_roles = json.load(f)
else:
    user_roles = {}

def save_roles():
    with open(ROLES_FILE, "w", encoding="utf-8") as f:
        json.dump(user_roles, f, ensure_ascii=False, indent=2)

def get_role(user_id):
    user_id = str(user_id)
    if user_id not in user_roles:
        # Новый пользователь — автоматически покупатель
        user_roles[user_id] = "buyer"
        save_roles()
    return user_roles[user_id]

def set_role(user_id, role):
    user_roles[str(user_id)] = role
    save_roles()

def is_admin(user_id):
    return user_id == ADMIN_ID

# --- Работа с Excel ---
def load_stock():
    return pd.read_excel(STOCK_FILE)

def save_stock(df):
    df.to_excel(STOCK_FILE, index=False)

def log_transaction(article, qty, op):
    now = datetime.datetime.now()
    cols = ['Дата', 'Артикул', 'Количество', 'Операция']

    if os.path.exists(STATS_FILE):
        df = pd.read_excel(STATS_FILE)
    else:
        df = pd.DataFrame(columns=cols)

    new_row = pd.DataFrame([{'Дата': now, 'Артикул': article, 'Количество': qty, 'Операция': op}])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_excel(STATS_FILE, index=False)

# --- Поиск товара ---
def search_item(query, df):
    mask = (
        df['Артикул'].astype(str).str.contains(query, case=False) |
        df['Наименование'].astype(str).str.contains(query, case=False) |
        df['Местоположение'].astype(str).str.contains(query, case=False)
    )
    return df[mask]

# --- Команды ---
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    role = get_role(user_id)
    if role == 'buyer':
        await update.message.reply_text("Добро пожаловать в наш магазин! Нажмите «Поиск» для поиска товара.", reply_markup=reply_markup)
    elif role == 'admin':
        await update.message.reply_text("Здравствуйте, админ! Нажмите «Поиск» для управления.", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"Привет! Ваша роль: {role}. Нажмите «Поиск» и введите запрос.", reply_markup=reply_markup)

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    role = get_role(user_id)
    text = update.message.text.strip()

    if text.lower() == 'поиск':
        await update.message.reply_text("Введи артикул, название или местоположение:")
        return

    df = load_stock()
    res = search_item(text, df)

    if res.empty:
        await update.message.reply_text("Товар не найден.")
    else:
        for _, r in res.iterrows():
            price = r['Цена']
            if role == 'buyer':
                price = round(price * (1 + MARKUP_PERCENTAGE / 100), 2)

            message = f"{r['Наименование']} (Артикул: {r['Артикул']})\nЦена: {price}₽"

            if role in ['admin', 'seller']:
                message += f"\nОстаток: {r['Количество']}\nМестоположение: {r['Местоположение']}"

            buttons = []
            if role == 'admin':
                buttons = [[
                    InlineKeyboardButton("Продать", callback_data=f"sell_{r['Артикул']}"),
                    InlineKeyboardButton("Установить", callback_data=f"install_{r['Артикул']}")
                ]]
            elif role == 'buyer':
                buttons = [[InlineKeyboardButton("Оформить заказ", callback_data=f"order_{r['Артикул']}")]]

            await update.message.reply_text(message, reply_markup=InlineKeyboardMarkup(buttons) if buttons else None)

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("sell_"):
        await query.edit_message_text("Введите команду /sell <артикул> <кол-во>")

    elif data.startswith("install_"):
        await query.edit_message_text("Введите команду /install <артикул> <кол-во>")

    elif data.startswith("order_"):
        ctx.user_data['article'] = data.split('_')[1]
        await query.edit_message_text("Введите ФИО:")
        return ORDER_FIO

    return ConversationHandler.END

async def order_fio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['fio'] = update.message.text
    await update.message.reply_text("Введите номер телефона:")
    return ORDER_PHONE

async def order_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['phone'] = update.message.text
    await update.message.reply_text("Введите адрес доставки:")
    return ORDER_ADDRESS

async def order_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['address'] = update.message.text

    seller_contact = '@seller_username'  # замените на реальный ник продавца

    await update.message.reply_text(
        f"Спасибо за заказ, {ctx.user_data['fio']}!\n"
        f"В ближайшее время с вами свяжется продавец: {seller_contact}",
        reply_markup=reply_markup
    )
    return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Заказ отменён.", reply_markup=reply_markup)
    return ConversationHandler.END

# --- Продажа, установка и добавление ---
async def sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Команда доступна только администратору.")
        return

    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /sell <артикул> <количество>")
        return

    article, qty = args[0], int(args[1])
    df = load_stock()
    if article not in df['Артикул'].values:
        await update.message.reply_text("Артикул не найден.")
        return

    df.loc[df['Артикул'] == article, 'Количество'] -= qty
    save_stock(df)
    log_transaction(article, qty, "Продажа")
    await update.message.reply_text(f"Продано {qty} шт. товара {article}.")

async def install(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Команда доступна только администратору.")
        return

    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /install <артикул> <количество>")
        return

    article, qty = args[0], int(args[1])
    df = load_stock()
    if article not in df['Артикул'].values:
        await update.message.reply_text("Артикул не найден.")
        return

    df.loc[df['Артикул'] == article, 'Количество'] -= qty
    save_stock(df)
    log_transaction(article, qty, "Установка")
    await update.message.reply_text(f"Установлено {qty} шт. товара {article}.")

async def add(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Команда доступна только администратору.")
        return

    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /add <артикул> <количество>")
        return

    article, qty = args[0], int(args[1])
    df = load_stock()
    if article not in df['Артикул'].values:
        await update.message.reply_text("Артикул не найден.")
        return

    df.loc[df['Артикул'] == article, 'Количество'] += qty
    save_stock(df)
    log_transaction(article, qty, "Пополнение")
    await update.message.reply_text(f"Добавлено {qty} шт. товара {article} на склад.")

# --- Управление ролями ---
async def role(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Команда доступна только администратору.")
        return

    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /role <user_id> <role>\nРоли: admin, seller, buyer, guest")
        return

    target_id, new_role = args[0], args[1].lower()
    if new_role not in ['admin', 'seller', 'buyer', 'guest']:
        await update.message.reply_text("Неверная роль. Возможные: admin, seller, buyer, guest")
        return

    set_role(target_id, new_role)
    await update.message.reply_text(f"Роль пользователя {target_id} установлена на {new_role}.")

# --- Запуск ---
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler)],
        states={
            ORDER_FIO: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_fio)],
            ORDER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_phone)],
            ORDER_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sell", sell))
    app.add_handler(CommandHandler("install", install))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("role", role))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(conv_handler)

    print("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()

