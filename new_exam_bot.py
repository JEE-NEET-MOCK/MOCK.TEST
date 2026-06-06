import os
import json
import base64
import random
import string
import asyncio
import aiohttp
import psycopg2
from telethon import TelegramClient, events, Button
from aiohttp import web

# --- CONFIGURATION ---
API_ID = int(os.getenv('API_ID', '30688814'))
API_HASH = os.getenv('API_HASH', 'd7dd867948fd288636f93851566c8543')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8683671263:AAFrdR1433jORzIuNniMKwDQ-SoDZRrgXao')
YOUR_GITHUB_WEBSITE = "https://jee-neet-mock.github.io/MOCK.TEST" 
SUPABASE_URL = os.getenv('SUPABASE_URL', 'postgresql://postgres:Dhiraj%400078@db.jebcvrozypxsnfmfbgie.supabase.co:5432/postgres')

# --- STATE MANAGEMENT ---
STATE_FILE = "exam_bot_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except: pass
    return {"active_tests": {}}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

bot_state = load_state()
active_tests = bot_state.setdefault("active_tests", {})

client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

user_selections = {} # To temporarily store their subject choice

def get_db():
    return psycopg2.connect(SUPABASE_URL)

async def create_telegraph_page(test_name, questions_list):
    async with aiohttp.ClientSession() as session:
        for attempt in range(5):
            try:
                acc_payload = {'short_name': 'JEEBot', 'author_name': 'JEE Exam Bot'}
                async with session.get('https://api.telegra.ph/createAccount', params=acc_payload, timeout=60) as r:
                    r_data = await r.json()
                    token = r_data['result']['access_token']
                
                json_str = json.dumps(questions_list)
                b64_encoded_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
                
                content = []
                for i in range(0, len(b64_encoded_str), 4000):
                    content.append({"tag": "p", "children": [b64_encoded_str[i:i+4000]]})
                    
                payload = {'access_token': token, 'title': test_name, 'content': content}
                async with session.post('https://api.telegra.ph/createPage', json=payload, timeout=60) as r2:
                    r2_data = await r2.json()
                    return r2_data['result']['path']
            except Exception as e:
                await asyncio.sleep(2)
    return None

# --- 1. START COMMAND & SUBJECT SELECTION ---
@client.on(events.NewMessage(pattern=r'^/start$'))
async def start_handler(event):
    buttons = [
        [Button.inline("🧪 Physics", b"subj_Physics"), Button.inline("⚗️ Chemistry", b"subj_Chemistry")],
        [Button.inline("📐 Mathematics", b"subj_Mathematics"), Button.inline("🏆 Full Mock Test", b"subj_Full")]
    ]
    await event.respond("👋 Welcome to the Dynamic JEE Exam Bot!\n\n📚 **Select a Subject to begin:**", buttons=buttons)

@client.on(events.CallbackQuery(pattern=b'^subj_(.*)'))
async def subject_callback(event):
    subject = event.pattern_match.group(1).decode('utf-8')
    user_id = event.sender_id
    user_selections[user_id] = subject
    
    if subject == "Full":
        await generate_test_logic(event, "Full", 75)
    else:
        buttons = [
            [Button.inline("10 Questions", b"num_10"), Button.inline("25 Questions", b"num_25")],
            [Button.inline("50 Questions", b"num_50"), Button.inline("🔙 Back", b"back_to_subj")]
        ]
        await event.edit(f"✅ You selected **{subject}**.\n\n🔢 **How many questions do you want?**", buttons=buttons)

@client.on(events.CallbackQuery(pattern=b'^back_to_subj$'))
async def back_callback(event):
    buttons = [
        [Button.inline("🧪 Physics", b"subj_Physics"), Button.inline("⚗️ Chemistry", b"subj_Chemistry")],
        [Button.inline("📐 Mathematics", b"subj_Mathematics"), Button.inline("🏆 Full Mock Test", b"subj_Full")]
    ]
    await event.edit("📚 **Select a Subject to begin:**", buttons=buttons)

# --- 2. GENERATE THE TEST ---
@client.on(events.CallbackQuery(pattern=b'^num_(\d+)'))
async def generate_test(event):
    num_q = int(event.pattern_match.group(1).decode('utf-8'))
    user_id = event.sender_id
    subject = user_selections.get(user_id, "Physics")
    await generate_test_logic(event, subject, num_q)

