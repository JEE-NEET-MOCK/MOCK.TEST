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

SUPABASE_URL = "https://jebcvrozypxsnfmfbgie.supabase.co"
SUPABASE_KEY = "sb_publishable_EpFqNE0R_81YeH3mgNzQ6A_0_qILYz4"
HEADERS = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}

async def fetch_random_questions(subject, limit):
    async with aiohttp.ClientSession() as session:
        url = f"{SUPABASE_URL}/rest/v1/questions?subject=eq.{subject}&select=id"
        async with session.get(url, headers=HEADERS) as r:
            data = await r.json()
            if not data: return []
            
        all_ids = [x['id'] for x in data]
        if limit > len(all_ids): limit = len(all_ids)
        selected_ids = random.sample(all_ids, limit)
        id_str = ",".join(map(str, selected_ids))
        
        url2 = f"{SUPABASE_URL}/rest/v1/questions?id=in.({id_str})&select=subject,question_text,correct_option"
        async with session.get(url2, headers=HEADERS) as r2:
            qs = await r2.json()
            random.shuffle(qs)
            return qs

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
    
    try:
        questions_db = []
        if subject == "Full":
            for s in ["physics", "chemistry", "mathematics"]:
                questions_db.extend(await fetch_random_questions(s, 25))
        else:
            db_subj = subject.lower()
            questions_db.extend(await fetch_random_questions(db_subj, num_q))
            
    except Exception as e:
        await msg.edit(f"❌ Database Error: {e}")
        return
    
    if not questions_db:
        await msg.edit("❌ Not enough questions in the database for this subject yet!")
        return
        
    exam_questions = []
    for row in questions_db:
        exam_questions.append({
            "s": row.get("subject", ""),
            "type": "MCQ",
            "l": row.get("question_text", ""),
            "c": row.get("correct_option", "")
        })
        
    test_name = f"{subject} Practice Test"
    try:
        telegraph_path = await create_telegraph_page(test_name, exam_questions)
        if not telegraph_path:
            await msg.edit("❌ Failed to generate Secure Link (Telegraph API returned None). Try again.")
            return
    except Exception as e:
        await msg.edit(f"❌ Telegraph API Error: {e}")
        return
        
    db_id = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    active_tests[db_id] = { "name": test_name, "questions": exam_questions }
    save_state(bot_state)
    
    bot_info = await client.get_me()
    suggested_time = 180 if len(exam_questions) == 75 else len(exam_questions) * 2
    web_app_url = f"{YOUR_GITHUB_WEBSITE}/?testid={db_id}&tpath={telegraph_path}&bot={bot_info.username}&time={suggested_time}"
    share_url = f"https://t.me/share/url?url={web_app_url}&text=Take%20this%20{test_name.replace(' ', '%20')}%20Challenge!"
    
    text = (f"🎯 **YOUR CUSTOM TEST IS READY!** 🎯\n\n"
            f"📌 **Topic:** `{test_name}`\n"
            f"🔢 **Questions:** `{len(exam_questions)}`\n"
            f"⏳ **Suggested Time:** `{suggested_time} Mins`\n\n"
            f"👇 *Click below to start or share it to your group!* 👇")
            
    buttons = [
        [Button.url("💻 OPEN EXAM SCREEN", web_app_url)],
        [Button.url("↗️ SHARE TO GROUP", share_url)]
    ]
    
    if target_channel:
        await client.send_message(target_channel, text, buttons=[[Button.url("💻 OPEN EXAM SCREEN", web_app_url)]])
        lb_msg = await client.send_message(target_channel, f"🏆 **LEADERBOARD FOR: {test_name}** 🏆\n\nNo scores yet. Be the first!")
        active_tests[db_id]["lb_msg_id"] = lb_msg.id
        save_state(bot_state)
        await msg.edit("✅ Test successfully generated and sent to the channel!")
    else:
        await msg.edit(text, buttons=buttons)

