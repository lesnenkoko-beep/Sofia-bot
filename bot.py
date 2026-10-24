import datetime
import sqlite3
import telebot
from telebot import types
import threading
import time

from config import TOKEN, COACH_TELEGRAM_IDS, DEV_TELEGRAM_ID

bot = telebot.TeleBot(TOKEN)

# Ініціалізація бази даних
conn = sqlite3.connect('clients.db', check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        balance INTEGER,
        attended INTEGER DEFAULT 0,
        expiry_date TEXT,
        tg_id INTEGER DEFAULT NULL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        studio TEXT,
        date_time TEXT,
        info TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        action_date TEXT
    )
''')
conn.commit()

# --- ФУНКЦІЇ КЛАВІАТУР ---
def get_coach_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('➕ Додати клієнтку', '⚙️ Керувати балансом')
    markup.add('📅 Мої тренування', '➕ Додати тренування в розклад')
    markup.add('📋 Список клієнток', '🔗 Отримати посилання')
    return markup

def get_client_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add('💳 Мій абонемент', '📅 Розклад тренувань')
    return markup

# --- ЗАХИЩЕНЕ ТЕСТОВЕ ПЕРЕКЛЮЧЕННЯ (ТІЛЬКИ ДЛЯ DEV) ---
test_modes = {}

def is_coach(user_id):
    if user_id not in COACH_TELEGRAM_IDS:
        return False
    if user_id == DEV_TELEGRAM_ID and test_modes.get(user_id) == 'client':
        return False
    return True

@bot.message_handler(commands=['as_client'])
def switch_to_client(message):
    if message.from_user.id == DEV_TELEGRAM_ID:
        test_modes[message.from_user.id] = 'client'
        bot.send_message(
            message.chat.id,
            "🔀 Режим тесту: тепер ти **Клієнт**.\nЩоб повернути меню тренера, напиши /as_coach",
            reply_markup=get_client_markup(),
            parse_mode='HTML'
        )

@bot.message_handler(commands=['as_coach'])
def switch_to_coach(message):
    if message.from_user.id == DEV_TELEGRAM_ID:
        test_modes[message.from_user.id] = 'coach'
        bot.send_message(
            message.chat.id,
            "🔀 Режим тесту: тепер ти знову **Тренер**.",
            reply_markup=get_coach_markup(),
            parse_mode='HTML'
        )

# --- ФОНОВА ПЕРЕВІРКА ---
def daily_check():
    while True:
        try:
            now = datetime.datetime.now()
            if now.hour == 10:
                conn_t = sqlite3.connect('clients.db', check_same_thread=False)
                cursor_t = conn_t.cursor()
                cursor_t.execute("SELECT name, tg_id, expiry_date FROM clients WHERE balance > 0")

                for row in cursor_t.fetchall():
                    name, tg_id, expiry_date = row
                    try:
                        exp_d = datetime.datetime.strptime(expiry_date, '%d.%m.%Y').date()
                        tomorrow = datetime.date.today() + datetime.timedelta(days=1)

                        if exp_d == tomorrow:
                            if tg_id:
                                bot.send_message(tg_id, f"⚠️ <b>Нагадування:</b> твій абонемент закінчується вже завтра ({expiry_date})!", parse_mode='HTML')
                            for coach in COACH_TELEGRAM_IDS:
                                bot.send_message(coach, f"🔔 <b>Увага:</b> У клієнтки <b>{name}</b> абонемент закінчується завтра ({expiry_date})!", parse_mode='HTML')
                    except Exception:
                        pass
                conn_t.close()
                time.sleep(7200)
            else:
                time.sleep(1800)
        except Exception:
            time.sleep(1800)

threading.Thread(target=daily_check, daemon=True).start()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id

    if is_coach(user_id):
        text_msg = "Привіт, Софіє! Головне меню тренера 👇"
        if user_id == DEV_TELEGRAM_ID:
            text_msg += "\n\n*(Тест-режим: ти можеш писати /as_client, щоб перевіряти бот як учениця)*"
        bot.send_message(message.chat.id, text_msg, reply_markup=get_coach_markup(), parse_mode='HTML')
        return

    if len(message.text.split()) > 1:
        client_id = message.text.split()[1]
        cursor.execute("SELECT name, tg_id FROM clients WHERE id = ?", (client_id,))
        res = cursor.fetchone()

        if res:
            if res[1] is None:
                cursor.execute("UPDATE clients SET tg_id = ? WHERE id = ?", (user_id, client_id))
                conn.commit()

                bot.send_message(
                    message.chat.id,
                    f"🎉 Супер! Твій профіль <b>{res[0]}</b> успішно прив'язано.\nТепер ти можеш перевіряти свій залишок кнопкою нижче.",
                    reply_markup=get_client_markup(),
                    parse_mode='HTML'
                )

                for coach in COACH_TELEGRAM_IDS:
                    try:
                        bot.send_message(coach, f"🎉 Клієнтка <b>{res[0]}</b> успішно активувала свій абонемент у боті!", parse_mode='HTML')
                    except:
                        pass

            elif res[1] == user_id:
                bot.send_message(message.chat.id, "Твій профіль вже було прив'язано раніше!", reply_markup=get_client_markup())
            else:
                bot.send_message(message.chat.id, "❌ Це посилання вже використане іншою людиною.", reply_markup=get_client_markup())
        else:
            bot.send_message(message.chat.id, "❌ Помилка: абонемент не знайдено.", reply_markup=get_client_markup())
        return

    cursor.execute("SELECT name FROM clients WHERE tg_id = ?", (user_id,))
    client = cursor.fetchone()
    if client:
        bot.send_message(
            message.chat.id,
            f"Привіт, {client[0]}! Раді бачити тебе на тренуваннях 💪",
            reply_markup=get_client_markup()
        )
    else:
        bot.send_message(
            message.chat.id,
            "Привіт! Твій профіль поки не прив'язано до жодного абонемента. Перейди за посиланням від тренера.",
            reply_markup=get_client_markup()
        )

# --- ЛОГІКА ТРЕНЕРА ---
@bot.message_handler(func=lambda msg: is_coach(msg.from_user.id))
def coach_actions(message):
    text = message.text

    if text == '📋 Список клієнток':
        cursor.execute("SELECT id, name, balance, attended, expiry_date FROM clients WHERE balance > 0")
        rows = cursor.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "Активних абонементів наразі немає.")
            return

        resp = "📋 <b>Активні клієнтки:</b>\n\n"
        for r in rows:
            resp += f"👤 <b>{r[1]}</b>\n• Залишок: {r[2]}\n• Відвідала: {r[3]}\n• Діє до: {r[4]}\n\n"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')

    elif text == '➕ Додати клієнтку':
        msg = bot.send_message(
            message.chat.id,
            "Введи дані у форматі:\n<code>Ім'я Заняття [Дата]</code>\n\n"
            "<i>Наприклад:</i> Олена 8 або Олена 8 25.11.2026",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_add_client)

    elif text == '⚙️ Керувати балансом':
        cursor.execute("SELECT id, name, balance FROM clients")
        rows = cursor.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "Список клієнток порожній.")
            return

        markup = types.InlineKeyboardMarkup()
        for r in rows:
            markup.add(types.InlineKeyboardButton(f"{r[1]} (залишок: {r[2]})", callback_data=f"manage_{r[0]}"))
        bot.send_message(message.chat.id, "Обери клієнтку для керування балансом:", reply_markup=markup)

    elif text == '🔗 Отримати посилання':
        cursor.execute("SELECT id, name FROM clients")
        rows = cursor.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "База клієнток порожня.")
            return

        markup = types.InlineKeyboardMarkup()
        for r in rows:
            markup.add(types.InlineKeyboardButton(r[1], callback_data=f"link_{r[0]}"))
        bot.send_message(message.chat.id, "Обери клієнтку, щоб отримати посилання:", reply_markup=markup)

    elif text == '➕ Додати тренування в розклад':
        msg = bot.send_message(
            message.chat.id,
            "Введи дані тренування у форматі:\n<code>Студія / Місто | Дата та час | Деталі</code>\n\n"
            "<i>Наприклад:</i>\nСтудія FitSpace | 20.10.2026 14:00 | Групове стретчинг",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_add_schedule)

    elif text == '📅 Мої тренування':
        cursor.execute("SELECT id, studio, date_time, info FROM schedule ORDER BY id DESC")
        rows = cursor.fetchall()
        if not rows:
            bot.send_message(message.chat.id, "У розкладі поки немає тренувань.")
            return

        markup = types.InlineKeyboardMarkup()
        for r in rows:
            markup.add(types.InlineKeyboardButton(f"📍 {r[1]} | ⏰ {r[2]}", callback_data=f"sched_{r[0]}"))
        bot.send_message(message.chat.id, "📅 <b>Твоє актуальне розклад:</b>\nОбери тренування, щоб керувати ним:", reply_markup=markup, parse_mode='HTML')

def process_add_client(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            raise ValueError

        last_part = parts[-1]
        try:
            valid_date = datetime.datetime.strptime(last_part, '%d.%m.%Y').date()
            expiry = valid_date.strftime('%d.%m.%Y')
            balance = int(parts[-2])
            name = " ".join(parts[:-2]).strip()
        except ValueError:
            balance = int(parts[-1])
            name = " ".join(parts[:-1]).strip()
            expiry = (datetime.date.today() + datetime.timedelta(days=30)).strftime('%d.%m.%Y')

        cursor.execute(
            "INSERT INTO clients (name, balance, attended, expiry_date) VALUES (?, ?, 0, ?)",
            (name, balance, expiry)
        )
        conn.commit()

        client_id = cursor.lastrowid
        bot_username = bot.get_me().username
        invite_link = "https://t.me/" + str(bot_username) + "?start=" + str(client_id)

        text_reply = (
            f"✅ Клієнтку <b>{name}</b> додано!\n"
            f"Абонемент на {balance} занять, діє до {expiry}.\n\n"
            f"🔗 <b>Посилання для неї:</b>\n{invite_link}"
        )
        bot.send_message(message.chat.id, text_reply, parse_mode='HTML', disable_web_page_preview=True)
    except Exception:
        bot.send_message(message.chat.id, "❌ Помилка формату. Спробуй ще раз (наприклад: Олена 8).")

def process_add_schedule(message):
    try:
        parts = message.text.split('|')
        if len(parts) < 2:
            raise ValueError

        studio = parts[0].strip()
        date_time = parts[1].strip()
        info = parts[2].strip() if len(parts) > 2 else "Тренування"

        cursor.execute("INSERT INTO schedule (studio, date_time, info) VALUES (?, ?, ?)", (studio, date_time, info))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Тренування успішно додано до розкладу!\n📍 <b>{studio}</b>\n⏰ {date_time}", parse_mode='HTML')
    except Exception:
        bot.send_message(message.chat.id, "❌ Помилка формату. Використовуй риску '|' (наприклад: Студія | 20.10.2026 12:00 | Опис)")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    data = call.data

    if data.startswith('manage_'):
        client_id = int(data.split('_')[1])
        cursor.execute("SELECT name, balance, attended FROM clients WHERE id = ?", (client_id,))
        res = cursor.fetchone()
        if not res:
            return
        name, balance, attended = res

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("➖ Списати (-1)", callback_data=f"bal_spend_{client_id}"),
            types.InlineKeyboardButton("➕ Повернути (+1)", callback_data=f"bal_return_{client_id}")
        )
        markup.add(
            types.InlineKeyboardButton("➕ Додати +5 занять", callback_data=f"bal_add5_{client_id}"),
            types.InlineKeyboardButton("📜 Історія відвідувань", callback_data=f"bal_history_{client_id}")
        )
        markup.add(
            types.InlineKeyboardButton("🗑 Видалити клієнтку", callback_data=f"bal_del_{client_id}")
        )
        bot.edit_message_text(
            f"👤 Клієнтка: <b>{name}</b>\n🔢 Залишок: {balance}\n✅ Відвідала: {attended}\n\nОбери дію:",
            call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='HTML'
        )

    elif data.startswith('bal_'):
        parts = data.split('_')
        action = parts[1]
        client_id = int(parts[2])

        cursor.execute("SELECT name, balance, attended, tg_id FROM clients WHERE id = ?", (client_id,))
        res = cursor.fetchone()
        if not res:
            return
        name, balance, attended, tg_id = res

        if action == 'history':
            cursor.execute("SELECT action_date FROM history WHERE client_id = ? ORDER BY id DESC LIMIT 10", (client_id,))
            hist_rows = cursor.fetchall()
            if not hist_rows:
                bot.answer_callback_query(call.id, "Історія відвідувань порожня.", show_alert=True)
                return
            h_text = f"📜 <b>Історія відвідувань ({name}):</b>\n\n"
            for hr in hist_rows:
                h_text += f"• {hr[0]}\n"
            bot.send_message(call.message.chat.id, h_text, parse_mode='HTML')
            return

        if action == 'spend' and balance > 0:
            balance -= 1
            attended += 1
            now_str = datetime.datetime.now().strftime('%d.%m.%Y о %H:%M')
            cursor.execute("INSERT INTO history (client_id, action_date) VALUES (?, ?)", (client_id, now_str))
            conn.commit()

            msg_text = f"✅ Тренування списано для <b>{name}</b>. Залишок: {balance}"

            # --- РОМАНТИЧНЕ ПОВІДОМЛЕННЯ СОНІ ---
            for coach_id in COACH_TELEGRAM_IDS:
                try:
                    bot.send_message(coach_id, "❤️ Я люблю тебе, ти найкращий тренер! 🌸", parse_mode='HTML')
                except:
                    pass

            if tg_id:
                try: bot.send_message(tg_id, f"🏋️‍♀️ Твоє тренування зараховано! Залишок: <b>{balance}</b>", parse_mode='HTML')
                except: pass
        elif action == 'return':
            balance += 1
            attended = max(0, attended - 1)
            msg_text = f"↩️ Заняття повернено для <b>{name}</b>. Залишок: {balance}"
        elif action == 'add5':
            balance += 5
            msg_text = f"➕ Додано 5 занять для <b>{name}</b>. Залишок: {balance}"
        elif action == 'del':
            cursor.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            conn.commit()
            bot.edit_message_text(f"🗑 Клієнтку <b>{name}</b> видалено.", call.message.chat.id, call.message.message_id, parse_mode='HTML')
            return
        else:
            return

        cursor.execute("UPDATE clients SET balance = ?, attended = ? WHERE id = ?", (balance, attended, client_id))
        conn.commit()
        bot.edit_message_text(f"{msg_text}\n\nКерування завершено.", call.message.chat.id, call.message.message_id, parse_mode='HTML')

    elif data.startswith('link_'):
        client_id = int(data.split('_')[1])
        cursor.execute("SELECT name FROM clients WHERE id = ?", (client_id,))
        res = cursor.fetchone()
        if res:
            bot_username = bot.get_me().username
            invite_link = "https://t.me/" + str(bot_username) + "?start=" + str(client_id)
            bot.send_message(call.message.chat.id, f"🔗 Посилання для <b>{res[0]}</b>:\n\n{invite_link}", parse_mode='HTML', disable_web_page_preview=True)

    elif data.startswith('sched_'):
        sched_id = int(data.split('_')[1])
        cursor.execute("SELECT studio, date_time, info FROM schedule WHERE id = ?", (sched_id,))
        res = cursor.fetchone()
        if not res:
            return
        studio, date_time, info = res

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Скасувати (видалити) тренування", callback_data=f"schedel_{sched_id}"))
        bot.edit_message_text(
            f"📍 Студія: <b>{studio}</b>\n⏰ Час: <b>{date_time}</b>\n📝 Info: {info}\n\nОбери дію:",
            call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='HTML'
        )

    elif data.startswith('schedel_'):
        sched_id = int(data.split('_')[1])
        cursor.execute("DELETE FROM schedule WHERE id = ?", (sched_id,))
        conn.commit()
        bot.edit_message_text("🗑 Тренування успішно видалено з розкладу.", call.message.chat.id, call.message.message_id, parse_mode='HTML')

@bot.message_handler(func=lambda msg: msg.text == '💳 Мій абонемент')
def client_check_balance(message):
    user_id = message.from_user.id
    cursor.execute("SELECT name, balance, attended, expiry_date FROM clients WHERE tg_id = ?", (user_id,))
    client = cursor.fetchone()
    if client:
        bot.send_message(
            message.chat.id,
            f"📋 <b>Твій абонемент:</b>\n\n"
            f"👤 Клієнтка: {client[0]}\n"
            f"🔢 Залишок занять: <b>{client[1]}</b>\n"
            f"✅ Відвідано тренувань: {client[2]}\n"
            f"⏳ Дійсний до: <b>{client[3]}</b>",
            parse_mode='HTML'
        )
    else:
        bot.send_message(
            message.chat.id,
            "Твій профіль ще не прив'язано до системи. Попроси у тренера своє персональне посилання.",
            parse_mode='HTML'
        )

@bot.message_handler(func=lambda msg: msg.text == '📅 Розклад тренувань')
def client_check_schedule(message):
    cursor.execute("SELECT studio, date_time, info FROM schedule ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "Наразі немає запланованих тренувань у розкладі.")
        return

    text = "📅 <b>Актуальний розклад студій:</b>\n\n"
    for r in rows:
        text += f"📍 <b>{r[0]}</b>\n⏰ Час: {r[1]}\n📝 {r[2]}\n\n"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

if __name__ == '__mai
