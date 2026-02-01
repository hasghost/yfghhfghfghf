# -*- coding: utf-8 -*-
import asyncio
import sys
import logging
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import CommandStart, Command
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import aiosqlite

from config import BOT_TOKEN, ADMIN_CHANNEL_ID, ADMIN_ID, MIN_REFERRALS, MIN_STARS_WITHDRAW
from database import *
from keyboards import *

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FSM для ожидания dice слот-машины
class NFTStates(StatesGroup):
    waiting_for_dice = State()

# FSM для создания розыгрыша админом
class AdminStates(StatesGroup):
    waiting_for_bet_amount = State()
    waiting_for_nft_link = State()

# Множество для отслеживания обрабатываемых dice (анти-спам)
processing_dice = set()

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

processing_requests = set()

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandStart):
    user_id = message.from_user.id
    username = message.from_user.username or None
    full_name = message.from_user.full_name or "Без имени"
    
    referrer_id = None
    if command.args and command.args.isdigit():
        referrer_id = int(command.args)
        if referrer_id == user_id:
            referrer_id = None
    
    is_new = await add_user(user_id, username, full_name, referrer_id)
    
    if not is_new:
        await message.answer(
            "👋 Вы уже зарегистрированы в системе!",
            reply_markup=main_menu_kb()
        )
        return
    
    if referrer_id:
        referrer_data_before = await get_user(referrer_id)
        if referrer_data_before:
            await increment_referrals(referrer_id)
            await add_stars(referrer_id, 1)
            referrer_data_after = await get_user(referrer_id)
            
            try:
                await bot.send_message(
                    referrer_id,
                    f"⭐ <b>Заработана 1 Stars!</b>\n\n"
                    f"<blockquote>Пользователь @{username or 'скрыт'} присоединился по вашей ссылке!</blockquote>\n\n"
                    f"💎 Ваш баланс: <b>{referrer_data_after[5]} ⭐ Stars</b>",
                    reply_markup=main_menu_kb()
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления рефереру {referrer_id}: {e}")
    
    welcome_text = (
        f"<b>🌟 Добро пожаловать в StarsZone!</b>\n\n"
        f"Привет, <b>{full_name}</b>! Рады видеть тебя здесь.\n\n"
        f"<blockquote>💰 Принцип максимально прост:\n"
        f"• Получите свою реферальную ссылку\n"
        f"• Поделитесь ею с другом\n"
        f"• Мгновенно получите 1 ⭐ за каждого друга!</blockquote>\n\n"
        f"<b>Начинайте зарабатывать прямо сейчас!</b>"
    )
    
    await message.answer(welcome_text, reply_markup=main_menu_kb())

@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_data = await get_user(callback.from_user.id)
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    profile_text = (
        f"👤 <b>Мой профиль</b>\n\n"
        f"<blockquote>"
        f"🆔 ID: <code>{user_data[0]}</code>\n"
        f"👤 Username: @{user_data[1] or 'скрыт'}\n"
        f"📛 Имя: <b>{user_data[2] or 'Без имени'}</b>\n"
        f"📅 Дата: {user_data[6][:10] if user_data[6] else 'Неизвестно'}"
        f"</blockquote>\n\n"
        f"<blockquote>"
        f"📊 Моя статистика:\n"
        f"├ Приглашено: <b>{user_data[4]} человек</b>\n"
        f"└ Заработано: <b>{user_data[5]} ⭐ Stars</b>"
        f"</blockquote>\n\n"
        f"<i>Каждый новый друг — новая звезда!</i>"
    )
    
    await callback.message.edit_text(profile_text, reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "top")
async def show_top(callback: CallbackQuery):
    top_users = await get_top_referrers(10)
    
    if not top_users:
        await callback.answer("🏆 Топ пока пуст!", show_alert=True)
        return
    
    top_text = (
        f"🏆 <b>ТОП-10 РЕФЕРЕРОВ</b>\n\n"
        f"<blockquote>"
    )
    
    for idx, (user_id, username, refs, stars) in enumerate(top_users, 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(idx, "💠")
        name = f"@{username}" if username else f"ID:{user_id}"
        top_text += f"{medal} <b>{name}</b> │ {refs} чел. │ {stars}⭐\n"
    
    top_text += (
        f"</blockquote>\n\n"
        f"<blockquote>🎯 Ваша цель: попасть в топ и заработать максимум звезд!</blockquote>"
    )
    
    await callback.message.edit_text(top_text, reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(F.data == "how_to_earn")
async def show_how_to_earn(callback: CallbackQuery):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={callback.from_user.id}"
    
    earn_text = (
        f"💰 <b>КАК ЗАРАБОТАТЬ ЗВЕЗДЫ</b>\n\n"
        f"<blockquote>"
        f"<b>ШАГ 1:</b> Получите свою ссылку\n"
        f"└ Нажмите кнопку 'Поделится'\n\n"
        f"<b>ШАГ 2:</b> Поделитесь с другом\n"
        f"└ Отправьте ссылку в ЛС или чат\n\n"
        f"<b>ШАГ 3:</b> Получите звезду мгновенно!\n"
        f"└ Как только друг присоединится — вы получаете 1 ⭐"
        f"</blockquote>\n\n"
        f"<blockquote>"
        f"💡 <b>Где размещать ссылку?</b>\n"
        f"• В Telegram чатах (тематических)\n"
        f"• В соцсетях (ВК, Instagram, TikTok)\n"
        f"• На форумах и в комментариях\n"
        f"• Расскажите друзьям лично!"
        f"</blockquote>\n\n"
        f"<b>⚡ Ваша ссылка готова — начинайте зарабатывать!</b>"
    )
    
    await callback.message.edit_text(
        earn_text, 
        reply_markup=share_link_kb(ref_link)
    )
    await callback.answer()

@router.callback_query(F.data == "withdraw")
async def show_withdrawal_options(callback: CallbackQuery):
    user_data = await get_user(callback.from_user.id)
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    if user_data[4] < MIN_REFERRALS:
        await callback.answer(
            f"❌ Недостаточно рефералов!\n"
            f"Минимум: {MIN_REFERRALS} | У вас: {user_data[4]}", 
            show_alert=True
        )
        return
    
    if user_data[5] < MIN_STARS_WITHDRAW:
        await callback.answer(
            f"❌ Недостаточно Stars!\n"
            f"Минимум: {MIN_STARS_WITHDRAW} | У вас: {user_data[5]}", 
            show_alert=True
        )
        return
    
    withdraw_text = (
        f"💸 <b>Вывод Stars</b>\n\n"
        f"<blockquote>"
        f"📊 Ваш баланс: <b>{user_data[5]} ⭐</b>\n"
        f"👥 Рефералов: <b>{user_data[4]} человек</b>\n"
        f"</blockquote>\n\n"
        f"<blockquote>Выберите сумму для вывода:</blockquote>"
    )
    
    await callback.message.edit_text(
        withdraw_text, 
        reply_markup=withdrawal_amounts_kb()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("withdraw_"))
async def process_withdrawal(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if user_id in processing_requests:
        await callback.answer("⏳ Запрос уже обрабатывается!", show_alert=True)
        return
    
    try:
        processing_requests.add(user_id)
        amount = int(callback.data.split("_")[1])
        
        user_data = await get_user(user_id)
        if not user_data:
            await callback.answer("❌ Пользователь не найден!", show_alert=True)
            return
        
        if user_data[4] < MIN_REFERRALS:
            await callback.answer(f"❌ Минимум {MIN_REFERRALS} рефералов!", show_alert=True)
            return
        
        if user_data[5] < amount:
            await callback.answer(
                f"❌ Недостаточно Stars!\nНужно: {amount} | У вас: {user_data[5]}", 
                show_alert=True
            )
            return
        
        pending_count = await get_pending_withdrawals_count(user_id)
        if pending_count >= 3:
            await callback.answer("❌ У вас уже 3 заявки в обработке. Дождитесь решения.", show_alert=True)
            return
        
        request_id = await create_withdrawal_request(user_id, amount)
        
        if not request_id:
            await callback.answer("❌ Ошибка создания заявки!", show_alert=True)
            return
        
        try:
            bot_info = await bot.get_me()
            user_link = f"tg://user?id={user_id}"
            
            admin_message = (
                f"🆔 <b>Заявка на вывод #{request_id}</b>\n\n"
                f"<blockquote>"
                f"👤 Пользователь: <a href='{user_link}'>{user_data[2] or 'Без имени'}</a>\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"💰 Сумма: <b>{amount} ⭐ Stars</b>\n"
                f"📊 Баланс: {user_data[5]} | Рефералов: {user_data[4]}"
                f"</blockquote>\n\n"
            )
            
            await bot.send_message(
                ADMIN_CHANNEL_ID, 
                admin_message, 
                reply_markup=admin_withdrawal_kb(request_id)
            )
        except Exception as e:
            logger.error(f"Ошибка отправки в админ-канал: {e}")
            await add_stars(user_id, amount)
            await callback.answer("❌ Ошибка отправки заявки админам!", show_alert=True)
            return
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        user_message = (
            f"✅ <b>Заявка #{request_id} создана!</b>\n\n"
            f"<blockquote>"
            f"💰 Сумма: <b>{amount} ⭐ Stars</b>\n"
            f"⏳ Статус: В обработке\n"
            f"📅 Дата: {current_time}"
            f"</blockquote>\n\n"
            f"<blockquote>⏰ Обычно выплата занимает 1-24 часа</blockquote>\n\n"
            f"💎 Когда заявку одобрят — вы получите уведомление!"
        )
        
        await callback.message.edit_text(user_message, reply_markup=back_to_menu_kb())
        await callback.answer()
        
    finally:
        processing_requests.discard(user_id)

@router.callback_query(F.data == "my_withdrawals")
async def show_my_withdrawals(callback: CallbackQuery):
    user_id = callback.from_user.id
    withdrawals = await get_user_withdrawals(user_id)
    
    if not withdrawals:
        await callback.answer("📭 У вас нет заявок", show_alert=True)
        return
    
    withdrawal_text = f"📋 <b>Мои заявки на вывод</b>\n\n"
    
    for req in withdrawals:
        status_emoji = {"pending": "⏳", "paid": "✅", "rejected": "❌"}
        status_text = {"pending": "В обработке", "paid": "Выплачено", "rejected": "Отклонено"}
        
        withdrawal_text += (
            f"<blockquote>"
            f"🆔 #{req[0]} | 💰 {req[1]} ⭐\n"
            f"📅 {req[3][:10] if req[3] else 'Неизвестно'} | {status_emoji.get(req[2], '❓')} <b>{status_text.get(req[2], 'Неизвестно')}</b>"
            f"</blockquote>\n"
        )
    
    await callback.message.edit_text(withdrawal_text, reply_markup=my_withdrawals_kb())
    await callback.answer()

# === NFT ОБРАБОТЧИКИ (ОПЛАТА ВКЛЮЧЕНА) ===
@router.callback_query(F.data == "nft_giveaway")
async def show_nft_giveaway(callback: CallbackQuery):
    """Показать активный розыгрыш NFT"""
    giveaway = await get_active_giveaway()
    
    if not giveaway:
        await callback.message.edit_text(
            "🎰 <b>Нет активных розыгрышей NFT</b>\n\n"
            "<blockquote>Следите за обновлениями! Админ скоро создаст новый розыгрыш с крутыми NFT призами.</blockquote>",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    giveaway_id, bet_amount, nft_link, is_active, created_by, winner_id, created_at, ended_at = giveaway
    stats = await get_giveaway_stats(giveaway_id)
    
    text = (
        f"🎰 <b>АКТИВНЫЙ РОЗЫГРЫШ NFT!</b>\n\n"
        f"<blockquote>"
        f"💎 <b>Приз:</b> <a href='{nft_link}'>NFT Подарок</a>\n"
        f"💰 <b>Ставка:</b> {bet_amount} ⭐ Stars\n"
        f"👥 <b>Уникальных игроков:</b> {stats['unique_users']}\n"
        f"🎲 <b>Всего бросков:</b> {stats['total_attempts']}\n"
        f"🎯 <b>Условия:</b> Выпадет <b>777 (64)</b> = выигрыш!"
        f"</blockquote>\n\n"
        f"<blockquote>🍀 <b>Испытайте свою удачу!</b>\n"
        f"Нажмите кнопку ниже, оплатите {bet_amount} Stars и сыграйте.\n"
        f"Если выпадет <b>777 (64)</b> (максимум) — NFT ваш!\n\n"
        f"<i>Попыток неограничено!</i></blockquote>"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=nft_giveaway_kb(giveaway_id, bet_amount),
        disable_web_page_preview=True
    )
    await callback.answer()

@router.callback_query(F.data.startswith("join_nft_"))
async def process_nft_payment(callback: CallbackQuery, state: FSMContext):
    """
    ОПЛАТА ВКЛЮЧЕНА: Отправка инвойса на оплату Stars
    """
    user_id = callback.from_user.id
    giveaway_id = int(callback.data.split("_")[2])
    
    giveaway = await get_active_giveaway()
    if not giveaway or giveaway[0] != giveaway_id:
        await callback.answer("❌ Этот розыгрыш уже завершен!", show_alert=True)
        return
    
    bet_amount = giveaway[1]
    
    # Создаем инвойс на оплату Stars
    try:
        await bot.send_invoice(
            chat_id=user_id,
            title="🎰 Участие в розыгрыше NFT",
            description=f"Оплата участия в розыгрыше NFT. Шанс выиграть уникальный NFT приз!\n\nСумма ставки: {bet_amount} Stars",
            payload=f"nft_{giveaway_id}_{user_id}",
            provider_token="",  # Пусто для Telegram Stars
            currency="XTR",     # XTR = Telegram Stars
            prices=[LabeledPrice(label=f"Ставка в розыгрыше", amount=bet_amount)]
        )
        await callback.answer("💸 Счет на оплату отправлен!")
    except Exception as e:
        logger.error(f"Ошибка создания инвойса: {e}")
        await callback.answer("❌ Ошибка создания счета!", show_alert=True)

@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery):
    """Обработка предварительной проверки оплаты"""
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, state: FSMContext):
    """Обработка успешной оплаты - переход к игре"""
    payload = message.successful_payment.invoice_payload
    
    if payload.startswith("nft_"):
        _, giveaway_id, user_id = payload.split("_")
        giveaway_id = int(giveaway_id)
        user_id = int(user_id)
        
        giveaway = await get_active_giveaway()
        if not giveaway or giveaway[0] != giveaway_id:
            await message.answer("❌ Этот розыгрыш уже завершен!")
            return
        
        # Добавляем попытку в БД
        attempt_id = await add_attempt(giveaway_id, user_id)
        if not attempt_id:
            await message.answer("❌ Ошибка создания попытки!")
            return
        
        attempts_count = await get_user_attempts_count(giveaway_id, user_id)
        
        # Сохраняем данные в FSM
        await state.set_state(NFTStates.waiting_for_dice)
        await state.update_data(
            giveaway_id=giveaway_id,
            attempt_id=attempt_id,
            bet_amount=giveaway[1],
            nft_link=giveaway[2]
        )
        
        await message.answer(
            f"✅ <b>Оплата прошла успешно!</b>\n\n"
            f"<blockquote>"
            f"🎰 Попытка #{attempts_count}\n"
            f"💎 Приз: <a href='{giveaway[2]}'>NFT Подарок</a>\n"
            f"🎯 Цель: Выпадение 777 (64)"
            f"</blockquote>\n\n"
            f"<b>👉 Отправьте анимированный эмодзи</b> 🎰 <b>(Слот-машина)</b>\n\n",
            disable_web_page_preview=True,
            reply_markup=back_to_menu_kb()
        )

@router.message(NFTStates.waiting_for_dice, F.dice.emoji == "🎰")
async def process_slot_dice(message: Message, state: FSMContext):
    """Обработка броска слот-машины (🎰) - защита от спама"""
    user_id = message.from_user.id
    
    if user_id in processing_dice:
        return
    
    try:
        processing_dice.add(user_id)
        
        data = await state.get_data()
        giveaway_id = data.get("giveaway_id")
        attempt_id = data.get("attempt_id")
        nft_link = data.get("nft_link")
        
        if not giveaway_id or not attempt_id:
            await message.answer("❌ Ошибка: данные игры не найдены.")
            return
        
        giveaway = await get_active_giveaway()
        if not giveaway or giveaway[0] != giveaway_id:
            await message.answer("❌ Этот розыгрыш уже завершен!", reply_markup=main_menu_kb())
            return
        
        dice_value = message.dice.value
        is_win = (dice_value == 64)
        
        result_status = "win" if is_win else "lose"
        await update_attempt_result(attempt_id, result_status, str(dice_value))
        
        await state.clear()
        await asyncio.sleep(2)
        
        if is_win:
            await close_giveaway(giveaway_id, user_id)
            
            user = await get_user(user_id)
            user_name = user[2] if user else f"ID:{user_id}"
            user_link = f"tg://user?id={user_id}"
            
            admin_msg = (
                f"🏆 <b>ПОБЕДИТЕЛЬ В РОЗЫГРЫШЕ NFT!</b>\n\n"
                f"<blockquote>"
                f"👤 Победитель: <a href='{user_link}'>{user_name}</a>\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"🔗 NFT: <a href='{nft_link}'>Ссылка на приз</a>\n"
                f"🆔 ID розыгрыша: #{giveaway_id}"
                f"</blockquote>\n\n"
                f"<b>Отправьте NFT победителю!</b>"
            )
            
            try:
                await bot.send_message(ADMIN_CHANNEL_ID, admin_msg)
            except Exception as e:
                logger.error(f"Ошибка уведомления админа: {e}")
            
            all_users = await get_all_users()
            announce_text = (
                f"🎉 <b>ПОБЕДИТЕЛЬ ОПРЕДЕЛЕН!</b>\n\n"
                f"<blockquote>"
                f"🏆 <b>{user_name}</b> выиграл NFT!\n"
                f"💎 Приз: <a href='{nft_link}'>NFT Подарок</a>"
                f"</blockquote>\n\n"
                f"🍀 <b>Испытайте свою удачу тоже!</b>\n"
                f"Нажмите '🎰 Получить NFT' в меню!"
            )
            
            await message.answer(
                f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                f"<blockquote>🎰 Выпало: <b>777 {dice_value}</b>\n"
                f"Вы выиграли NFT!</blockquote>\n\n"
                f"Администратор свяжется с вами для передачи приза.",
                reply_markup=main_menu_kb()
            )
            
            asyncio.create_task(broadcast_message(all_users, announce_text, exclude_user=user_id))
            
        else:
            await message.answer(
                f"😔 <b>Не повезло...</b>\n\n"
                f"<blockquote>🎰 Выпало: <b>{dice_value}</b> из 64\n\n"
                f"Нужно было <b>777 (64)</b> для победы!\n\n"
                f"Хотите попробовать снова? Нажмите '🎰 Получить NFT' в меню!</blockquote>",
                reply_markup=main_menu_kb()
            )
            
    finally:
        await asyncio.sleep(1)
        processing_dice.discard(user_id)

@router.message(NFTStates.waiting_for_dice, F.dice)
async def wrong_dice_type(message: Message):
    await message.answer(
        "❌ <b>Нужен именно эмодзи Слот-машины</b> 🎰!\n\n"
        f"Вы отправили: {message.dice.emoji}\n"
    )

@router.message(NFTStates.waiting_for_dice)
async def not_dice(message: Message):
    await message.answer(
        "❌ <b>Отправьте анимированный эмодзи</b> 🎰 <b>(Слот-машина)</b>!\n\n"
    )

# === АДМИН МЕНЮ ===
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен!")
        return
    
    admin_text = (
        f"👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        f"Добро пожаловать, <b>{message.from_user.full_name}</b>!\n\n"
        f"<blockquote>Выберите раздел:</blockquote>"
    )
    
    await message.answer(admin_text, reply_markup=admin_menu_kb())

@router.callback_query(F.data == "admin_stats")
async def admin_full_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    try:
        async with aiosqlite.connect("bot_database.db") as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            total_users = (await cursor.fetchone())[0]
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM users WHERE date(joined_date) = date('now')"
            )
            new_today = (await cursor.fetchone())[0]
            
            cursor = await db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM withdrawal_requests WHERE status = 'paid'"
            )
            total_paid = (await cursor.fetchone())[0]
            
            cursor = await db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM withdrawal_requests WHERE status = 'pending'"
            )
            pending_amount = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM withdrawal_requests")
            total_withdrawals = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM withdrawal_requests WHERE status = 'pending'")
            pending_count = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM withdrawal_requests WHERE status = 'paid'")
            paid_count = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM nft_giveaways WHERE is_active = 1")
            active_giveaways = (await cursor.fetchone())[0]
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM nft_giveaways WHERE winner_id IS NOT NULL"
            )
            completed_giveaways = (await cursor.fetchone())[0]
            
            cursor = await db.execute("SELECT COUNT(*) FROM nft_giveaways")
            total_giveaways = (await cursor.fetchone())[0]
            
            cursor = await db.execute(
                "SELECT COUNT(*) FROM nft_attempts WHERE giveaway_id IN "
                "(SELECT id FROM nft_giveaways WHERE is_active = 1)"
            )
            current_attempts = (await cursor.fetchone())[0]
            
            cursor = await db.execute(
                "SELECT username, referrals_count, stars_earned FROM users ORDER BY referrals_count DESC LIMIT 5"
            )
            top_refs = await cursor.fetchall()
    
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await callback.answer("❌ Ошибка загрузки статистики!", show_alert=True)
        return
    
    stats_text = (
        f"📊 <b>ПОДРОБНАЯ СТАТИСТИКА БОТА</b>\n\n"
        f"<b>👥 Пользователи:</b>\n"
        f"<blockquote>"
        f"├ Всего: <b>{total_users}</b>\n"
        f"├ Новых сегодня: <b>{new_today}</b>\n"
        f"└ Рефералов всего: <b>{sum([r[1] for r in top_refs])}</b>"
        f"</blockquote>\n\n"
        f"<b>💸 Выводы Stars:</b>\n"
        f"<blockquote>"
        f"├ Всего заявок: <b>{total_withdrawals}</b>\n"
        f"├ В обработке: <b>{pending_count}</b>\n"
        f"├ Выплачено: <b>{paid_count}</b>\n"
        f"├ Всего выплачено: <b>{total_paid}</b> ⭐\n"
        f"└ В ожидании: <b>{pending_amount}</b> ⭐"
        f"</blockquote>\n\n"
        f"<b>🎰 NFT Розыгрыши:</b>\n"
        f"<blockquote>"
        f"├ Активных: <b>{active_giveaways}</b>\n"
        f"├ Проведено: <b>{completed_giveaways}</b>\n"
        f"├ Всего создано: <b>{total_giveaways}</b>\n"
        f"└ Попыток в текущем: <b>{current_attempts}</b>"
        f"</blockquote>\n\n"
        f"<b>🏆 Топ-5 рефереров:</b>\n<blockquote>"
    )
    
    for idx, (username, refs, stars) in enumerate(top_refs, 1):
        name = f"@{username}" if username else f"ID:{idx}"
        stats_text += f"{idx}. {name} — {refs} ref / {stars} ⭐\n"
    
    stats_text += "</blockquote>"
    
    await callback.message.edit_text(stats_text, reply_markup=admin_back_kb())
    await callback.answer()

