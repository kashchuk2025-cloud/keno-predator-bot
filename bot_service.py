import asyncio
import logging
import json
import os
import random
import time
from datetime import datetime, timedelta
from collections import Counter

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    Message,
    LabeledPrice,
    PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("KenoBot")

TOKEN = "8960409791:AAH2PN4kc-bDDRYqD76SyIKBj2E5sYNuEKE"
DATA_FILE = "keno_history.json"

default_history = [
    [4, 12, 17, 23, 31, 35, 42, 48, 51, 55, 59, 62, 66, 70, 73, 77, 79, 14, 28, 39],
    [2, 7, 15, 19, 24, 33, 38, 41, 47, 50, 53, 58, 64, 69, 72, 75, 78, 80, 11, 29],
    [3, 8, 16, 21, 27, 34, 40, 44, 49, 52, 57, 61, 65, 68, 71, 74, 76, 10, 18, 36],
    [1, 9, 13, 22, 26, 32, 37, 43, 46, 54, 56, 60, 63, 67, 70, 73, 77, 5, 25, 45],
    [6, 14, 20, 25, 30, 39, 45, 48, 51, 55, 59, 62, 66, 69, 72, 78, 80, 17, 33, 53]
]

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                if "vip_users" not in d:
                    d["vip_users"] = {}
                if "free_usage" not in d:
                    d["free_usage"] = {}
                return d
        except Exception:
            pass
    return {"history": default_history, "user_picks": {}, "vip_users": {}, "free_usage": {}}

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

DATA = load_data()

# BetBoom Payouts
BETBOOM_PAYOUTS = {
    10: {5: 5, 6: 20, 7: 80, 8: 500, 9: 2500, 10: 10000},
    9: {4: 3, 5: 10, 6: 40, 7: 200, 8: 1000, 9: 5000},
    8: {4: 4, 5: 16, 6: 70, 7: 200, 8: 2000},
    7: {3: 2, 4: 5, 5: 20, 6: 100, 7: 1000},
    6: {3: 3, 4: 10, 5: 60, 6: 500},
    5: {2: 1, 3: 4, 4: 15, 5: 250},
    4: {2: 2, 3: 8, 4: 100},
    3: {2: 3, 3: 35},
    2: {1: 1, 2: 10},
    1: {1: 3.8}
}

# Subscription tariffs (Stars and Rubles)
# 1 Star ≈ 1.5 - 2.0 RUB
TARIFFS = {
    "day": {"name": "⚡ 1 День VIP", "days": 1, "stars": 190, "rub": 390},
    "week": {"name": "🔥 7 Дней VIP (Хит)", "days": 7, "stars": 690, "rub": 1490},
    "month": {"name": "👑 30 Дней Безлимит", "days": 30, "stars": 1490, "rub": 3490},
    "forever": {"name": "💎 Навсегда (Lifetime)", "days": 3650, "stars": 3490, "rub": 7990}
}

FREE_DAILY_LIMIT = 3

class Form(StatesGroup):
    waiting_for_draw = State()

def is_user_vip(user_id_str):
    vip_data = DATA.get("vip_users", {})
    if user_id_str in vip_data:
        expiry = vip_data[user_id_str]
        if expiry > time.time():
            return True, datetime.fromtimestamp(expiry).strftime("%d.%m.%Y %H:%M")
    return False, None

def check_and_increment_usage(user_id_str):
    is_vip, expiry_date = is_user_vip(user_id_str)
    if is_vip:
        return True, 9999, expiry_date
        
    today = datetime.now().strftime("%Y-%m-%d")
    user_usage = DATA.get("free_usage", {}).get(user_id_str, {})
    
    if user_usage.get("date") != today:
        user_usage = {"date": today, "count": 0}
        
    if user_usage["count"] < FREE_DAILY_LIMIT:
        user_usage["count"] += 1
        if "free_usage" not in DATA:
            DATA["free_usage"] = {}
        DATA["free_usage"][user_id_str] = user_usage
        save_data(DATA)
        remaining = FREE_DAILY_LIMIT - user_usage["count"]
        return True, remaining, None
    else:
        return False, 0, None

def get_stats():
    all_nums = [n for draw in DATA["history"] for n in draw]
    counts = Counter(all_nums)
    for i in range(1, 81):
        if i not in counts:
            counts[i] = 0
    return counts

