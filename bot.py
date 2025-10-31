import asyncio
import os
import re
import time
import json
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession

# ==== কনফিগারেশন লোড করা ====
# Render.com environment variables
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
SESSION_STRING = os.getenv('SESSION_STRING', '')

OTP_SOURCE_CHAT = int(os.getenv('OTP_SOURCE_CHAT', 0))
OTP_TARGET_CHAT = int(os.getenv('OTP_TARGET_CHAT', 0))
FILE_SOURCE_CHAT = int(os.getenv('FILE_SOURCE_CHAT', 0))
FILE_TARGET_CHAT = int(os.getenv('FILE_TARGET_CHAT', 0))

YOUR_GROUP_LINK = os.getenv('YOUR_GROUP_LINK', "https://t.me/default_group")
YOUR_CHANNEL_LINK = os.getenv('YOUR_CHANNEL_LINK', "https://t.me/default_channel")

print("🚀 Starting Telegram OTP Bot on Render.com...")

# Session setup for Render.com
if SESSION_STRING:
    print("🔑 Using Session String authentication...")
    client = TelegramClient(
        StringSession(SESSION_STRING),
        API_ID,
        API_HASH,
        connection_retries=5,
        timeout=15,
        flood_sleep_threshold=0
    )
else:
    print("🔑 Using session file authentication...")
    client = TelegramClient(
        'user_forward_session',
        API_ID,
        API_HASH,
        connection_retries=5,
        timeout=15,
        flood_sleep_threshold=0
    )

# ডিফল্ট কনস্ট্যান্টস
DEFAULT_COUNTRY_NAME = "Unknown"
DEFAULT_FLAG = "🌍"
DEFAULT_DIAL_CODE = "Unknown"

# ==== কান্ট্রি ডেটা সেটআপ ====
COUNTRY_DATA = {}
COUNTRY_DATA_FILE = 'country_flags.json'

