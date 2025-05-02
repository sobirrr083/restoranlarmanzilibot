import os
import logging
from dotenv import load_dotenv
import sqlite3
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, ConversationHandler

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
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )
    ''')
    
    # Add default admin
    default_admin = os.getenv('ADMIN_ID')
    if default_admin:
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (int(default_admin),))
    
    conn.commit()
    conn.close()

# States for conversation handlers
MAIN, ADDING_NAME, ADDING_DESCRIPTION, ADDING_ADDRESS, ADDING_LOCATION = range(5)
EDITING_SELECT, EDITING_NAME, EDITING_DESCRIPTION, EDITING_ADDRESS, EDITING_LOCATION = range(5, 10)

# Check if user is admin
def is_admin(user_id):
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Admin panel keyboard
def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("➕ Restoran qo'shish"), KeyboardButton("✏️ Restoranni tahrirlash")],
        [KeyboardButton("🗑️ Restoranni o'chirish"), KeyboardButton("🔙 Orqaga qaytish")],
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
    
    # Add a back button
    if keyboard:
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")])
    
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
    
    # Add a back button
    if keyboard:
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(keyboard)

# Debug function to check admin status
async def debug_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admins")
    admins = cursor.fetchall()
    conn.close()
    await update.message.reply_text(f"Sizning ID: {user_id}\nAdmin IDs: {admins}")

# Start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

# Add admin command
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Check if the user is already an admin
    if not is_admin(user_id):
        await update.message.reply_text("Bu amalni bajarish uchun sizda huquq yo'q.")
        return
    
    # Check if an ID was provided
    if not context.args:
        await update.message.reply_text("Qo'shmoqchi bo'lgan admin ID sini kiriting. Masalan: /add_admin 12345678")
        return
    
    try:
        new_admin_id = int(context.args[0])
        
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        
        if cursor.rowcount > 0:
            await update.message.reply_text(f"ID {new_admin_id} adminlar ro'yxatiga qo'shildi.")
        else:
            await update.message.reply_text(f"ID {new_admin_id} allaqachon adminlar ro'yxatida mavjud.")
        
        conn.close()
    
    except ValueError:
        await update.message.reply_text("ID raqam bo'lishi kerak.")

# Handle admin panel options
async def handle_admin_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    text = update.message.text
    
    if not is_admin(user_id):
        await update.message.reply_text("Sizda admin huquqlari yo'q.")
        return ConversationHandler.END
    
    if text == "➕ Restoran qo'shish":
        # Add back button to keyboard
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
        # Check if there are any restaurants
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
        # Check if there are any restaurants
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
    
    elif text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Bosh menyu.",
            reply_markup=get_user_keyboard()
        )
        return MAIN
    
    return MAIN

# Handle adding restaurant - name
async def add_restaurant_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Restoranni qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    context.user_data['restaurant_name'] = text
    
    # Add back button to keyboard
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
    
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Restoranni qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    context.user_data['restaurant_description'] = text
    
    # Add back button to keyboard
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
    
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Restoranni qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    context.user_data['restaurant_address'] = text
    
    # Add skip and back buttons
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
    # Check if user wants to go back
    if update.message.text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Restoranni qo'shish bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Check if user wants to skip location
    if update.message.text == "⏩ O'tkazib yuborish":
        # Save restaurant to database without location
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        
        # Default description and address if not provided
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
        
        # Clear user data
        context.user_data.clear()
        
        return MAIN
    
    # Process location if provided
    if update.message.location:
        location = update.message.location
        
        # Save restaurant to database
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        
        # Default description and address if not provided
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
        
        # Clear user data
        context.user_data.clear()
        
        return MAIN
    
    # If we get here, something went wrong
    await update.message.reply_text(
        "Noto'g'ri ma'lumot kiritildi. Iltimos, lokatsiya yuboring yoki tugmalardan birini bosing.",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("📍 Lokatsiya yuborish", request_location=True)],
            [KeyboardButton("⏩ O'tkazib yuborish")],
            [KeyboardButton("🔙 Orqaga qaytish")]
        ], resize_keyboard=True)
    )
    
    return ADDING_LOCATION

# Handle editing restaurant selection
async def edit_restaurant_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Check for back to menu action
    if query.data == "back_to_menu":
        await query.edit_message_text("Amallar bekor qilindi.")
        return MAIN
    
    # Extract restaurant ID from callback data
    data = query.data.split("_")
    if len(data) == 2 and data[0] == "edit":
        restaurant_id = int(data[1])
        context.user_data['editing_restaurant_id'] = restaurant_id
        
        # Get restaurant info
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
                [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_admin")]
            ]
            
            await query.edit_message_text(
                f"Restoran: {restaurant[0]}\n\n"
                f"Tavsif: {restaurant[1]}\n\n"
                f"Manzil: {restaurant[2]}\n\n"
                "Tahrirlash uchun parametrni tanlang:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            return EDITING_SELECT
    
    await query.edit_message_text("Xatolik yuz berdi. Qaytadan urinib ko'ring.")
    return MAIN

# Handle editing restaurant field selection
async def edit_restaurant_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_admin":
        await query.edit_message_text("Tahrirlash bekor qilindi.")
        return MAIN
    
    action = query.data.split("_")[1]
    
    if action == "name":
        # Add back button
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
        # Add back button
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
        # Add back button
        keyboard = [
            [KeyboardButton("🔙 Orqaga qaytish")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await query.message.reply_text(
            f"Joriy manzil: {context.user_data['old_address']}\n"
            "Yangi manzilni kiriting: (yoki '🔙 Orqaga qaytish' tugmasini bosing)",
            reply_markup=reply_markup
        )
        return EDITING_ADDRESS
    
    elif action == "location":
        # Add back button
        keyboard = [
            [KeyboardButton("📍 Lokatsiya yuborish", request_location=True)],
            [KeyboardButton("⏩ O'tkazib yuborish")],
            [KeyboardButton("🔙 Orqaga qaytish")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await query.message.reply_text(
            "Yangi lokatsiyani yuboring: (ixtiyoriy, yoki '⏩ O'tkazib yuborish' tugmasini bosing)",
            reply_markup=reply_markup
        )
        return EDITING_LOCATION
    
    return MAIN

# Handle editing restaurant - name
async def edit_restaurant_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    # Check if going back
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Tahrirlash bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Update restaurant name
    restaurant_id = context.user_data['editing_restaurant_id']
    
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE restaurants SET name = ? WHERE id = ?", (text, restaurant_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "Restoran nomi muvaffaqiyatli tahrirlandi!",
        reply_markup=get_admin_keyboard()
    )
    
    return MAIN

# Handle editing restaurant - description
async def edit_restaurant_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    # Check if going back
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Tahrirlash bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Update restaurant description
    restaurant_id = context.user_data['editing_restaurant_id']
    
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE restaurants SET description = ? WHERE id = ?", (text, restaurant_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "Restoran tavsifi muvaffaqiyatli tahrirlandi!",
        reply_markup=get_admin_keyboard()
    )
    
    return MAIN

# Handle editing restaurant - address
async def edit_restaurant_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text
    
    # Check if going back
    if text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Tahrirlash bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Update restaurant address
    restaurant_id = context.user_data['editing_restaurant_id']
    
    conn = sqlite3.connect('restaurants.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE restaurants SET address = ? WHERE id = ?", (text, restaurant_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "Restoran manzili muvaffaqiyatli tahrirlandi!",
        reply_markup=get_admin_keyboard()
    )
    
    return MAIN

# Handle editing restaurant - location
async def edit_restaurant_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    restaurant_id = context.user_data['editing_restaurant_id']
    
    # Check if going back
    if update.message.text == "🔙 Orqaga qaytish":
        await update.message.reply_text(
            "Tahrirlash bekor qilindi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Check if skipping
    if update.message.text == "⏩ O'tkazib yuborish":
        await update.message.reply_text(
            "Lokatsiya tahrirlash o'tkazib yuborildi.",
            reply_markup=get_admin_keyboard()
        )
        return MAIN
    
    # Process location if provided
    if update.message.location:
        location = update.message.location
        
        conn = sqlite3.connect('restaurants.db')
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE restaurants SET latitude = ?, longitude = ? WHERE id = ?",
            (location.latitude, location.longitude, restaurant_id)
        )
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            "Restoran lokatsiyasi muvaffaqiyatli tahrirlandi!",
            reply_markup=get_admin_keyboard()
        )
        
        return MAIN
    
    # If we get here, something went wrong
    await update.message.reply_text(
        "Noto'g'ri ma'lumot kiritildi. Iltimos, lokatsiya yuboring yoki tugmalardan birini bosing.",
        reply_markup=ReplyKeyboardMarkup([
            [KeyboardButton("📍 Lokatsiya yuborish", request_location=True)],
            [KeyboardButton("⏩ O'tkazib yuborish")],
            [KeyboardButton("🔙 Orqaga qaytish")]
        ], resize_keyboard=True)
    )
    
    return EDITING_LOCATION

# Handle callbacks (viewing/deleting restaurants)
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    # Check for back to menu action
    if query.data == "back_to_menu":
        await query.edit_message_text("Bosh menyu.")
        return MAIN
    
    data = query.data.split("_")
    
    if len(data) == 2:
        action = data[0]
        restaurant_id = int(data[1])
        
        if action == "view":
            # View restaurant details
            conn = sqlite3.connect('restaurants.db')
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, description, address, latitude, longitude FROM restaurants WHERE id = ?",
                (restaurant_id,)
            )
            restaurant = cursor.fetchone()
            conn.close()
            
            if restaurant:
                keyboard = []
                
                # Add location button if coordinates exist
                if restaurant[3] and restaurant[4]:
                    keyboard.append([InlineKeyboardButton("📍 Lokatsiyani ko'rish", callback_data=f"location_{restaurant_id}")])
                
                # Add back button
                keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")])
                
                await query.edit_message_text(
                    f"🍽️ *{restaurant[0]}*\n\n"
                    f"ℹ️ *Ma'lumot:* {restaurant[1]}\n\n"
                    f"📍 *Manzil:* {restaurant[2]}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            else:
                await query.edit_message_text("Restoran topilmadi.")
        
        elif action == "location":
            # Send restaurant location
            conn = sqlite3.connect('restaurants.db')
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, latitude, longitude FROM restaurants WHERE id = ?",
                (restaurant_id,)
            )
            restaurant = cursor.fetchone()
            conn.close()
            
            if restaurant and restaurant[1] and restaurant[2]:
                await query.message.reply_location(
                    latitude=restaurant[1],
                    longitude=restaurant[2]
                )
                
                # Create back button
                keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data=f"view_{restaurant_id}")]]
                
                await query.edit_message_text(
                    f"{restaurant[0]} restorani lokatsiyasi yuqorida ko'rsatilgan.",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await query.edit_message_text("Bu restoran uchun lokatsiya mavjud emas.")
        
        elif action == "delete":
            # Delete restaurant
            if is_admin(query.from_user.id):
                conn = sqlite3.connect('restaurants.db')
                cursor = conn.cursor()
                
                # Get restaurant name
                cursor.execute("SELECT name FROM restaurants WHERE id = ?", (restaurant_id,))
                restaurant = cursor.fetchone()
                
                if restaurant:
                    cursor.execute("DELETE FROM restaurants WHERE id = ?", (restaurant_id,))
                    conn.commit()
                    
                    # Create back button
                    keyboard = [[InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_menu")]]
                    
                    await query.edit_message_text(
                        f"'{restaurant[0]}' restorani o'chirildi.",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await query.edit_message_text("Restoran topilmadi.")
                
                conn.close()
            else:
                await query.edit_message_text("Sizda admin huquqlari yo'q.")
    
    return MAIN

# Handle user menu options
async def handle_user_choice(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data

    if choice == "korish":
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, ism, familiya, telefon FROM users")
        users = cursor.fetchall()
        conn.close()

        if not users:
            await query.edit_message_text("Foydalanuvchilar ro'yxati bo'sh.", reply_markup=back_to_main_menu())
        else:
            message_text = "Foydalanuvchilar ro'yxati:\n\n"
            for user in users:
                message_text += f"ID: {user[0]}, Ism: {user[1]}, Familiya: {user[2]}, Telefon: {user[3]}\n"
            
            await query.edit_message_text(message_text, reply_markup=back_to_main_menu())
    
    elif choice == "qoshish":
        await query.edit_message_text("Yangi foydalanuvchi ma'lumotlarini kiriting.\nFormat: Ism Familiya Telefon", reply_markup=back_to_main_menu())
        return ADD_USER
    
    elif choice == "ochirish":
        await query.edit_message_text("O'chirmoqchi bo'lgan foydalanuvchi ID raqamini kiriting:", reply_markup=back_to_main_menu())
        return DELETE_USER
    
    elif choice == "yangilash":
        await query.edit_message_text("Yangilamoqchi bo'lgan foydalanuvchi ID raqamini kiriting:", reply_markup=back_to_main_menu())
        return UPDATE_USER_ID
    
    elif choice == "bosh_menu":
        await query.edit_message_text("Bosh menyu:", reply_markup=get_main_menu())
    
    return MAIN

# Add user function
async def add_user(update: Update, context: CallbackContext) -> int:
    user_data = update.message.text.split()
    
    if len(user_data) < 3:
        await update.message.reply_text("Noto'g'ri format. Iltimos, Ism Familiya Telefon formatida kiriting.")
        return ADD_USER
    
    ism = user_data[0]
    familiya = user_data[1]
    telefon = user_data[2]
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (ism, familiya, telefon) VALUES (?, ?, ?)", (ism, familiya, telefon))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"Foydalanuvchi qo'shildi: {ism} {familiya}", reply_markup=get_main_menu())
    return MAIN

# Delete user function
async def delete_user(update: Update, context: CallbackContext) -> int:
    try:
        user_id = int(update.message.text)
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        if user:
            cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            await update.message.reply_text(f"Foydalanuvchi ID {user_id} muvaffaqiyatli o'chirildi.", reply_markup=get_main_menu())
        else:
            await update.message.reply_text(f"ID {user_id} bilan foydalanuvchi topilmadi.", reply_markup=get_main_menu())
        
        conn.close()
    except ValueError:
        await update.message.reply_text("Noto'g'ri ID formati. Raqam kiriting.", reply_markup=get_main_menu())
    
    return MAIN

# Update user functions
async def update_user_id(update: Update, context: CallbackContext) -> int:
    try:
        user_id = int(update.message.text)
        
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            context.user_data['update_user_id'] = user_id
            await update.message.reply_text(
                f"Foydalanuvchi topildi: ID {user_id}, Ism: {user[1]}, Familiya: {user[2]}, Telefon: {user[3]}\n"
                "Yangi ma'lumotlarni kiriting (Ism Familiya Telefon):", 
                reply_markup=back_to_main_menu()
            )
            return UPDATE_USER_DATA
        else:
            await update.message.reply_text(f"ID {user_id} bilan foydalanuvchi topilmadi.", reply_markup=get_main_menu())
            return MAIN
    except ValueError:
        await update.message.reply_text("Noto'g'ri ID formati. Raqam kiriting.", reply_markup=get_main_menu())
        return MAIN

async def update_user_data(update: Update, context: CallbackContext) -> int:
    user_data = update.message.text.split()
    
    if len(user_data) < 3:
        await update.message.reply_text("Noto'g'ri format. Iltimos, Ism Familiya Telefon formatida kiriting.")
        return UPDATE_USER_DATA
    
    user_id = context.user_data.get('update_user_id')
    ism = user_data[0]
    familiya = user_data[1]
    telefon = user_data[2]
    
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET ism = ?, familiya = ?, telefon = ? WHERE id = ?", (ism, familiya, telefon, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"Foydalanuvchi ID {user_id} ma'lumotlari yangilandi.", reply_markup=get_main_menu())
    return MAIN

# Back to main menu function
def back_to_main_menu():
    keyboard = [
        [InlineKeyboardButton("⬅️ Orqaga", callback_data="bosh_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def main():
    application = Application.builder().token(TOKEN).build()
    
    # Set up database
    setup_database()
    
    # Add conversation handler with states
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN: [
                CallbackQueryHandler(handle_admin_choice, pattern="^(users|products|orders)$"),
                CallbackQueryHandler(handle_user_choice, pattern="^(korish|qoshish|ochirish|yangilash|bosh_menu)$"),
                CallbackQueryHandler(handle_product_choice, pattern="^(view_products|add_product|delete_product|update_product)$"),
                CallbackQueryHandler(handle_order_choice, pattern="^(view_orders|add_order|delete_order|update_order)$"),
            ],
            ADD_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user)],
            DELETE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_user)],
            UPDATE_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_user_id)],
            UPDATE_USER_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_user_data)],
            # Add other states for products and orders handling
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    
    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()
async def handle_user_choice