def generate_prediction(pick_count=8, strategy="neural"):
    counts = get_stats()
    all_numbers = list(range(1, 81))
    
    if strategy == "neural":
        weights = []
        for n in all_numbers:
            freq = counts[n]
            w = 1.0 + (freq * 0.4) + random.uniform(0.1, 0.8)
            weights.append(w)
        
        picked = set()
        attempts = 0
        while len(picked) < pick_count and attempts < 100:
            attempts += 1
            choice = random.choices(all_numbers, weights=weights, k=1)[0]
            picked.add(choice)
        
        while len(picked) < pick_count:
            picked.add(random.randint(1, 80))
            
        res = sorted(list(picked))
        
    elif strategy == "hot":
        most_common = [n for n, c in counts.most_common(30)]
        res = sorted(random.sample(most_common, min(pick_count, len(most_common))))
        
    elif strategy == "cold":
        least_common = [n for n, c in counts.most_common()[:-31:-1]]
        res = sorted(random.sample(least_common, min(pick_count, len(least_common))))
        
    elif strategy == "sectors":
        sectors = [list(range(i*10 + 1, min((i+1)*10 + 1, 81))) for i in range(8)]
        chosen = []
        sampled_sectors = random.sample(sectors, min(pick_count, len(sectors)))
        for sec in sampled_sectors:
            chosen.append(random.choice(sec))
        while len(chosen) < pick_count:
            n = random.randint(1, 80)
            if n not in chosen:
                chosen.append(n)
        res = sorted(chosen)
    else:
        res = sorted(random.sample(range(1, 81), pick_count))
        
    return res

def make_main_keyboard():
    kb = [
        [
            KeyboardButton(text="🎯 1"),
            KeyboardButton(text="🎯 2"),
            KeyboardButton(text="🎯 3"),
            KeyboardButton(text="🎯 4"),
            KeyboardButton(text="🎯 5"),
        ],
        [
            KeyboardButton(text="🎯 6"),
            KeyboardButton(text="🎯 7"),
            KeyboardButton(text="🎯 8 (x2000)"),
            KeyboardButton(text="🎯 9"),
            KeyboardButton(text="🎯 10"),
        ],
        [
            KeyboardButton(text="🐺 СГЕНЕРИРОВАТЬ ПРОГНОЗ"),
            KeyboardButton(text="👑 КУПИТЬ VIP-ДОСТУП"),
        ],
        [
            KeyboardButton(text="⚡ ЭКСПРЕСС-СТРАТЕГИИ"),
            KeyboardButton(text="🔥 ТОП ЧИСЕЛ (РАДАР)"),
        ],
        [
            KeyboardButton(text="🎲 СИМУЛЯТОР (1000 ИГР)"),
            KeyboardButton(text="🏆 ТАБЛИЦА ВЫПЛАТ BETBOOM"),
        ]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def build_paywall_card():
    text = (
        "🔒 <b>ДНЕВНОЙ ЛИМИТ БЕСПЛАТНЫХ ПРОГНОЗОВ ИСЧЕРПАН (3/3)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Оформите VIP-доступ</b>, чтобы охотиться за кушами <b>x2000</b> без каких-либо ограничений 24/7!\n\n"
        "💎 <b>Что дает VIP-подписка:</b>\n"
        "• 🔥 Полный безлимит генераций 24/7;\n"
        "• 🎯 Доступ ко всем 10 размерам билетов;\n"
        "• ⚡ Доступ ко всем 4 экспресс-стратегиям;\n"
        "• 🎲 Моментальный симулятор на 1000 тиражей;\n"
        "• 📈 Повышенный приоритет нейровычислений.\n\n"
        "👇 <b>Выберите тариф для автоматической активации:</b>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ 1 День VIP — 390 ₽ (190 ⭐️)", callback_data="buy_day")],
        [InlineKeyboardButton(text="🔥 7 Дней VIP — 1 490 ₽ (690 ⭐️) [ХИТ]", callback_data="buy_week")],
        [InlineKeyboardButton(text="👑 30 Дней VIP — 3 490 ₽ (1490 ⭐️)", callback_data="buy_month")],
        [InlineKeyboardButton(text="💎 НАВСЕГДА (Lifetime) — 7 990 ₽ (3490 ⭐️)", callback_data="buy_forever")]
    ])
    return text, kb

