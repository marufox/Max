import telebot
import instaloader
import time
import os
import pyotp
import threading
from telebot import types
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============= Bot Token Input =============
print("🤖 Enter your bot token:")
BOT_TOKEN = input("TOKEN: ").strip()

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

# ============= Cookie Extractor Function with detailed error =============
def extract_cookie(username, password, twofa_key):
    L = instaloader.Instaloader(quiet=True)
    try:
        try:
            L.login(username, password)
        except Exception as login_error:
            error_str = str(login_error).lower()
            
            # Check if 2FA is needed
            if "two factor" in error_str or "2fa" in error_str or "two-factor" in error_str:
                if twofa_key and twofa_key != "":
                    try:
                        totp = pyotp.TOTP(twofa_key.replace(" ", "")).now()
                        L.two_factor_login(totp)
                    except Exception as twofa_error:
                        return False, "2FA key is incorrect or expired", username
                else:
                    return False, "2FA required but no key provided", username
            else:
                # Check for other login errors
                if "password" in error_str or "invalid password" in error_str:
                    return False, "Incorrect password", username
                elif "user not found" in error_str or "no user" in error_str:
                    return False, "Username does not exist", username
                elif "suspended" in error_str or "blocked" in error_str:
                    return False, "Account is suspended or blocked", username
                elif "rate limit" in error_str or "too many" in error_str:
                    return False, "Rate limited by Instagram (try later)", username
                else:
                    return False, f"Login failed: {login_error[:50]}", username
        
        # Get cookies after successful login
        cookies = L.context._session.cookies.get_dict()
        if not cookies:
            return False, "No cookies received from Instagram", username
        
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        return True, cookie_str, username
        
    except Exception as e:
        error_msg = str(e)[:60]
        return False, f"Error: {error_msg}", username

# ============= Bot Commands =============
@bot.message_handler(commands=['start'])
def start_command(message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🍪 Extract Cookies")
    
    bot.send_message(message.chat.id, 
        "⚡ *Instagram Cookie Extractor Bot* ⚡\n\n"
        "🚀 *Super Fast - 100 IDs in 30 seconds*\n\n"
        "👇 *Click below to start* 👇",
        parse_mode="Markdown",
        reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🍪 Extract Cookies")
def ask_username(message):
    bot.send_message(message.chat.id, 
        "📝 *Enter usernames* (one per line):\n\n"
        "⚡ *Maximum 100*\n\n"
        "Example:\n"
        "`user1`\n`user2`\n`user3`",
        parse_mode="Markdown",
        reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, get_usernames)

def get_usernames(message):
    usernames = [u.strip() for u in message.text.split('\n') if u.strip()]
    
    if not usernames or len(usernames) > 100:
        bot.send_message(message.chat.id, "❌ Please enter 1-100 usernames!")
        return start_command(message)
    
    user_data[message.chat.id] = {'usernames': usernames}
    bot.send_message(message.chat.id, 
        f"✅ {len(usernames)} usernames received\n\n🔐 *Enter password:*", 
        parse_mode="Markdown")
    bot.register_next_step_handler(message, get_password)

def get_password(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        return start_command(message)
    
    user_data[chat_id]['password'] = message.text.strip()
    bot.send_message(chat_id, 
        "🔑 *Enter 2FA keys* (one per line):\n\n"
        f"📌 *{len(user_data[chat_id]['usernames'])} keys required*\n"
        "📌 One key per username (same order)\n\n"
        "⚠️ If no 2FA, still need to provide a key or press Enter",
        parse_mode="Markdown")
    bot.register_next_step_handler(message, get_2fa)

def get_2fa(message):
    chat_id = message.chat.id
    if chat_id not in user_data:
        return start_command(message)
    
    twofas = [t.strip() for t in message.text.split('\n') if t.strip()]
    usernames = user_data[chat_id]['usernames']
    username_count = len(usernames)
    twofa_count = len(twofas)
    
    # Check if counts match
    if username_count != twofa_count:
        error_msg = (
            f"❌ *Mismatch Error!*\n\n"
            f"📊 Usernames: {username_count}\n"
            f"🔑 2FA Keys: {twofa_count}\n\n"
            f"⚠️ *Reason:* Number of 2FA keys does not match number of usernames.\n\n"
            f"✅ You need to provide EXACTLY {username_count} 2FA key(s).\n\n"
            f"💡 Tip: If no 2FA, just press Enter for each account"
        )
        bot.send_message(chat_id, error_msg, parse_mode="Markdown")
        
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("🍪 Extract Cookies")
        bot.send_message(chat_id, "Press the button below to start over", reply_markup=kb)
        
        del user_data[chat_id]
        return
    
    password = user_data[chat_id]['password']
    
    bot.send_message(chat_id, 
        f"⚡ *Processing {username_count} accounts...*\n\n"
        f"✅ {twofa_count} 2FA keys matched\n\n"
        f"🚀 *Please wait (10 threads parallel)*", 
        parse_mode="Markdown")
    
    threading.Thread(target=process_accounts_fast, 
                    args=(chat_id, usernames, password, twofas), 
                    daemon=True).start()
    
    del user_data[chat_id]

def process_accounts_fast(chat_id, usernames, password, twofas):
    results = []
    success_count = 0
    total = len(usernames)
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {}
        for i, username in enumerate(usernames):
            twofa = twofas[i] if i < len(twofas) else ""
            future = executor.submit(extract_cookie, username, password, twofa)
            futures[future] = i + 1
        
        for future in as_completed(futures):
            success, reason, username = future.result()
            serial = futures[future]
            
            if success:
                results.append(f"{username}|{password}|{reason}")
                success_count += 1
                bot.send_message(chat_id, f"✅ `{serial}.` **Success:** `{username}`", parse_mode="Markdown")
            else:
                # Show detailed reason for failure
                bot.send_message(chat_id, 
                    f"❌ `{serial}.` **Failed:** `{username}`\n"
                    f"📌 *Reason:* `{reason}`", 
                    parse_mode="Markdown")
    
    # Save results
    if results:
        filename = f"cookies_{chat_id}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n".join(results))
        
        with open(filename, "rb") as f:
            bot.send_document(chat_id, f, 
                caption=f"🍪 *Cookies Extracted*\n\n"
                       f"✅ **Success:** {success_count}/{total}\n"
                       f"❌ **Failed:** {total-success_count}\n"
                       f"🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode="Markdown")
        os.remove(filename)
    else:
        bot.send_message(chat_id, 
            f"❌ *No cookies extracted!*\n\n"
            f"📊 **Total:** {total} accounts\n"
            f"💡 **All failed.** Check:\n"
            f"• Usernames exist?\n"
            f"• Password correct?\n"
            f"• 2FA keys valid?",
            parse_mode="Markdown")
    
    # Return keyboard
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🍪 Extract Cookies")
    
    bot.send_message(chat_id, 
        f"🏁 *Task Complete!*\n\n"
        f"✅ **Success:** {success_count}\n"
        f"❌ **Failed:** {total-success_count}\n\n"
        f"🔄 Ready for next task",
        parse_mode="Markdown",
        reply_markup=kb)

# ============= Run Bot =============
print(f"\n✅ Bot is running!")
print(f"👉 @{bot.get_me().username}")
print(f"⚡ 10 threads - 100 IDs in ~30 seconds")
print(f"📊 Detailed error messages enabled\n")

bot.infinity_polling()