# --- 3. RECEIVE SCORE ---
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
            
    ans_str = ans_str[:len(questions)]
    
    if len(ans_str) != len(questions):
        await event.respond("❌ Invalid answers format.")
        return
        
    score_data = {}
    score = correct = wrong = unattempted = 0
    
    answer_key_html = []
    
    for i, q in enumerate(questions):
        subj = q["s"].lower()
        if subj not in score_data:
            score_data[subj] = {"correct": 0, "wrong": 0, "score": 0}
            
        user_ans = ans_str[i]
        correct_ans = q["c"].strip().upper() if q["c"] else ""
        
        # Build answer key HTML
        color = "#22c55e" if user_ans == correct_ans else ("#ef4444" if user_ans != "X" else "#f59e0b")
        status_text = "✅ Correct" if user_ans == correct_ans else (f"❌ Wrong (Your Answer: {user_ans})" if user_ans != "X" else "⏭ Unattempted")
        answer_key_html.append({"tag": "h4", "children": [f"Q{i+1}: {status_text} | Correct Answer: {correct_ans}"]})
        
        if user_ans == "X":
            unattempted += 1
        elif user_ans == correct_ans:
            score += 4
            correct += 1
            score_data[subj]["correct"] += 1
            score_data[subj]["score"] += 4
        else:
            score -= 1
            wrong += 1
            score_data[subj]["wrong"] += 1
            score_data[subj]["score"] -= 1
            
    sender = await event.get_sender()
    username = getattr(sender, 'username', 'Unknown') or getattr(sender, 'first_name', 'Student')
    
    # Save to leaderboard REST (Delete old entry if exists, then insert new to prevent duplicates)
    try:
        async with aiohttp.ClientSession() as session:
            del_url = f"{SUPABASE_URL}/rest/v1/leaderboard?user_id=eq.{event.sender_id}&test_id=eq.{test_id}"
            await session.delete(del_url, headers=HEADERS)
            
            url = f"{SUPABASE_URL}/rest/v1/leaderboard"
            payload = {"user_id": event.sender_id, "username": username, "test_id": test_id, "score": score}
            await session.post(url, headers=HEADERS, json=payload)
    except Exception as e:
        print(f"Failed to update leaderboard score: {e}")

    # Generate telegraph for Answer Key
    ans_key_url = None
    try:
        async with aiohttp.ClientSession() as session:
            acc_payload = {'short_name': 'JEEBot', 'author_name': 'JEE Exam Bot'}
            async with session.get('https://api.telegra.ph/createAccount', params=acc_payload, timeout=60) as r:
                token = (await r.json())['result']['access_token']
                
            payload = {'access_token': token, 'title': f"Answer Key: {active_tests[test_id]['name']}", 'content': answer_key_html}
            async with session.post('https://api.telegra.ph/createPage', json=payload, timeout=60) as r2:
                ans_key_url = (await r2.json())['result']['url']
    except Exception as e:
        print(f"Failed to generate answer key: {e}")

    subject_text = ""
    for s_name, s_data in score_data.items():
        if s_data["correct"] > 0 or s_data["wrong"] > 0 or score > 0:
            subject_text += f"🔹 **{s_name.capitalize()}:** {s_data['score']} pts (✅ {s_data['correct']} | ❌ {s_data['wrong']})\n"
    if not subject_text:
        subject_text = "🔹 All subjects unattempted.\n"

    text = (f"📝 **SCORECARD FOR: {active_tests[test_id]['name']}**\n"
            f"👤 **Student:** `{username}`\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"✅ **Total Correct:** `{correct}`\n"
            f"❌ **Total Incorrect:** `{wrong}`\n"
            f"⏭ **Unattempted:** `{unattempted}`\n\n"
            f"📊 **Subject-wise Marks:**\n{subject_text}"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"🏆 **GRAND TOTAL SCORE:** `{score}`\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"*(Score updated on Leaderboard!)*")
    
    buttons = [[Button.url("📖 REVIEW MISTAKES (ANSWER KEY)", ans_key_url)]] if ans_key_url else None
    
    await event.respond(text, buttons=buttons)
    await update_channel_leaderboard(test_id)
    
async def update_channel_leaderboard(test_id):
    if test_id not in active_tests:
        return
        
    lb_msg_id = active_tests[test_id].get("lb_msg_id")
    if not lb_msg_id:
        return
        
    channel_id = -1002457209121
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{SUPABASE_URL}/rest/v1/leaderboard?test_id=eq.{test_id}&order=score.desc,timestamp.asc&limit=15&select=username,score"
            async with session.get(url, headers=HEADERS) as r:
                leaders = await r.json()
    except:
        return
    
    if not leaders:
        return
        
    test_name = active_tests[test_id]["name"]
    text = f"🏆 **LEADERBOARD FOR: {test_name}** 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(leaders):
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        text += f"{medal} `{row.get('username')}` - **{row.get('score')} pts**\n"
        
    try:
        await client.edit_message(channel_id, lb_msg_id, text)
    except Exception as e:
        print(f"Failed to update channel leaderboard: {e}")

@client.on(events.NewMessage(pattern=r'^/send$'))
async def send_to_channel(event):
    await generate_test_logic(event, "Full", 75, target_channel=-1002457209121)

@client.on(events.NewMessage(pattern=r'^/leaderboard'))
async def show_leaderboard(event):
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{SUPABASE_URL}/rest/v1/leaderboard?order=score.desc,timestamp.asc&limit=10&select=username,score"
            async with session.get(url, headers=HEADERS) as r:
                leaders = await r.json()
    except:
        await event.respond("❌ Failed to fetch leaderboard.")
        return
    
    if not leaders:
        await event.respond("🏆 **GLOBAL LEADERBOARD** 🏆\n\nNo scores recorded yet!")
        return
        
    text = "🌍 **ALL-TIME GLOBAL LEADERBOARD** 🌍\n*(Highest scores ever recorded across all tests)*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, row in enumerate(leaders):
        medal = medals[i] if i < 3 else f"**{i+1}.**"
        text += f"{medal} `{row.get('username')}` - **{row.get('score')} pts**\n"
        
    await event.respond(text)

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
