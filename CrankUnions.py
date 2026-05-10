import telebot
import sqlite3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8779192289:AAEeVZaQkq2ANZM7Fz236PTE-1N2RSwwMKk"
bot = telebot.TeleBot(TOKEN)

# ================= БАЗА =================
conn = sqlite3.connect("CUBC.db", check_same_thread=False)
cursor = conn.cursor()

# СТАРАЯ ТАБЛИЦА
cursor.execute("""
CREATE TABLE IF NOT EXISTS bikes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    photo_id TEXT,
    is_deleted INTEGER DEFAULT 0,
    on_sale INTEGER DEFAULT 0
)
""")

conn.commit()

# ====== УДАЛЕНИЕ ======
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_"))
def delete_bike(call):
    bike_id = call.data.split("_")[1]

    cursor.execute("UPDATE bikes SET is_deleted=1 WHERE id=?", (bike_id,))
    conn.commit()

    bot.answer_callback_query(call.id, "Удалено")


# ====== ПРОДАЖА ======
@bot.callback_query_handler(func=lambda call: call.data.startswith("sale_"))
def sale_bike(call):
    bike_id = call.data.split("_")[1]

    cursor.execute("UPDATE bikes SET on_sale=1 WHERE id=?", (bike_id,))
    conn.commit()

    bot.answer_callback_query(call.id, "Выставлено на продажу")


# ====== СПИСОК ПРОДАЖ ======
@bot.message_handler(commands=['salebikes'])
def sale_bikes(message):
    cursor.execute("SELECT photo_id, username FROM bikes WHERE on_sale=1 AND is_deleted=0")
    bikes = cursor.fetchall()

    if not bikes:
        bot.send_message(message.chat.id, "❌ Нет байков на продаже")
        return

    for bike in bikes:
        bot.send_photo(message.chat.id, bike[0],
                       caption=f"💰 Продается\n👤 @{bike[1]}")


# ====== ВСЕ БАЙКИ ======
@bot.message_handler(commands=['allbikes'])
def all_bikes(message):
    cursor.execute("SELECT photo_id, username FROM bikes WHERE is_deleted=0")
    bikes = cursor.fetchall()

    if not bikes:
        bot.send_message(message.chat.id, "❌ Нет байков")
        return

    for bike in bikes:
        bot.send_photo(message.chat.id, bike[0],
                       caption=f"🚲 @{bike[1]}")


# ====== УДАЛЕННЫЕ ======
@bot.message_handler(commands=['deleted'])
def deleted_bikes(message):
    if message.chat.type != "private":
        return

    user_id = message.from_user.id

    cursor.execute("SELECT id, photo_id FROM bikes WHERE user_id=? AND is_deleted=1", (user_id,))
    bikes = cursor.fetchall()

    if not bikes:
        bot.send_message(message.chat.id, "❌ Удаленных нет")
        return

    for bike in bikes:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("♻️ Восстановить", callback_data=f"restore_{bike[0]}"))

        bot.send_photo(message.chat.id, bike[1], reply_markup=markup)


# ====== ВОССТАНОВЛЕНИЕ ======
@bot.callback_query_handler(func=lambda call: call.data.startswith("restore_"))
def restore_bike(call):
    bike_id = call.data.split("_")[1]

    cursor.execute("UPDATE bikes SET is_deleted=0 WHERE id=?", (bike_id,))
    conn.commit()

    bot.answer_callback_query(call.id, "Восстановлено")

# ===== ДОБАВЛЯЕМ НОВЫЕ КОЛОНКИ БЕЗ УДАЛЕНИЯ СТАРОЙ БД =====
def add_column(name, column):
    try:
        cursor.execute(f"ALTER TABLE {name} ADD COLUMN {column}")
        conn.commit()
    except:
        pass

add_column("bikes", "likes INTEGER DEFAULT 0")
add_column("bikes", "dislikes INTEGER DEFAULT 0")

# ТАБЛИЦА ГОЛОСОВ
cursor.execute("""
CREATE TABLE IF NOT EXISTS votes (
    user_id INTEGER,
    bike_id INTEGER,
    vote TEXT
)
""")

conn.commit()

# ========= /TOPBIKE С ПЕРЕЛИСТЫВАНИЕМ =========

def topbike_caption(bike):

    rank = get_rank(bike[0])

    return (
        f"🚲 Владелец: @{bike[2]}\n\n"
        f"🏆 Место в топе: {rank}\n"
        f"👍 Понравилось: {bike[6]}\n"
        f"👎 НеПонравилось: {bike[7]}"
    )