def load_country_data():
    """`country_flags.json` থেকে ডেটা লোড করে বা একটি ডিফল্ট সেট তৈরি করে।"""
    global COUNTRY_DATA
    try:
        with open(COUNTRY_DATA_FILE, 'r', encoding='utf-8') as f:
            COUNTRY_DATA = json.load(f)
        print(f"✅ Country data loaded from {COUNTRY_DATA_FILE}")
    except FileNotFoundError:
        print(f"⚠️ {COUNTRY_DATA_FILE} not found. Creating a basic country data dictionary.")
        COUNTRY_DATA = {
            'sudan': {'flag': '🇸🇩', 'dial_code': '+249'},
            'venezuela': {'flag': '🇻🇪', 'dial_code': '+58'},
            'nepal': {'flag': '🇳🇵', 'dial_code': '+977'},
            'madagascar': {'flag': '🇲🇬', 'dial_code': '+261'},
            'bangladesh': {'flag': '🇧🇩', 'dial_code': '+880'},
            'india': {'flag': '🇮🇳', 'dial_code': '+91'},
            'pakistan': {'flag': '🇵🇰', 'dial_code': '+92'},
            'united states': {'flag': '🇺🇸', 'dial_code': '+1'},
            'uk': {'flag': '🇬🇧', 'dial_code': '+44'},
            # অন্যান্য দেশ যোগ করুন...
        }
        with open(COUNTRY_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(COUNTRY_DATA, f, ensure_ascii=False, indent=4)
        print(f"✅ Basic country data saved to {COUNTRY_DATA_FILE}")

load_country_data()

# ফ্ল্যাগ এবং ডায়ালিং কোড দিয়ে কান্ট্রি ডেটা ম্যাপ তৈরি
FLAG_TO_COUNTRY = {v['flag']: k for k, v in COUNTRY_DATA.items() if 'flag' in v}
DIAL_CODE_TO_COUNTRY = {v['dial_code']: k for k, v in COUNTRY_DATA.items() if 'dial_code' in v}

def get_country_info(country_name=None, flag=None, dial_code=None):
    """দেশের নাম, পতাকা বা ডায়ালিং কোড থেকে দেশের তথ্য খুঁজে বের করে।"""
    if country_name:
        for k, v in COUNTRY_DATA.items():
            if k.lower() == country_name.lower() or v.get('name', '').lower() == country_name.lower():
                return k.title(), v.get('flag', DEFAULT_FLAG), v.get('dial_code', DEFAULT_DIAL_CODE)
    if flag:
        country_key = FLAG_TO_COUNTRY.get(flag)
        if country_key:
            return country_key.title(), COUNTRY_DATA[country_key]['flag'], COUNTRY_DATA[country_key].get('dial_code', DEFAULT_DIAL_CODE)
    if dial_code:
        country_key = DIAL_CODE_TO_COUNTRY.get(dial_code)
        if country_key:
            return country_key.title(), COUNTRY_DATA[country_key]['flag'], COUNTRY_DATA[country_key]['dial_code']
    return DEFAULT_COUNTRY_NAME, DEFAULT_FLAG, DEFAULT_DIAL_CODE

def mask_phone_number(num: str) -> str:
    """ফোন নম্বরের মাঝের অংশ **** দিয়ে মাস্কিং করে।"""
    num = num.replace(' ', '').replace('-', '')
    
    if len(num) < 7:
        return num

    if num.startswith('+'):
        prefix_match = re.match(r'^\+\d{1,4}', num)
        if prefix_match:
            prefix_str = prefix_match.group(0)
            main_num = num[len(prefix_str):]
            if len(main_num) > 4:
                mask_start = len(main_num) // 3
                mask_end = len(main_num) - (len(main_num) // 3)
                return f"{prefix_str}{main_num[:mask_start]}****{main_num[mask_end:]}"
            return num
        
    if len(num) > 4:
        mask_start = len(num) // 3
        mask_end = len(num) - (len(num) // 3)
        return f"{num[:mask_start]}****{num[mask_end:]}"
    
    return num

def extract_otp_info(original_text):
    """সব তথ্য একসাথে এক্সট্র্যাক্ট করে"""
    otp_patterns = [
        r'(?:otp|code|pin|verify|verification|secret|رمز|কড|kód|codice|código)\s*[:\s-]*\s*(\d{4,8})',
        r'(\d{4,8})\s*(?:is your|হৈছে আপোনাৰ)\s*(?:facebook|whatsapp|verification)?\s*code',
        r'\b(?:G-|Google\s*Code:\s*)(\d{6})\b',
        r'(?:whatsapp|facebook|fb|wa).*?(\d{3}[-\s]?\d{3,4})\b',
        r'(?<!\d)(\d{6})(?!\d)',
        r'(?<!\d)(\d{4})(?!\d)'
    ]

    otp_code = None
    used_pattern = None
    for pattern_str in otp_patterns:
        match = re.search(pattern_str, original_text, re.IGNORECASE)
        if match:
            potential_otp = match.group(1).replace('-', '').replace(' ', '')
            
            if len(potential_otp) >= 9:
                if re.match(r'^\d{1,4}\d{6,}', potential_otp):
                    continue
                
            otp_code = potential_otp
            used_pattern = pattern_str
            break

    country_name_detected = DEFAULT_COUNTRY_NAME
    country_flag_detected = DEFAULT_FLAG
    country_dial_code_detected = DEFAULT_DIAL_CODE

    country_full_match = re.search(r'(?:Country:\s*)?([A-Za-z\s]+)\s*([🇦-🇿]{2,})', original_text)
    if country_full_match:
        c_name_from_text = country_full_match.group(1).strip()
        flag_from_text = country_full_match.group(2)
        
        found_name, found_flag, found_dial = get_country_info(country_name=c_name_from_text)
        if found_name != DEFAULT_COUNTRY_NAME:
            country_name_detected, country_flag_detected, country_dial_code_detected = found_name, found_flag, found_dial
        else:
            found_name, found_flag, found_dial = get_country_info(flag=flag_from_text)
            if found_name != DEFAULT_COUNTRY_NAME:
                country_name_detected, country_flag_detected, country_dial_code_detected = found_name, found_flag, found_dial
            else:
                country_name_detected = c_name_from_text.title()
                country_flag_detected = flag_from_text
    
    if country_name_detected == DEFAULT_COUNTRY_NAME:
        country_name_match = re.search(r'Country:\s*([A-Za-z\s]+)', original_text, re.IGNORECASE)
        if country_name_match:
            c_name_from_text = country_name_match.group(1).strip()
            country_name_detected, country_flag_detected, country_dial_code_detected = get_country_info(country_name=c_name_from_text)
        
    if country_name_detected == DEFAULT_COUNTRY_NAME:
        flag_only_match = re.search(r'([🇦-🇿]{2,})', original_text)
        if flag_only_match:
            flag = flag_only_match.group(1)
            country_name_detected, country_flag_detected, country_dial_code_detected = get_country_info(flag=flag)

    if country_name_detected == DEFAULT_COUNTRY_NAME:
        dial_code_match = re.search(r'(\+\d{1,4})\d{7,15}', original_text)
        if dial_code_match:
            dial_code = dial_code_match.group(1)
            country_name_detected, country_flag_detected, country_dial_code_detected = get_country_info(dial_code=dial_code)

    if country_dial_code_detected == DEFAULT_DIAL_CODE and country_name_detected != DEFAULT_COUNTRY_NAME:
        _, _, temp_dial_code = get_country_info(country_name=country_name_detected)
        if temp_dial_code != DEFAULT_DIAL_CODE:
            country_dial_code_detected = temp_dial_code
    
    final_country_display = f"{country_flag_detected} {country_name_detected}"

    number = "Not Found"
    
    number_match_masked = re.search(r'(?:Number|Phone|মোবাইল|Tel|T:)\s*[:\s]*(\d+\*{3,}\d+)', original_text, re.IGNORECASE)
    if number_match_masked:
        number = number_match_masked.group(1)
    else:
        number_match_full = re.search(r'(?:Number|Phone|মোবাইল|Tel|T:)\s*[:\s]*(\+?\d{7,15})', original_text, re.IGNORECASE)
        if number_match_full:
            number = mask_phone_number(number_match_full.group(1))
        else:
            masked_number_fallback = re.search(r'\d{2,}\*{3,}\d{2,}', original_text)
            if masked_number_fallback:
                number = masked_number_fallback.group(0)
            else:
                potential_number = re.search(r'\+\d{7,15}', original_text)
                if potential_number:
                    number = mask_phone_number(potential_number.group(0))

    service = "General Service"
    service_patterns = {
        'whatsapp|wa': 'WhatsApp', 'facebook|fb': 'Facebook', 'telegram': 'Telegram',
        'instagram': 'Instagram', 'Google|G-': 'Google', 'imo': 'IMO',
        'signal': 'Signal', 'vk': 'VK', 'twitter': 'Twitter', 'apple': 'Apple',
        'microsoft': 'Microsoft', 'snapchat': 'Snapchat', 'discord': 'Discord',
        'tiktok': 'TikTok', 'paypal': 'PayPal', 'amazon': 'Amazon',
        'netflix': 'Netflix', 'binance': 'Binance', 'hbo max': 'HBO Max',
        'viber': 'Viber', 'line': 'LINE', 'wechat': 'WeChat', 'skype': 'Skype',
        'roblox': 'Roblox', 'steam': 'Steam', 'epic games': 'Epic Games',
        'garena': 'Garena', 'free fire': 'Free Fire', 'pubg': 'PUBG',
        'banking|bank': 'Banking/Finance', 'email|mail': 'Email Service',
        'olx': 'OLX', 'uber': 'Uber', 'careem': 'Careem', 'talabat': 'Talabat',
        'foodpanda': 'Foodpanda', 'bKash': 'bKash', 'nagad': 'Nagad',
        'rocket': 'Rocket', 'daraz': 'Daraz', 'pathao': 'Pathao', 'shopee': 'Shopee',
        'lazada': 'Lazada', 'ebay': 'eBay', 'stripe': 'Stripe', 'coinbase': 'Coinbase',
        'bybit': 'Bybit', 'kucoin': 'KuCoin', 'okx': 'OKX'
    }

    found_services = []
    for pattern_str, service_name in service_patterns.items():
        if re.search(r'\b(?:' + pattern_str + r')\b', original_text.lower()):
            found_services.append(service_name)

    if found_services:
        if 'whatsapp' in original_text.lower() and 'WhatsApp' in found_services:
            service = 'WhatsApp'
        elif 'facebook' in original_text.lower() and 'Facebook' in found_services:
            service = 'Facebook'
        elif 'google' in original_text.lower() and 'Google' in found_services:
            service = 'Google'
        else:
            service = ", ".join(sorted(list(set(found_services))))
    elif "your verification code" in original_text.lower() or "your login code" in original_text.lower():
        service = "General Verification"
    elif "your security code" in original_text.lower() or "security alert" in original_text.lower():
        service = "Security Code"
    elif "your password reset" in original_text.lower():
        service = "Password Reset"

    return {
        'otp_code': otp_code,
        'country': final_country_display,
        'number': number,
        'service': service,
        'used_pattern': used_pattern
    }

async def main():
    await client.start()
    print("🔑 Logged in successfully to Render.com!")

    try:
        source_entity = await client.get_entity(OTP_SOURCE_CHAT)
        target_entity = await client.get_entity(OTP_TARGET_CHAT)
        print(f"✅ Source OTP Group: {source_entity.title}")
        print(f"✅ Target OTP Group: {target_entity.title}")

        file_source_entity = await client.get_entity(FILE_SOURCE_CHAT)
        file_target_entity = await client.get_entity(FILE_TARGET_CHAT)
        print(f"✅ Source File Group: {file_source_entity.title}")
        print(f"✅ Target File Group: {file_target_entity.title}")

    except Exception as e:
        print(f"❌ Group access error: {e}")
        return

    @client.on(events.NewMessage(chats=OTP_SOURCE_CHAT))
    async def process_otp(event):
        try:
            start_time = time.time()
            original_text = event.raw_text

            if any(keyword in original_text.lower() for keyword in [
                'welcome', 'hey there', 'joined', 'left', 'group link', 'bot link',
                'https://t.me/', 'subscribe to get otp', 'premium otp',
                'click here', 'join now', 'channel for otp', 'admin here',
                'https://discord.gg/', 'http://', 'https://'
            ]):
                print("❌ ইলিগ্যাল বা ওয়েলকাম মেসেজ স্কিপ করা হলো।")
                return

            print(f"🎯 OTP স্ক্যান করা হচ্ছে...")
            info = extract_otp_info(original_text)

            if not info['otp_code']:
                print("❌ OTP কোড না পেয়ে স্কিপ করা হলো।")
                return

            print(f"✅ OTP Found: {info['otp_code']}")

            current_time = datetime.now().strftime("%I:%M:%S %p")
            current_date = datetime.now().strftime("%d-%m-%Y")

            formatted_message = f"""✅ {info['country']} {info['service']} OTP Received Successfully 🎉

🔑 **OTP Code:** `{info['otp_code']}`

📞 **Number:** `{info['number']}`
🛠️ **Service:** {info['service']}
🌍 **Country:** {info['country']}
⏰ **Time:** {current_time}
📅 **Date:** {current_date}

# Your {info['service']} verification code: `{info['otp_code']}`
Do not share this code with anyone!
"""
            await client.send_message(
                OTP_TARGET_CHAT,
                message=formatted_message,
                buttons=[
                    [Button.url("📢 Main Channel", YOUR_CHANNEL_LINK),
                     Button.url("🔐 Join OTP Group", YOUR_GROUP_LINK)]
                ]
            )

            processing_time = round((time.time() - start_time) * 1000, 2)
            print(f"✅ OTP সেন্ড করা হয়েছে {processing_time}ms এ! ⚡")
            print(f"📍 {info['country']} | 📱 {info['number']} | 🔢 {info['otp_code']} | 🛠️ {info['service']}")

        except Exception as e:
            print(f"🚨 OTP প্রসেসিং এরর: {e}")
            try:
                await client.send_message(
                    OTP_TARGET_CHAT,
                    f"⚠️ Error processing OTP! Could not format. Original message: \n\n`{original_text}`"
                )
            except Exception as fe:
                print(f"🚨 ফেইল্ড টু ফরওয়ার্ড এরর মেসেজ: {fe}")

    @client.on(events.NewMessage(chats=FILE_SOURCE_CHAT))
    async def forward_file(event):
        if event.file or event.media:
            try:
                caption = event.raw_text or ""
                cleaned_caption = re.sub(r'@\w+|t\.me/\S+|telegram\.me/\S+|OTP\s*:\s*JOIN HERE|http\S+|https\S+', '', caption, flags=re.IGNORECASE).strip()

                await client.send_file(
                    FILE_TARGET_CHAT,
                    file=event.media,
                    caption=cleaned_caption if cleaned_caption else None,
                    buttons=[Button.url("🔐 OTP Group Join Here", YOUR_GROUP_LINK)]
                )
                print(f"📁 ফাইল ফরওয়ার্ড করা হয়েছে!")
            except Exception as e:
                print(f"❌ ফাইল ফরওয়ার্ডিং এরর: {e}")

    print("🤖 চূড়ান্ত ইন্টেলিজেন্ট বট চালু!")
    print("⚡ আল্ট্রা-ফাস্ট OTP প্রসেসিং...")
    print("📡 OTP এবং ফাইল মেসেজের জন্য অপেক্ষা করছি...")
    print("=" * 50)

    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())