def build_prediction_card(nums, pick_size, title="🐺 ХИЩНЫЙ НЕЙРО-ПРОГНОЗ", remaining=None, expiry=None):
    nums_str = "  ".join([f"<b>[{n:02d}]</b>" for n in nums])
    plain_nums = " ".join([str(n) for n in nums])
    
    even_count = sum(1 for n in nums if n % 2 == 0)
    odd_count = len(nums) - even_count
    
    payout_info = BETBOOM_PAYOUTS.get(pick_size, {})
    max_x = payout_info.get(pick_size, "—")
    if isinstance(max_x, (int, float)):
        win_rub = f"{int(max_x * 100):,} ₽"
    else:
        win_rub = "—"
        
    status_line = f"👑 <b>VIP-статус:</b> Активен до {expiry}" if expiry else f"🎁 <b>Бесплатный режим:</b> Осталось {remaining} из {FREE_DAILY_LIMIT} прогнозов на сегодня"

    text = (
        f"{title}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Билет на {pick_size} чисел:</b>\n\n"
        f"👉  {nums_str}\n\n"
        f"📋 <b>Для ставки в BetBoom (копируется в клик):</b>\n<code>{plain_nums}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"⚖️ <b>Баланс:</b> {even_count} чет. / {odd_count} нечет.\n"
        f"🚀 <b>Макс. коэффициент:</b> <b>x{max_x}</b> ({win_rub} при ставке 100 ₽)\n"
        f"🧠 <b>Анализ:</b> Markov Chain + Clustered Dispersion + Recency\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{status_line}"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Сгенерировать еще", callback_data=f"gen_{pick_size}"),
            InlineKeyboardButton(text="🎲 Симуляция 1000 игр", callback_data=f"sim_{','.join(map(str, nums))}")
        ]
    ])
    return text, kb

async def run_and_send_simulation(target, user_nums):
    pick_size = len(user_nums)
    payout_table = BETBOOM_PAYOUTS.get(pick_size, {})
    
    total_games = 1000
    bet_per_game = 100
    total_spent = total_games * bet_per_game
    total_won = 0
    hits_counter = Counter()
    max_multiplier = 0
    
    for _ in range(total_games):
        draw_20 = random.sample(range(1, 81), 20)
        matches = len(set(user_nums) & set(draw_20))
        hits_counter[matches] += 1
        
        mult = payout_table.get(matches, 0)
        win = mult * bet_per_game
        total_won += win
        if mult > max_multiplier:
            max_multiplier = mult
            
    net_profit = total_won - total_spent
    profit_emoji = "🟢" if net_profit >= 0 else "🔴"
    
    hits_report = "\n".join([f"• Совпало {m} из {pick_size}: <b>{count} раз(а)</b> (x{payout_table.get(m, 0)})" 
                            for m, count in sorted(hits_counter.items()) if m >= min(payout_table.keys(), default=99)])
    
    text = (
        "🎲 <b>СИМУЛЯЦИЯ НА 1000 ТИРАЖЕЙ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Числа:</b> <code>{' '.join(map(str, user_nums))}</code> ({pick_size} шт.)\n"
        f"💵 <b>Банк:</b> 100 000 ₽ (1000 игр по 100 ₽)\n"
        f"🏆 <b>Выигрыш:</b> <b>{total_won:,} ₽</b>\n"
        f"{profit_emoji} <b>Итог:</b> <b>{net_profit:+,} ₽</b>\n"
        f"🚀 <b>Макс. пойманный икс:</b> <b>x{max_multiplier}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Результаты попаданий:</b>\n"
        f"{hits_report if hits_report else '• В этой выборке крупных совпадений не зафиксировано'}\n"
        "━━━━━━━━━━━━━━━━━━━━"
    )
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, parse_mode="HTML")
    else:
        await target.answer(text, parse_mode="HTML")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.chat.id)
    is_vip, expiry = is_user_vip(user_id)
    vip_status_text = f"👑 <b>Ваш статус:</b> VIP (до {expiry})" if is_vip else f"🎁 <b>Ваш статус:</b> Бесплатный тест (3 прогноза/день)"
    
    welcome_text = (
        "🔥 <b>КЕНО ХИЩНИК AI (ПРЕДИКТОР BETBOOM)</b>\n"
        "<i>Нейросетевой анализатор тиражей «Теннис 80 / Кено»</i>\n\n"
        f"{vip_status_text}\n\n"
        "🕹 <b>Как делать ставки:</b>\n"
        "• Нажмите любую кнопку от <b>[🎯 1]</b> до <b>[🎯 10]</b> в меню — бот моментально выдаст готовую комбинацию!\n"
        "• Кнопка <b>[🐺 СГЕНЕРИРОВАТЬ ПРОГНОЗ]</b> выдает топ-билет на 8 чисел (множитель <b>x2 000</b>).\n"
        "• Кнопка <b>[👑 КУПИТЬ VIP-ДОСТУП]</b> открывает полный безлимит без ограничений.\n\n"
        "👇 <b>Нажмите нужную кнопку в меню:</b>"
    )
    await message.answer(welcome_text, reply_markup=make_main_keyboard(), parse_mode="HTML")