def topbike_markup(current_index, total):

    markup = InlineKeyboardMarkup(row_width=2)

    left = InlineKeyboardButton(
        "⬅️",
        callback_data=f"top_prev_{current_index - 1}"
    ) if current_index > 0 else InlineKeyboardButton(
        "⬅️",
        callback_data="empty"
    )

    right = InlineKeyboardButton(
        "➡️",
        callback_data=f"top_next_{current_index + 1}"
    ) if current_index < total - 1 else InlineKeyboardButton(
        "➡️",
        callback_data="empty"
    )

    markup.add(left, right)

    return markup


@bot.message_handler(commands=['topbike'])
def topbike(message):

    cursor.execute("""
    SELECT *
    FROM bikes
    WHERE is_deleted=0
    ORDER BY (likes - dislikes) DESC, likes DESC
    """)

    bikes = cursor.fetchall()

    if not bikes:
        bot.send_message(message.chat.id, "❌ Байков нет")
        return

    bike = bikes[0]

    bot.send_photo(
        message.chat.id,
        bike[3],
        caption=topbike_caption(bike),
        reply_markup=topbike_markup(0, len(bikes))
    )


@bot.callback_query_handler(func=lambda call:
    call.data.startswith("top_prev_") or
    call.data.startswith("top_next_"))
def topbike_swipe(call):

    index = int(call.data.split("_")[-1])

    cursor.execute("""
    SELECT *
    FROM bikes
    WHERE is_deleted=0
    ORDER BY (likes - dislikes) DESC, likes DESC
    """)

    bikes = cursor.fetchall()

    if index < 0 or index >= len(bikes):
        return

    bike = bikes[index]

    try:
        bot.edit_message_media(
            media=telebot.types.InputMediaPhoto(
                bike[3],
                caption=topbike_caption(bike)
            ),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=topbike_markup(index, len(bikes))
        )
    except:
        pass


@bot.callback_query_handler(func=lambda call: call.data == "empty")
def empty(call):
    bot.answer_callback_query(call.id)

# ================= РАНГ =================
def get_rank(bike_id):

    cursor.execute("""
    SELECT id, likes, dislikes
    FROM bikes
    WHERE is_deleted=0
    ORDER BY (likes - dislikes) DESC, likes DESC
    """)

    bikes = cursor.fetchall()

    for index, bike in enumerate(bikes, start=1):
        if bike[0] == bike_id:
            return index

    return "?"


# ================= ТЕКСТ =================
def bike_caption(bike):

    rank = get_rank(bike[0])

    return (
        f"🚲 Владелец: @{bike[2]}\n\n"
        f"🏆 Место в топе: {rank}\n"
        f"👍 Понравилось: {bike[6]}\n"
        f"👎 НеПонравилось: {bike[7]}"
    )


# ================= INLINE =================
def bike_markup(user_id, bike_id):

    cursor.execute("""
    SELECT id
    FROM bikes
    WHERE user_id=? AND is_deleted=0
    ORDER BY id
    """, (user_id,))

    ids = [x[0] for x in cursor.fetchall()]

    index = ids.index(bike_id)

    left = "empty"
    right = "empty"

    if index > 0:
        left = f"prev_{ids[index - 1]}"

    if index < len(ids) - 1:
        right = f"next_{ids[index + 1]}"

    markup = InlineKeyboardMarkup(row_width=4)

    markup.add(
        InlineKeyboardButton("⬅️", callback_data=left),
        InlineKeyboardButton("👍🏻", callback_data=f"like_{bike_id}"),
        InlineKeyboardButton("👎🏻", callback_data=f"dislike_{bike_id}"),
        InlineKeyboardButton("➡️", callback_data=right)
    )

    return markup


# ================= ДОБАВЛЕНИЕ БАЙКА =================
@bot.message_handler(commands=['checkbike'])
def add_bike(message):

    if not message.reply_to_message or not message.reply_to_message.photo:
        bot.reply_to(message, "❌ Ответь на фото")
        return

    # ЗАПРЕТ ЧУЖИХ ФОТО
    if message.reply_to_message.from_user.id != message.from_user.id:
        bot.reply_to(message, "❌ Нельзя добавлять чужой велосипед")
        return

    photo_id = message.reply_to_message.photo[-1].file_id

    cursor.execute("SELECT * FROM bikes WHERE photo_id=?", (photo_id,))
    exists = cursor.fetchone()

    if exists:
        bot.reply_to(message, "❌ Этот байк уже есть")
        return

    username = message.from_user.username or message.from_user.first_name

    cursor.execute("""
    INSERT INTO bikes (
        user_id,
        username,
        photo_id
    )
    VALUES (?, ?, ?)
    """, (
        message.from_user.id,
        username,
        photo_id
    ))

    conn.commit()

    bot.reply_to(message, "✅ Байк добавлен")