@router.callback_query(F.data == "admin_giveaway")
async def admin_giveaway_menu(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    giveaway = await get_active_giveaway()
    
    if giveaway:
        stats = await get_giveaway_stats(giveaway[0])
        text = (
            f"🎰 <b>УПРАВЛЕНИЕ РОЗЫГРЫШАМИ</b>\n\n"
            f"<b>🔥 Активен розыгрыш #{giveaway[0]}</b>\n\n"
            f"<blockquote>"
            f"💰 Ставка: {giveaway[1]} Stars\n"
            f"💎 NFT: <a href='{giveaway[2]}'>Ссылка на приз</a>\n"
            f"👥 Уникальных игроков: {stats['unique_users']}\n"
            f"🎲 Всего попыток: {stats['total_attempts']}\n"
            f"📅 Создан: {giveaway[6][:10] if giveaway[6] else 'Неизвестно'}"
            f"</blockquote>\n\n"
            f"Выберите действие:"
        )
        kb = admin_giveaway_manage_kb(has_active=True)
    else:
        text = (
            f"🎰 <b>УПРАВЛЕНИЕ РОЗЫГРЫШАМИ</b>\n\n"
            f"<blockquote>Сейчас нет активных розыгрышей.</blockquote>"
        )
        kb = admin_giveaway_manage_kb(has_active=False)
    
    await callback.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    await callback.answer()

@router.callback_query(F.data == "admin_create_giveaway")
async def admin_start_create_giveaway(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_bet_amount)
    
    await callback.message.edit_text(
        "🎰 <b>СОЗДАНИЕ НОВОГО РОЗЫГРЫША</b>\n\n"
        "<b>Шаг 1/2:</b> Введите сумму ставки (число Stars)\n\n"
        "<i>Пример: 50</i>",
        reply_markup=admin_cancel_kb()
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_bet_amount, F.text.regexp(r'^\d+$'))
async def admin_process_bet_amount(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    bet_amount = int(message.text)
    if bet_amount < 1:
        await message.answer("❌ Сумма должна быть больше 0!", reply_markup=admin_cancel_kb())
        return
    
    await state.update_data(bet_amount=bet_amount)
    await state.set_state(AdminStates.waiting_for_nft_link)
    
    await message.answer(
        "🎰 <b>СОЗДАНИЕ НОВОГО РОЗЫГРЫША</b>\n\n"
        f"<b>Шаг 1:</b> ✅ Ставка: {bet_amount} Stars\n"
        f"<b>Шаг 2/2:</b> Отправьте ссылку на NFT приз\n\n"
        f"<i>Пример: https://t.me/nft/mygift</i>",
        reply_markup=admin_cancel_kb()
    )

@router.message(AdminStates.waiting_for_bet_amount)
async def admin_wrong_bet_amount(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("❌ Введите число! Например: 50", reply_markup=admin_cancel_kb())

@router.message(AdminStates.waiting_for_nft_link, F.text)
async def admin_process_nft_link(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    data = await state.get_data()
    bet_amount = data.get("bet_amount")
    nft_link = message.text
    
    giveaway_id = await create_giveaway(bet_amount, nft_link, message.from_user.id)
    
    if giveaway_id:
        await message.answer(
            f"✅ <b>Розыгрыш #{giveaway_id} создан!</b>\n\n"
            f"<blockquote>"
            f"💰 Ставка: {bet_amount} Stars\n"
            f"💎 NFT: {nft_link}\n"
            f"🎰 Условие: Выпадение 777 (64)"
            f"</blockquote>\n\n"
            f"Начинаю рассылку уведомлений...",
            reply_markup=admin_menu_kb(),
            disable_web_page_preview=True
        )
        
        all_users = await get_all_users()
        announce_text = (
            f"🎰 <b>НОВЫЙ РОЗЫГРЫШ NFT!</b>\n\n"
            f"<blockquote>"
            f"💎 Новый приз разыгрывается!\n"
            f"💰 Ставка: {bet_amount} Stars\n"
            f"🎯 Условие: Выпадение 777 (64)\n"
            f"🔗 <a href='{nft_link}'>Посмотреть приз</a>"
            f"</blockquote>\n\n"
            f"<b>🍀 Испытайте удачу!</b> Нажмите '🎰 Получить NFT' в меню!"
        )
        
        asyncio.create_task(broadcast_message(all_users, announce_text))
        logger.info(f"Админ создал розыгрыш #{giveaway_id}")
    else:
        await message.answer("❌ Ошибка создания розыгрыша!", reply_markup=admin_menu_kb())
    
    await state.clear()

@router.callback_query(F.data == "admin_stop_giveaway")
async def admin_stop_current_giveaway(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    giveaway = await get_active_giveaway()
    if not giveaway:
        await callback.answer("❌ Нет активных розыгрышей!", show_alert=True)
        return
    
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute(
            "UPDATE nft_giveaways SET is_active = 0, ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (giveaway[0],)
        )
        await db.commit()
    
    await callback.message.edit_text(
        f"✅ <b>Розыгрыш #{giveaway[0]} завершен!</b>\n\n"
        f"<blockquote>Статистика сохранена в истории.</blockquote>",
        reply_markup=admin_giveaway_menu()
    )
    await callback.answer("Розыгрыш завершен!")

@router.callback_query(F.data == "admin_giveaway_history")
async def admin_giveaway_history(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    try:
        async with aiosqlite.connect("bot_database.db") as db:
            cursor = await db.execute(
                "SELECT * FROM nft_giveaways WHERE is_active = 0 ORDER BY ended_at DESC LIMIT 5"
            )
            history = await cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await callback.answer("❌ Ошибка загрузки!", show_alert=True)
        return
    
    if not history:
        text = "📜 <b>История розыгрышей</b>\n\n<blockquote>Пока нет завершенных розыгрышей.</blockquote>"
    else:
        text = "📜 <b>ПОСЛЕДНИЕ ЗАВЕРШЕННЫЕ РОЗЫГРЫШИ</b>\n\n"
        
        for row in history:
            giveaway_id, bet_amount, nft_link, is_active, created_by, winner_id, created_at, ended_at = row
            winner = await get_user(winner_id) if winner_id else None
            winner_name = winner[2] if winner else "Никто (завершен админом)"
            
            text += (
                f"<blockquote><b>#{giveaway_id}</b>\n"
                f"💰 Ставка: {bet_amount} Stars\n"
                f"🏆 Победитель: {winner_name}\n"
                f"📅 {ended_at[:10] if ended_at else 'Неизвестно'}</blockquote>\n\n"
            )
    
    await callback.message.edit_text(text, reply_markup=admin_back_kb())
    await callback.answer()

@router.callback_query(F.data == "admin_menu")
async def admin_back_to_menu(callback: CallbackQuery, state: FSMContext = None):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    if state:
        await state.clear()
    
    await callback.message.edit_text(
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n\n"
        "Выберите раздел:",
        reply_markup=admin_menu_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "cancel_action")
async def admin_cancel_action(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    await state.clear()
    await admin_back_to_menu(callback, state)

# === ОБРАБОТЧИКИ ВЫВОДА (из предыдущих версий) ===
@router.callback_query(F.data.startswith("admin_paid_"))
async def mark_as_paid(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[2])
    request_data = await get_withdrawal_request(request_id)
    
    if not request_data:
        await callback.answer("❌ Заявка не найдена!", show_alert=True)
        return
    
    if request_data[3] != 'pending':
        await callback.answer(f"❌ Заявка уже обработана! Статус: {request_data[3]}", show_alert=True)
        return
    
    if not await update_withdrawal_status(request_id, "paid"):
        await callback.answer("❌ Ошибка обновления статуса!", show_alert=True)
        return
    
    user_id = request_data[1]
    amount = request_data[2]
    
    try:
        await bot.send_message(
            user_id,
            f"🎉 <b>Заявка #{request_id} выплачена!</b>\n\n"
            f"<blockquote>"
            f"💰 Сумма: <b>{amount} ⭐ Stars</b>\n"
            f"✅ Статус: Выплачено\n"
            f"🎊 Средства отправлены на ваш кошелек"
            f"</blockquote>\n\n"
            f"💎 Спасибо за использование бота!",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователя {user_id}: {e}")
    
    await callback.message.edit_text(
        f"{callback.message.text}\n\n"
        f"<b>✅ Статус обновлен: Выплачено</b>\n"
        f"👤 Админ: @{callback.from_user.username or 'скрыт'}",
        reply_markup=None
    )
    await callback.answer("✅ Статус изменен!")

@router.callback_query(F.data.startswith("admin_reject_"))
async def mark_as_rejected(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен!", show_alert=True)
        return
    
    request_id = int(callback.data.split("_")[2])
    request_data = await get_withdrawal_request(request_id)
    
    if not request_data:
        await callback.answer("❌ Заявка не найдена!", show_alert=True)
        return
    
    if request_data[3] != 'pending':
        await callback.answer(f"❌ Заявка уже обработана! Статус: {request_data[3]}", show_alert=True)
        return
    
    if not await update_withdrawal_status(request_id, "rejected"):
        await callback.answer("❌ Ошибка обновления статуса!", show_alert=True)
        return
    
    user_id = request_data[1]
    amount = request_data[2]
    
    await add_stars(user_id, amount)
    
    try:
        await bot.send_message(
            user_id,
            f"❌ <b>Заявка #{request_id} отклонена</b>\n\n"
            f"<blockquote>"
            f"💰 Сумма: <b>{amount} ⭐ Stars</b>\n"
            f"📛 Статус: Отклонено\n"
            f"💎 Средства возвращены на ваш баланс\n"
            f"❓ Свяжитесь с администратором для уточнения"
            f"</blockquote>",
            reply_markup=main_menu_kb()
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления пользователя {user_id}: {e}")
    
    await callback.message.edit_text(
        f"{callback.message.text}\n\n"
        f"<b>❌ Статус обновлен: Отклонено</b>\n"
        f"👤 Админ: @{callback.from_user.username or 'скрыт'}",
        reply_markup=None
    )
    await callback.answer("✅ Статус изменен!")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext = None):
    if state:
        await state.clear()
    
    user_data = await get_user(callback.from_user.id)
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    menu_text = (
        f"<b>🏠 Главное меню</b>\n\n"
        f"Привет, <b>{user_data[2] or 'Пользователь'}</b>! 👋\n\n"
        f"<blockquote>"
        f"💎 Баланс: <b>{user_data[5]} ⭐ звезд</b>\n"
        f"👥 Рефералы: <b>{user_data[4]} человек</b>\n"
        f"🎯 Каждый друг = 1 звезда!\n"
        f"🎰 NFT розыгрыши активны!"
        f"</blockquote>\n\n"
        f"<b>Выберите действие:</b>"
    )
    
    try:
        await callback.message.edit_text(menu_text, reply_markup=main_menu_kb())
    except:
        await callback.message.answer(menu_text, reply_markup=main_menu_kb())
    
    await callback.answer()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===
async def broadcast_message(user_ids: list, text: str, exclude_user: int = None):
    """Рассылка сообщения всем пользователям"""
    success = 0
    failed = 0
    
    for user_id in user_ids:
        if user_id == exclude_user:
            continue
        try:
            await bot.send_message(user_id, text, reply_markup=main_menu_kb())
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
    
    if success > 0 or failed > 0:
        logger.info(f"Рассылка завершена: успешно {success}, ошибок {failed}")

async def get_user_attempts_count(giveaway_id: int, user_id: int) -> int:
    try:
        async with aiosqlite.connect("bot_database.db") as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM nft_attempts WHERE giveaway_id = ? AND user_id = ?",
                (giveaway_id, user_id)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
    except:
        return 0

async def main():
    await init_db()
    logger.info("🚀 Бот запущен!")
    logger.info("📊 Реферальная система активна")
    logger.info("🎰 NFT розыгрыши активны (ОПЛАТА ВКЛЮЧЕНА)")
    logger.info(f"💸 Админский канал: {ADMIN_CHANNEL_ID}")
    logger.info(f"👑 Админ ID: {ADMIN_ID}")
    logger.info(f"📏 Минимум рефералов: {MIN_REFERRALS}, минимум звезд: {MIN_STARS_WITHDRAW}")
    
    try:
        chat = await bot.get_chat(ADMIN_CHANNEL_ID)
        logger.info(f"✅ Доступ к каналу '{chat.title}' получен")
    except Exception as e:
        logger.error(f"❌ Нет доступа к админ-каналу {ADMIN_CHANNEL_ID}: {e}")
        logger.error("Добавьте бота в канал как администратора!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("❌ Бот остановлен вручную")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"❌ Критическая ошибка: {e}")
        sys.exit(1)