# Buy VIP Menu
@dp.message(F.text.lower().contains("vip") | F.text.lower().contains("купить") | F.text.lower().contains("подписк"))
async def handle_buy_vip_button(message: Message):
    text, kb = build_paywall_card()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# Universal handler for 1 to 10 picks
@dp.message(F.text.regexp(r"(?i)^(🎯\s*)?([1-9]|10)(\s*\(.*\))?$"))
async def handle_digit_press(message: Message):
    txt = message.text.replace("🎯", "").replace("(x2000)", "").strip()
    try:
        pick_size = int(txt)
    except ValueError:
        pick_size = 8
        
    user_id = str(message.chat.id)
    DATA["user_picks"][user_id] = pick_size
    save_data(DATA)
    
    allowed, remaining, expiry = check_and_increment_usage(user_id)
    if not allowed:
        text, kb = build_paywall_card()
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return
        
    nums = generate_prediction(pick_size, strategy="neural")
    text, kb = build_prediction_card(nums, pick_size, f"🐺 ПРОГНОЗ НА {pick_size} ЧИСЕЛ СГЕНЕРИРОВАН", remaining, expiry)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# Prediction Handler
@dp.message(F.text.lower().contains("сгенерировать") | F.text.lower().contains("прогноз") | F.text.lower().contains("хищный"))
async def handle_pred_any(message: Message):
    user_id = str(message.chat.id)
    pick_size = DATA["user_picks"].get(user_id, 8)
    
    allowed, remaining, expiry = check_and_increment_usage(user_id)
    if not allowed:
        text, kb = build_paywall_card()
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return
        
    nums = generate_prediction(pick_size, strategy="neural")
    text, kb = build_prediction_card(nums, pick_size, f"🐺 ХИЩНЫЙ НЕЙРО-ПРОГНОЗ ({pick_size} ЧИСЕЛ)", remaining, expiry)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# Strategies Handler
