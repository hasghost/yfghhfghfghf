# -*- coding: utf-8 -*-
from aiogram.utils.keyboard import InlineKeyboardBuilder
from urllib.parse import quote

def main_menu_kb():
    """Главное меню с кнопкой NFT"""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Мой профиль", callback_data="profile")
    builder.button(text="🏆 Топ рефералов", callback_data="top")
    builder.button(text="💰 Заработать", callback_data="how_to_earn")
    builder.button(text="💸 Вывести Stars", callback_data="withdraw")
    builder.button(text="🎰 Получить NFT", callback_data="nft_giveaway")
    builder.adjust(1)
    return builder.as_markup()

def back_to_menu_kb():
    """Кнопка назад в меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data="back_to_menu")
    return builder.as_markup()

def share_link_kb(ref_link: str):
    """Кнопка для мгновенного шаринга ссылки"""
    builder = InlineKeyboardBuilder()
    encoded_link = quote(ref_link, safe='')
    builder.button(text="📤 Поделиться ссылкой", url=f"https://t.me/share/url?url={encoded_link}")
    builder.button(text="⬅️ В меню", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def withdrawal_amounts_kb():
    """Клавиатура с фиксированными суммами вывода"""
    builder = InlineKeyboardBuilder()
    amounts = [15, 25, 50, 100]
    for amount in amounts:
        builder.button(text=f"💎 {amount} Stars", callback_data=f"withdraw_{amount}")
    builder.button(text="📋 Мои заявки", callback_data="my_withdrawals")
    builder.button(text="⬅️ В меню", callback_data="back_to_menu")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

def my_withdrawals_kb():
    """Кнопка возврата из заявок"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В меню", callback_data="back_to_menu")
    return builder.as_markup()

def admin_withdrawal_kb(request_id: int):
    """Клавиатура для админа с заявкой"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Выплачено", callback_data=f"admin_paid_{request_id}")
    builder.button(text="❌ Отклонить", callback_data=f"admin_reject_{request_id}")
    builder.adjust(2)
    return builder.as_markup()

# === НОВЫЕ КЛАВИАТУРЫ ДЛЯ NFT ===
def nft_giveaway_kb(giveaway_id: int, bet_amount: int):
    """Клавиатура для участия в розыгрыше NFT"""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"🎰 Испытать удачу ({bet_amount} ⭐)", 
        callback_data=f"join_nft_{giveaway_id}"
    )
    builder.button(text="⬅️ В меню", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def nft_spin_again_kb():
    """Клавиатура после проигрыша (можно добавить повторную попытку)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Попробовать снова", callback_data="nft_giveaway")
    builder.button(text="⬅️ В меню", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def admin_menu_kb():
    """Главное меню админа"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика бота", callback_data="admin_stats")
    builder.button(text="🎰 Управление розыгрышами", callback_data="admin_giveaway")
    builder.button(text="📢 Рассылка", callback_data="admin_broadcast")
    builder.button(text="⬅️ Выйти", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def admin_back_kb():
    """Кнопка назад в админ-меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад к админке", callback_data="admin_menu")
    return builder.as_markup()

def admin_giveaway_manage_kb(has_active: bool):
    """Клавиатура управления розыгрышами"""
    builder = InlineKeyboardBuilder()
    
    if has_active:
        builder.button(text="🛑 Завершить текущий", callback_data="admin_stop_giveaway")
    
    builder.button(text="➕ Создать новый", callback_data="admin_create_giveaway")
    builder.button(text="📜 История", callback_data="admin_giveaway_history")
    builder.button(text="⬅️ Назад", callback_data="admin_menu")
    builder.adjust(1)
    return builder.as_markup()

def admin_cancel_kb():
    """Кнопка отмены"""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_action")
    return builder.as_markup()
