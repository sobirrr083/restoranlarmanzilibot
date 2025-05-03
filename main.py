import os
import logging
from dotenv import load_dotenv
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler
from telegram.error import Conflict
import re

# Load environment variables
load_dotenv()
TOKEN = os.getenv('TELEGRAM_TOKEN')

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup
def init_db():
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    
    # Restaurants table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS restaurants (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        address TEXT,
        latitude REAL,
        longitude REAL
    )
    ''')
    
    # Admins table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )
    ''')
    
    # Contact info table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS contact_info (
        id INTEGER PRIMARY KEY,
        contact_text TEXT NOT NULL
    )
    ''')
    
    # Add default admin
    default_admin = os.getenv('ADMIN_ID')
    if default_admin:
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (int(default_admin),))
    
    # Add default contact info
    cursor.execute("SELECT COUNT(*) FROM contact_info")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO contact_info (contact_text) VALUES (?)", ("Savollar va takliflar uchun: @admin",))
    
    conn.commit()
    conn.close()

# States for conversation handlers
MAIN, ADDING_NAME, ADDING_DESCRIPTION, ADDING_ADDRESS, ADDING_LOCATION = range(5)
EDITING_SELECT, EDITING_NAME, EDITING_DESCRIPTION, EDITING_ADDRESS, EDITING_LOCATION = range(5, 10)
ADDING_ADMIN, CHANGING_CONTACT = range(10, 12)

# Check if user is admin
def is_admin(user_id):
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Get contact info
def get_contact_info():
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("SELECT contact_text FROM contact_info WHERE id = 1")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "Savollar va takliflar uchun: @admin"

# Admin panel keyboard
def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("➕ Restoran qo'shish"), KeyboardButton("✏️ Restoranni tahrirlash")],
        [KeyboardButton("🗑️ Restoranni o'chirish"), KeyboardButton("👤 Foydalanuvchi rejimiga o'tish")],
        [KeyboardButton("👑 Admin qo'shish"), KeyboardButton("📞 Bog'lanish ma'lumotini o'zgartirish")],
        [KeyboardButton("🔙 Orqaga qaytish")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# User main keyboard
def get_user_keyboard():
    keyboard = [
        [KeyboardButton("🍽️ Restoranlar ro'yxati")],
        [KeyboardButton("ℹ️ Bot haqida"), KeyboardButton("📞 Bog'lanish")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Get all restaurants for inline keyboard
def get_restaurants_keyboard(for_editing=False):
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM restaurants")
    restaurants = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for restaurant in restaurants:
        action = "edit" if for_editing else "view"
        callback_data = f"{action}_{restaurant[0]}"
        keyboard.append([InlineKeyboardButton(restaurant[1], callback_data=callback_data)])
    
    return InlineKeyboardMarkup(keyboard)

# Get restaurants list for deletion
def get_restaurants_for_deletion():
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM restaurants")
    restaurants = cursor.fetchall()
    conn.close()
    
    keyboard = []
    for restaurant in restaurants:
        callback_data = f"delete_{restaurant[0]}"
        keyboard.append([InlineKeyboardButton(restaurant[1], callback_data=callback_data)])
    
    return InlineKeyboardMarkup(keyboard)

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info(f"User {update.effective_user.id} started the bot")
    await update.message.reply_text(
        "Assalomu alaykum! Restoranlar botiga xush kelibsiz.\n\n"
        "Bu botdan foydalanib siz restoranlar haqida ma'lumot olishingiz mumkin. "
        "Restoranlar ro'yxatini ko'rish uchun '🍽️ Restoranlar ro'yxati' tugmasini bosing.\n\n"
        "Admin bo'lsangiz /admin buyrug'ini yuborib admin panelga kirishingiz mumkin.",
        reply_markup=get_user_keyboard()
    )
    
    return MAIN

# Admin command handler
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    logger.info(f"User {user_id} called /admin")
    
    if is_admin(user_id):
        await update.message.reply_text(
            "Admin panel. Kerakli amalni tanlang:",
            reply_markup=get_admin_keyboard()
        )
    else:
        await update.message.reply_text(
            "Sizda admin huquqlari yo'q.\n\n"
            "Admin huquqlarini olish uchun bot administratori bilan bog'laning.",
            reply_markup=get_user_keyboard()
        )
    
    return MAIN

# Handle admin panel options
async def handle_admin_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Admin choice by user {user_id}: {text}")
    
    if not is_admin(user_id):
        logger.warning(f"Non-admin user {user_id} tried to access admin panel")
        await update.message.reply_text("Sizda admin huquqlari yo'q.")
        return ConversationHandler.END
    
    if text == "➕ Restoran qo'shish":
        keyboard = [
            [KeyboardButton("🔙 Orqaga qaytish")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Restoran nomini kiriting: (yoki '🔙 Orqaga qaytish' tugmasini bosing)",
            reply_markup=reply_markup
        )
        return ADDING_NAME
    
    elif text == "✏️ Restoranni tahrirlash":
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM restaurants")
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            await update.message.reply_text(
                "Hozircha hech qanday restoran mavjud emas. Avval restoran qo'shing.",
                reply_markup=get_admin_keyboard()
            )
            return MAIN
        
        await update.message.reply_text(
            "Tahrirlash uchun restoranni tanlang:",
            reply_markup=get_restaurants_keyboard(for_editing=True)
        )
        return EDITING_SELECT
    
    elif text == "🗑️ Restoranni o'chirish":
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM restaurants")
        count = cursor.fetchone()[0]
        conn.close()
        
        if count == 0:
            await update.message.reply_text(
                "Hozircha hech qanday restoran mavjud emas. Avval restoran qo'shing.",
                reply_markup=get_admin_keyboard()
            )
            return MAIN
        
        await update.message.reply_text(
            "O'chirish uchun restoranni tanlang:",
            reply_markup=get_restaurants_for_deletion()
        )
        return MAIN
    
    elif text == "👤 Foydalanuvchi rejimiga o'tish":
        await update.message.reply_text(
            "Foydalanuvchi rejimiga o'tdingiz.",
            reply_markup=get_user_keyboard()
        )
        return MAIN
    
    elif text == "👑 Admin qo'shish":
        keyboard = [
            [KeyboardButton("🔙 Orqaga qaytish")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "Yangi adminning Telegram ID'sini kiriting (raqamlar, masalan: 123456789):",
            reply_markup=reply_markup
        )
        return ADDING_ADMIN
    
    elif text == "📞 Bog'lanish ma'lumotini o'zgartirish":
        current_contact = get_contact_info()
        keyboard = [
            [KeyboardButton("🔙 Orqaga qaytish")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Joriy bog'lanish ma'lumoti: {current_contact}\n\n"
            "Yangi bog'lanish ma'lumotini kiriting (masalan: Telegram @username yoki telefon raqami):",
            reply_markup=reply_markup
        )
        return CHANGING_CONTACT
    
    elif text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Bosh menyu.",
            reply_markup=get_user_keyboard()
        )
        return MAIN
    
    logger.info(f"Unrecognized admin choice by user {user_id}: {text}")
    await update.message.reply_text(
        "Iltimos, quyidagi tugmalardan birini bosing:",
        reply_markup=get_admin_keyboard()
    )
    return MAIN

# Handle adding restaurant - name
async def add_restaurant_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    logger.info(f"Adding restaurant name by user {update.effective_user.id}: {text}")
    
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Restoranni qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    context.user_data['restaurant_name'] = text
    
    keyboard = [
        [KeyboardButton("🔙 Orqaga qaytish")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Restoran haqida qisqacha ma'lumot kiriting: (ixtiyoriy, yoki '🔙 Orqaga qaytish' tugmasini bosing)",
        reply_markup=reply_markup
    )
    return ADDING_DESCRIPTION

# Handle adding restaurant - description
async def add_restaurant_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    logger.info(f"Adding restaurant description by user {update.effective_user.id}: {text}")
    
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Restoranni qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    context.user_data['restaurant_description'] = text
    
    keyboard = [
        [KeyboardButton("🔙 Orqaga qaytish")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Restoran manzilini kiriting: (yoki '🔙 Orqaga qaytish' tugmasini bosing)",
        reply_markup=reply_markup
    )
    return ADDING_ADDRESS

# Handle adding restaurant - address
async def add_restaurant_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    logger.info(f"Adding restaurant address by user {update.effective_user.id}: {text}")
    
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Restoranni qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    context.user_data['restaurant_address'] = text
    
    keyboard = [
        [KeyboardButton("📍 Lokatsiya yuborish", request_location=True)],
        [KeyboardButton("⏩ O'tkazib yuborish")],
        [KeyboardButton("🔙 Orqaga qaytish")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "Restoran joylashuvini lokatsiya ko'rinishida yuboring: (ixtiyoriy, yoki '⏩ O'tkazib yuborish' tugmasini bosing)",
        reply_markup=reply_markup
    )
    return ADDING_LOCATION

# Handle adding restaurant - location
async def add_restaurant_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    logger.info(f"Adding restaurant location by user {user_id}")
    
    if update.message.text == "🔙 Orqaga qaytish":
        logger.info(f"User {user_id} cancelled adding restaurant")
        await update.message.reply_text(
            "Restoranni qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    if update.message.text == "⏩ O'tkazib yuborish":
        logger.info(f"User {user_id} skipped adding location")
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        
        description = context.user_data.get('restaurant_description', '')
        address = context.user_data.get('restaurant_address', '')
        
        cursor.execute(
            "INSERT INTO restaurants (name, description, address, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
            (
                context.user_data['restaurant_name'],
                description,
                address,
                None,
                None
            )
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            "Restoran muvaffaqiyatli qo'shildi!",
            reply_markup=get_admin_keyboard()
        )
        
        context.user_data.clear()
        return MAIN
    
    if update.message.location:
        location = update.message.location
        logger.info(f"User {user_id} provided location: {location.latitude}, {location.longitude}")
        
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        
        description = context.user_data.get('restaurant_description', '')
        address = context.user_data.get('restaurant_address', '')
        
        cursor.execute(
            "INSERT INTO restaurants (name, description, address, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
            (
                context.user_data['restaurant_name'],
                description,
                address,
                location.latitude,
                location.longitude
            )
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            "Restoran muvaffaqiyatli qo'shildi!",
            reply_markup=get_admin_keyboard()
        )
        
        context.user_data.clear()
        return MAIN
    
    logger.warning(f"Invalid input in ADDING_LOCATION by user {user_id}")
    await update.message.reply_text(
        "Noto'g'ri ma'lumot kiritildi. Iltimos, lokatsiya yuboring yoki tugmalardan birini bosing.",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("📍 Lokatsiya yuborish", request_location=True)],
            [KeyboardButton("⏩ O'tkazib yuborish")],
            [KeyboardButton("🔙 Orqaga qaytish")]
        ], resize_keyboard=True)
    )
    
    return ADDING_LOCATION

# Handle adding admin
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Adding admin by user {user_id}: {text}")
    
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Admin qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Validate Telegram ID (must be numeric)
    if not re.match(r'^\d+$', text):
        await update.message.reply_text(
            "Iltimos, faqat raqamlardan iborat Telegram ID kiriting (masalan: 123456789):",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("🔙 Orqaga qaytish")]], resize_keyboard=True)
        )
        return ADDING_ADMIN
    
    new_admin_id = int(text)
    
    # Check if already admin
    if is_admin(new_admin_id):
        await update.message.reply_text(
            "Bu foydalanuvchi allaqachon admin!",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Add new admin
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"ID {new_admin_id} foydalanuvchisi admin sifatida qo'shildi!",
        reply_markup=get_admin_keyboard()
    )
    
    return MAIN

# Handle changing contact info
async def change_contact_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Changing contact info by user {user_id}: {text}")
    
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Bog'lanish ma'lumotini o'zgartirish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Update contact info
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE contact_info SET contact_text = ? WHERE id = 1", (text,))
    if cursor.rowcount == 0:  # If no rows updated, insert new
        cursor.execute("INSERT INTO contact_info (id, contact_text) VALUES (1, ?)", (text,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "Bog'lanish ma'lumoti muvaffaqiyatli o'zgartirildi!",
        reply_markup=get_admin_keyboard()
    )
    
    return MAIN

# Handle editing restaurant selection
async def edit_restaurant_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    logger.info(f"User {query.from_user.id} selecting restaurant to edit: {query.data}")
    
    data = query.data.split("_")
    if len(data) == 2 and data[0] == "edit":
        restaurant_id = int(data[1])
        context.user_data['editing_restaurant_id'] = restaurant_id
        
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        cursor.execute("SELECT name, description, address FROM restaurants WHERE id = ?", (restaurant_id,))
        restaurant = cursor.fetchone()
        conn.close()
        
        if restaurant:
            context.user_data['old_name'] = restaurant[0]
            context.user_data['old_description'] = restaurant[1]
            context.user_data['old_address'] = restaurant[2]
            
            keyboard = [
                [InlineKeyboardButton("Nomini tahrirlash", callback_data="edit_name")],
                [InlineKeyboardButton("Tavsifni tahrirlash", callback_data="edit_description")],
                [InlineKeyboardButton("Manzilni tahrirlash", callback_data="edit_address")],
                [InlineKeyboardButton("Lokatsiyani tahrirlash", callback_data="edit_location")],
            ]
            
            await query.edit_message_text(
                f"Restoran: {restaurant[0]}\n\n"
                f"Tavsif: {restaurant[1]}\n\n"
                f"Manzil: {restaurant[2]}\n\n"
                "Tahrirlash uchun parametrni tanlang:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return EDITING_SELECT
    
    logger.warning(f"Invalid edit selection by user {query.from_user.id}: {query.data}")
    await query.edit_message_text("Xatolik yuz berdi. Qaytadan urinib ko'ring.")
    return MAIN

# Handle editing restaurant field selection
async def edit_restaurant_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    logger.info(f"User {query.from_user.id} editing field: {query.data}")
    
    action = query.data.split("_")[1]
    
    if action == "name":
        keyboard = [
            [KeyboardButton("🔙 Orqaga qaytish")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await query.message.reply_text(
            f"Joriy nom: {context.user_data['old_name']}\n"
            "Yangi nomni kiriting: (yoki '🔙 Orqaga qaytish' tugmasini bosing)",
            reply_markup=reply_markup
        )
        return EDITING_NAME
    
    elif action == "description":
        keyboard = [
            [KeyboardButton("🔙 Orqaga qaytish")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await query.message.reply_text(
            f"Joriy tavsif: {context.user_data['old_description']}\n"
            "Yangi tavsifni kiriting: (yoki '🔙 Orqaga qaytish' tugmasini bosing)",
            reply_markup=reply_markup
        )
        return EDITING_DESCRIPTION
    
    elif action == "address":
        keyboard = [
            [KeyboardButton("🔙 Orqaga qaytish")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