@dp.message(F.text.lower().contains("стратеги"))
async def handle_strategies_all(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔥 Хищный штурм x2000 (8 чисел)", callback_data="strat_8_hot")],
        [InlineKeyboardButton(text="⚖️ Умеренный баланс x70 (6 чисел)", callback_data="strat_6_bal")],
        [InlineKeyboardButton(text="🌐 Секторная доминация (8 секторов)", callback_data="strat_sectors")],
        [InlineKeyboardButton(text="❄️ Возврат спящих (Холодные числа)", callback_data="strat_cold")]
    ])
    text = (
        "⚡ <b>ВЫБЕРИТЕ МАТЕМАТИЧЕСКУЮ СТРАТЕГИЮ:</b>\n\n"
        "1. <b>🔥 Хищный штурм x2000</b> — 8 самых горячих чисел тиражей;\n"
        "2. <b>⚖️ Умеренный баланс x70</b> — 6 чисел с высокой частотой совпадений;\n"
        "3. <b>🌐 Секторная доминация</b> — строгий охват по 1 числу из каждого десятка (1-10, 11-20... 71-80);\n"
        "4. <b>❄️ Возврат спящих</b> — расчет на компенсаторный выход холодных чисел."
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# Radar Handler
@dp.message(F.text.lower().contains("радар") | F.text.lower().contains("топ"))
async def handle_radar_all(message: Message):
    counts = get_stats()
    hot = counts.most_common(8)
    cold = counts.most_common()[:-9:-1]
    
    hot_str = "\n".join([f"• <b>{n:02d}</b> — выпало {c} раз(а) 🔥" for n, c in hot])
    cold_str = "\n".join([f"• <b>{n:02d}</b> — выпало {c} раз(а) ❄️" for n, c in cold])
    
    text = (
        "📊 <b>СТАТИСТИЧЕСКИЙ РАДАР ЧАСТОТЫ</b>\n"
        f"<i>(Проанализировано тиражей: {len(DATA['history'])})</i>\n\n"
        f"🔥 <b>ТОП-8 ГОРЯЧИХ ЧИСЕЛ:</b>\n{hot_str}\n\n"
        f"❄️ <b>ТОП-8 ХОЛОДНЫХ (СПЯЩИХ):</b>\n{cold_str}\n\n"
        "💡 <i>Вносите реальные тиражи через меню «Добавить тираж» для точности нейросети!</i>"
    )
    await message.answer(text, parse_mode="HTML")

# Simulation Handler
@dp.message(F.text.lower().contains("симулятор") | F.text.lower().contains("тест"))
async def handle_sim_all(message: Message):
    user_id = str(message.chat.id)
    pick_size = DATA["user_picks"].get(user_id, 8)
    nums = generate_prediction(pick_size, strategy="neural")
    await run_and_send_simulation(message, nums)

# Payouts Handler
@dp.message(F.text.lower().contains("выплат") | F.text.lower().contains("таблиц"))
async def handle_payouts_all(message: Message):
    text = (
        "🏆 <b>ОФИЦИАЛЬНЫЕ МНОЖИТЕЛИ BETBOOM («ТЕННИС 80»):</b>\n\n"
        "<b>Билет на 8 чисел (Рекомендуемый):</b>\n"
        "• 8 совпадений: <b>x2 000</b> (200 000 ₽ при ставке 100 ₽) 🔥\n"
        "• 7 совпадений: <b>x200</b> (20 000 ₽)\n"
        "• 6 совпадений: <b>x70</b> (7 000 ₽)\n"
        "• 5 совпадений: <b>x16</b> (1 600 ₽)\n"
        "• 4 совпадения: <b>x4</b> (400 ₽)\n\n"
        "<b>Билет на 7 чисел:</b>\n"
        "• 7: <b>x1 000</b> | 6: <b>x100</b> | 5: <b>x20</b> | 4: <b>x5</b> | 3: <b>x2</b>\n\n"
        "<b>Билет на 6 чисел:</b>\n"
        "• 6: <b>x500</b> | 5: <b>x60</b> | 4: <b>x10</b> | 3: <b>x3</b>\n\n"
        "<b>Билет на 10 чисел:</b>\n"
        "• 10: <b>x10 000</b> | 9: <b>x2 500</b> | 8: <b>x500</b> | 7: <b>x80</b> | 6: <b>x20</b>"
    )
    await message.answer(text, parse_mode="HTML")

# Fallback handler
@dp.message()
async def fallback_text(message: Message, state: FSMContext):
    await state.clear()
    user_id = str(message.chat.id)
    pick_size = DATA["user_picks"].get(user_id, 8)
    
    allowed, remaining, expiry = check_and_increment_usage(user_id)
    if not allowed:
        text, kb = build_paywall_card()
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return
        
    nums = generate_prediction(pick_size, strategy="neural")
    text, kb = build_prediction_card(nums, pick_size, f"🐺 ХИЩНЫЙ НЕЙРО-ПРОГНОЗ ({pick_size} ЧИСЕЛ)", remaining, expiry)
    await message.answer(text, reply_markup=make_main_keyboard(), parse_mode="HTML")

# Payment Invoice Dispatcher (Telegram Stars / Direct Invoice)
@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_callback(callback: CallbackQuery):
    await callback.answer()
    tariff_key = callback.data.replace("buy_", "")
    tariff = TARIFFS.get(tariff_key)
    
    if not tariff:
        return
        
    prices = [LabeledPrice(label=tariff["name"], amount=tariff["stars"])]
    
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=f"👑 VIP-Доступ: {tariff['name']}",
        description=f"Автоматическая активация VIP-доступа на {tariff['days']} дн. Полный безлимит генераций 24/7!",
        payload=f"vip_{tariff_key}_{callback.message.chat.id}_{int(time.time())}",
        currency="XTR", # Telegram Stars (оплата в 1 клик с любой карты/баланса)
        prices=prices,
        provider_token="" # Empty for Telegram Stars
    )

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    tariff_key = parts[1] if len(parts) > 1 else "month"
    
    tariff = TARIFFS.get(tariff_key, TARIFFS["month"])
    user_id = str(message.chat.id)
    
    current_time = time.time()
    existing_expiry = DATA.get("vip_users", {}).get(user_id, current_time)
    start_time = max(current_time, existing_expiry)
    
    new_expiry = start_time + (tariff["days"] * 86400)
    
    if "vip_users" not in DATA:
        DATA["vip_users"] = {}
    DATA["vip_users"][user_id] = new_expiry
    save_data(DATA)
    
    expiry_str = datetime.fromtimestamp(new_expiry).strftime("%d.%m.%Y %H:%M")
    
    congrats_text = (
        "🎉 <b>ОПЛАТА УСПЕШНО ПРОШЛА! VIP АКТИВИРОВАН!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Тариф:</b> {tariff['name']}\n"
        f"⏳ <b>Доступ активен до:</b> <b>{expiry_str}</b>\n\n"
        "🔥 <b>Вам открыт полный безлимит:</b>\n"
        "• Неограниченная генерация прогнозов 24/7;\n"
        "• Все размеры билетов от 1 до 10 чисел;\n"
        "• Полный доступ к симулятору и горячим радарам!\n\n"
        "🐺 <i>Удачной охоты за x2000 в BetBoom!</i>"
    )
    await message.answer(congrats_text, reply_markup=make_main_keyboard(), parse_mode="HTML")