async def generate_test_logic(event, subject, num_q, target_channel=None):
    msg = await event.respond("⏳ Generating your custom test from the cloud database...") if target_channel else await event.edit("⏳ Generating your custom test from the cloud database...")
    
    conn = get_db()
    c = conn.cursor()
    
    if subject == "Full":
        questions_db = []
        for s in ["physics", "chemistry", "mathematics"]:
            c.execute("SELECT subject, question_text, correct_option FROM questions WHERE subject=%s ORDER BY RANDOM() LIMIT 25", (s,))
            questions_db.extend(c.fetchall())
    else:
        db_subj = subject.lower()
        c.execute("SELECT subject, question_text, correct_option FROM questions WHERE subject=%s ORDER BY RANDOM() LIMIT %s", (db_subj, num_q))
        questions_db = c.fetchall()
        
    conn.close()
    
    if not questions_db:
        await msg.edit("❌ Not enough questions in the database for this subject yet!")
        return
        
    # Format for Website
    exam_questions = []
    for row in questions_db:
        exam_questions.append({
            "s": row[0],
            "type": "MCQ",
            "l": row[1],
            "c": row[2]
        })
        
    test_name = f"{subject} Practice Test"
    telegraph_path = await create_telegraph_page(test_name, exam_questions)
    
    if not telegraph_path:
        await msg.edit("❌ Failed to generate Secure Link. Try again.")
        return
        
    db_id = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    active_tests[db_id] = { "name": test_name, "questions": exam_questions }
    save_state(bot_state)
    
    bot_info = await client.get_me()
    web_app_url = f"{YOUR_GITHUB_WEBSITE}/?testid={db_id}&tpath={telegraph_path}&bot={bot_info.username}"
    share_url = f"https://t.me/share/url?url={web_app_url}&text=Take%20this%20{test_name.replace(' ', '%20')}%20Challenge!"
    
    text = (f"🎯 **YOUR CUSTOM TEST IS READY!** 🎯\n\n"
            f"📌 **Topic:** `{test_name}`\n"
            f"🔢 **Questions:** `{len(exam_questions)}`\n"
            f"⏳ **Suggested Time:** `{len(exam_questions) * 2} Mins`\n\n"
            f"👇 *Click below to start or share it to your group!* 👇")
            
    buttons = [
        [Button.url("💻 OPEN EXAM SCREEN", web_app_url)],
        [Button.url("↗️ SHARE TO GROUP", share_url)]
    ]
    
    if target_channel:
        await client.send_message(target_channel, text, buttons=[[Button.url("💻 OPEN EXAM SCREEN", web_app_url)]])
        await msg.edit("✅ Test successfully generated and sent to the channel!")
    else:
        await msg.edit(text, buttons=buttons)

# --- 3. RECEIVE SCORE (No Leaderboard) ---
@client.on(events.NewMessage(pattern=r'^/start res_([a-zA-Z0-9]+)_([a-zA-Z0-9\-_]+)'))
async def receive_submission(event):
    test_id = event.pattern_match.group(1)
    ans_encoded = event.pattern_match.group(2)
    
    if test_id not in active_tests:
        await event.respond("❌ This test is no longer active.")
        return
        
    questions = active_tests[test_id]["questions"]
    
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    map_ans = {0:'A', 1:'B', 2:'C', 3:'D', 4:'X'}
    ans_str = ""
    for char in ans_encoded:
        if char in chars:
            val = chars.index(char)
            v1 = val // 5
            v2 = val % 5
            ans_str += map_ans.get(v1, 'X') + map_ans.get(v2, 'X')
            
    ans_str = ans_str[:len(questions)] # Trim dummy char if odd
    
    if len(ans_str) != len(questions):
        await event.respond("❌ Invalid answers format.")
        return
        
    score = correct = wrong = unattempted = 0
    for i, q in enumerate(questions):
        user_ans = ans_str[i]
        correct_ans = q["c"].strip().upper() if q["c"] else ""
        
        if user_ans == "X":
            unattempted += 1
        elif user_ans == correct_ans:
            score += 4
            correct += 1
        else:
            score -= 1
            wrong += 1
            
    # Save to leaderboard
    sender = await event.get_sender()
    username = getattr(sender, 'username', 'Unknown') or getattr(sender, 'first_name', 'Student')
    
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO leaderboard (user_id, username, test_id, score) VALUES (%s, %s, %s, %s)", 
              (event.sender_id, username, test_id, score))
    conn.commit()
    conn.close()

    text = (f"📝 **SCORECARD FOR: {active_tests[test_id]['name']}**\n"
            f"👤 **Student:** `{username}`\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"✅ **Correct:** `{correct}`\n"
            f"❌ **Incorrect:** `{wrong}`\n"
            f"⏭ **Unattempted:** `{unattempted}`\n"
            f"🏆 **Total Score:** `{score}`\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"*(Score saved to Leaderboard!)*")
    
    await event.respond(text)
    
    # Update leaderboard in channel
    await update_channel_leaderboard()
    
async def update_channel_leaderboard():
    channel_id = -1002457209121
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username, score, timestamp FROM leaderboard ORDER BY score DESC, timestamp ASC LIMIT 10")
    leaders = c.fetchall()
    conn.close()
    
    if not leaders:
        return
        
    text = "🏆 **GLOBAL CHANNEL LEADERBOARD** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(leaders):
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        text += f"{medal} `{row[0]}` - **{row[1]} pts**\n"
        
    try:
        if "leaderboard_msg_id" in bot_state:
            await client.edit_message(channel_id, bot_state["leaderboard_msg_id"], text)
        else:
            msg = await client.send_message(channel_id, text)
            bot_state["leaderboard_msg_id"] = msg.id
            save_state(bot_state)
    except Exception as e:
        print(f"Failed to update channel leaderboard: {e}")

@client.on(events.NewMessage(pattern=r'^/send$'))
async def send_to_channel(event):
    await generate_test_logic(event, "Full", 75, target_channel=-1002457209121)

@client.on(events.NewMessage(pattern=r'^/leaderboard'))
async def show_leaderboard(event):
    await update_channel_leaderboard()
    await event.respond("✅ Leaderboard updated in the channel!")

# --- RENDER DUMMY WEB SERVER ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

print("🚀 NEW EXAM BOT ACTIVE (PostgreSQL DB + Render Dummy Server!)")
client.loop.run_until_complete(web_server())
client.run_until_disconnected()