# ================= ПОКАЗ БАЙКОВ =================
@bot.message_handler(commands=['bikecheck'])
def bikecheck(message):

    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    else:
        user_id = message.from_user.id

    cursor.execute("""
    SELECT *
    FROM bikes
    WHERE user_id=? AND is_deleted=0
    ORDER BY id
    """, (user_id,))

    bikes = cursor.fetchall()

    if not bikes:
        bot.send_message(message.chat.id, "❌ Байков нет")
        return

    bike = bikes[0]

    bot.send_photo(
        message.chat.id,
        bike[3],
        caption=bike_caption(bike),
        reply_markup=bike_markup(user_id, bike[0])
    )


# ================= ТОП =================
@bot.message_handler(commands=['topbike'])
def topbike(message):

    cursor.execute("""
    SELECT *
    FROM bikes
    WHERE is_deleted=0
    ORDER BY (likes - dislikes) DESC, likes DESC
    LIMIT 1
    """)

    bike = cursor.fetchone()

    if not bike:
        bot.send_message(message.chat.id, "❌ Байков нет")
        return

    bot.send_photo(
        message.chat.id,
        bike[3],
        caption=bike_caption(bike),
        reply_markup=bike_markup(bike[1], bike[0])
    )


# ================= ЛАЙК =================
@bot.callback_query_handler(func=lambda call: call.data.startswith("like_"))
def like(call):

    bike_id = int(call.data.split("_")[1])

    cursor.execute("""
    SELECT *
    FROM votes
    WHERE user_id=? AND bike_id=?
    """, (
        call.from_user.id,
        bike_id
    ))

    vote = cursor.fetchone()

    if vote:
        bot.answer_callback_query(call.id, "❌ Ты уже голосовал")
        return

    cursor.execute("""
    INSERT INTO votes (
        user_id,
        bike_id,
        vote
    )
    VALUES (?, ?, ?)
    """, (
        call.from_user.id,
        bike_id,
        "like"
    ))

    cursor.execute("""
    UPDATE bikes
    SET likes = likes + 1
    WHERE id=?
    """, (bike_id,))

    conn.commit()

    update_bike(call, bike_id)

    bot.answer_callback_query(call.id, "👍 Лайк")


# ================= ДИЗЛАЙК =================
@bot.callback_query_handler(func=lambda call: call.data.startswith("dislike_"))
def dislike(call):

    bike_id = int(call.data.split("_")[1])

    cursor.execute("""
    SELECT *
    FROM votes
    WHERE user_id=? AND bike_id=?
    """, (
        call.from_user.id,
        bike_id
    ))

    vote = cursor.fetchone()

    if vote:
        bot.answer_callback_query(call.id, "❌ Ты уже голосовал")
        return

    cursor.execute("""
    INSERT INTO votes (
        user_id,
        bike_id,
        vote
    )
    VALUES (?, ?, ?)
    """, (
        call.from_user.id,
        bike_id,
        "dislike"
    ))

    cursor.execute("""
    UPDATE bikes
    SET dislikes = dislikes + 1
    WHERE id=?
    """, (bike_id,))

    conn.commit()

    update_bike(call, bike_id)

    bot.answer_callback_query(call.id, "👎 Дизлайк")


# ================= СВАЙП =================
@bot.callback_query_handler(func=lambda call:
    call.data.startswith("next_") or
    call.data.startswith("prev_"))
def swipe(call):

    bike_id = int(call.data.split("_")[1])

    update_bike(call, bike_id)


# ================= ОБНОВЛЕНИЕ =================
def update_bike(call, bike_id):

    cursor.execute("""
    SELECT *
    FROM bikes
    WHERE id=?
    """, (bike_id,))

    bike = cursor.fetchone()

    if not bike:
        return

    try:
        bot.edit_message_media(
            media=telebot.types.InputMediaPhoto(
                bike[3],
                caption=bike_caption(bike)
            ),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=bike_markup(bike[1], bike_id)
        )
    except:
        pass


# ================= EMPTY =================
@bot.callback_query_handler(func=lambda call: call.data == "empty")
def empty(call):
    bot.answer_callback_query(call.id)


# ================= START =================
print("                                                                                                                                                                                                                        CRANK UNIONS QYZYLORDA FIXED GROUP                                                                                                                                                                                                                        ")

bot.infinity_polling()