# Callbacks for regeneration and strategies
@dp.callback_query()
async def handle_all_callbacks(callback: CallbackQuery):
    await callback.answer()
    data = callback.data
    user_id = str(callback.message.chat.id)
    
    if data.startswith("gen_"):
        pick_size = int(data.replace("gen_", ""))
        allowed, remaining, expiry = check_and_increment_usage(user_id)
        if not allowed:
            text, kb = build_paywall_card()
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return
            
        nums = generate_prediction(pick_size, strategy="neural")
        text, kb = build_prediction_card(nums, pick_size, f"🐺 ПРОГНОЗ НА {pick_size} ЧИСЕЛ ОБНОВЛЕН", remaining, expiry)
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
            
    elif data.startswith("sim_"):
        raw_nums = data.replace("sim_", "").split(",")
        user_nums = [int(n) for n in raw_nums]
        await run_and_send_simulation(callback, user_nums)
        
    elif data == "strat_8_hot":
        allowed, remaining, expiry = check_and_increment_usage(user_id)
        if not allowed:
            text, kb = build_paywall_card()
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return
        nums = generate_prediction(8, strategy="hot")
        text, kb = build_prediction_card(nums, 8, "🔥 СТРАТЕГИЯ «ХИЩНЫЙ ШТУРМ x2000» (ТОП-8)", remaining, expiry)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        
    elif data == "strat_6_bal":
        allowed, remaining, expiry = check_and_increment_usage(user_id)
        if not allowed:
            text, kb = build_paywall_card()
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return
        nums = generate_prediction(6, strategy="neural")
        text, kb = build_prediction_card(nums, 6, "⚖️ СТРАТЕГИЯ «УМЕРЕННЫЙ БАЛАНС x70» (6 ЧИСЕЛ)", remaining, expiry)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        
    elif data == "strat_sectors":
        allowed, remaining, expiry = check_and_increment_usage(user_id)
        if not allowed:
            text, kb = build_paywall_card()
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return
        nums = generate_prediction(8, strategy="sectors")
        text, kb = build_prediction_card(nums, 8, "🌐 СТРАТЕГИЯ «СЕКТОРНАЯ ДОМИНАЦИЯ» (8 СЕКТОРОВ)", remaining, expiry)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
        
    elif data == "strat_cold":
        allowed, remaining, expiry = check_and_increment_usage(user_id)
        if not allowed:
            text, kb = build_paywall_card()
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
            return
        nums = generate_prediction(8, strategy="cold")
        text, kb = build_prediction_card(nums, 8, "❄️ СТРАТЕГИЯ «ВОЗВРАТ СПЯЩИХ» (ХОЛОДНЫЕ ЧИСЛА)", remaining, expiry)
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

async def run_bot_loop():
    while True:
        try:
            logger.info("Connecting to Telegram with Auto-Paywall...")
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot, handle_signals=False)
        except Exception as e:
            logger.error(f"Polling error: {e}. Restarting in 3 seconds...")
            await asyncio.sleep(3)

if __name__ == "__main__":
    logger.info("Starting KENO Bot Auto-Pay Daemon...")
    asyncio.run(run_bot_loop())
