# -*- coding: utf-8 -*-
import aiosqlite
import logging
from typing import Optional, List, Tuple

DB_PATH = "bot_database.db"
logger = logging.getLogger(__name__)

async def init_db():
    """Создание всех таблиц SQLite с индексами"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Существующая таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    invited_by INTEGER,
                    referrals_count INTEGER DEFAULT 0,
                    stars_earned INTEGER DEFAULT 0,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(invited_by) REFERENCES users(user_id)
                )
            """)
            
            # Таблица заявок на вывод
            await db.execute("""
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL CHECK(amount > 0),
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'paid', 'rejected')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)
            
            # === NFT Таблица розыгрышей ===
            await db.execute("""
                CREATE TABLE IF NOT EXISTS nft_giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bet_amount INTEGER NOT NULL CHECK(bet_amount > 0),
                    nft_link TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1,
                    created_by INTEGER NOT NULL,
                    winner_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    FOREIGN KEY(created_by) REFERENCES users(user_id),
                    FOREIGN KEY(winner_id) REFERENCES users(user_id)
                )
            """)
            
            # === NFT Таблица попыток (убран UNIQUE чтобы были неограниченные попытки) ===
            await db.execute("""
                CREATE TABLE IF NOT EXISTS nft_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    giveaway_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    result TEXT CHECK(result IN ('win', 'lose', NULL)),
                    slot_result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(giveaway_id) REFERENCES nft_giveaways(id),
                    FOREIGN KEY(user_id) REFERENCES users(user_id)
                )
            """)
            
            # Индексы
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_referrals ON users(referrals_count DESC)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_user ON withdrawal_requests(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_withdrawals_status ON withdrawal_requests(status)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_giveaways_active ON nft_giveaways(is_active)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_attempts_giveaway ON nft_attempts(giveaway_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_attempts_user ON nft_attempts(user_id)")
            
            await db.commit()
            logger.info("База данных инициализирована успешно")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        raise

# === Существующие функции (без изменений) ===
async def add_user(user_id: int, username: Optional[str], full_name: str, invited_by: Optional[int] = None) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username, full_name, invited_by) VALUES (?, ?, ?, ?)",
                (user_id, username, full_name, invited_by)
            )
            await db.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя {user_id}: {e}")
        return False

async def get_user(user_id: int) -> Optional[Tuple]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return await cursor.fetchone()
    except Exception as e:
        logger.error(f"Ошибка получения пользователя {user_id}: {e}")
        return None

async def increment_referrals(user_id: int) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (user_id,))
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка инкремента рефералов {user_id}: {e}")
        return False

async def add_stars(user_id: int, amount: int = 1) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET stars_earned = stars_earned + ? WHERE user_id = ?", (amount, user_id))
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка начисления звезд {user_id}: {e}")
        return False

async def get_top_referrers(limit: int = 10) -> List[Tuple]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT user_id, username, referrals_count, stars_earned FROM users ORDER BY referrals_count DESC LIMIT ?",
                (limit,)
            )
            return await cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка получения топа: {e}")
        return []

async def create_withdrawal_request(user_id: int, amount: int) -> Optional[int]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT stars_earned FROM users WHERE user_id = ?",
                (user_id,)
            )
            balance_row = await cursor.fetchone()
            
            if not balance_row or balance_row[0] < amount:
                return None
            
            await db.execute(
                "UPDATE users SET stars_earned = stars_earned - ? WHERE user_id = ?",
                (amount, user_id)
            )
            
            cursor = await db.execute(
                "INSERT INTO withdrawal_requests (user_id, amount, status) VALUES (?, ?, 'pending')",
                (user_id, amount)
            )
            request_id = cursor.lastrowid
            await db.commit()
            return request_id
            
    except Exception as e:
        logger.error(f"Ошибка создания заявки {user_id}: {e}")
        return None

async def get_user_withdrawals(user_id: int) -> List[Tuple]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT id, amount, status, created_at FROM withdrawal_requests WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            return await cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка получения заявок {user_id}: {e}")
        return []

async def update_withdrawal_status(request_id: int, new_status: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE withdrawal_requests SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_status, request_id)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления статуса {request_id}: {e}")
        return False

async def get_withdrawal_request(request_id: int) -> Optional[Tuple]:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT * FROM withdrawal_requests WHERE id = ?", (request_id,))
            return await cursor.fetchone()
    except Exception as e:
        logger.error(f"Ошибка получения деталей заявки {request_id}: {e}")
        return None

async def get_pending_withdrawals_count(user_id: int) -> int:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM withdrawal_requests WHERE user_id = ? AND status = 'pending'",
                (user_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return 0

# === НОВЫЕ ФУНКЦИИ ДЛЯ NFT (ИСПРАВЛЕННЫЕ) ===
async def get_all_users() -> List[int]:
    """Получить всех пользователей для рассылки"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT user_id FROM users")
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Ошибка получения всех пользователей: {e}")
        return []

async def create_giveaway(bet_amount: int, nft_link: str, created_by: int) -> Optional[int]:
    """Создание нового розыгрыша (закрывает предыдущий активный)"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Закрываем предыдущий активный розыгрыш
            await db.execute(
                "UPDATE nft_giveaways SET is_active = 0 WHERE is_active = 1"
            )
            # Создаем новый
            cursor = await db.execute(
                "INSERT INTO nft_giveaways (bet_amount, nft_link, created_by) VALUES (?, ?, ?)",
                (bet_amount, nft_link, created_by)
            )
            await db.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Ошибка создания розыгрыша: {e}")
        return None

async def get_active_giveaway() -> Optional[Tuple]:
    """Получить активный розыгрыш"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT * FROM nft_giveaways WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
            )
            return await cursor.fetchone()
    except Exception as e:
        logger.error(f"Ошибка получения активного розыгрыша: {e}")
        return None

async def add_attempt(giveaway_id: int, user_id: int) -> Optional[int]:
    """Добавить новую попытку (всегда создает новую запись)"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO nft_attempts (giveaway_id, user_id) VALUES (?, ?)",
                (giveaway_id, user_id)
            )
            await db.commit()
            return cursor.lastrowid
    except Exception as e:
        logger.error(f"Ошибка добавления попытки: {e}")
        return None

async def update_attempt_result(attempt_id: int, result: str, slot_result: str) -> bool:
    """Обновить результат попытки"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE nft_attempts SET result = ?, slot_result = ? WHERE id = ?",
                (result, slot_result, attempt_id)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка обновления результата: {e}")
        return False

async def close_giveaway(giveaway_id: int, winner_id: int) -> bool:
    """Закрыть розыгрыш с победителем"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE nft_giveaways 
                   SET is_active = 0, winner_id = ?, ended_at = CURRENT_TIMESTAMP 
                   WHERE id = ?""",
                (winner_id, giveaway_id)
            )
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка закрытия розыгрыша: {e}")
        return False

async def get_giveaway_stats(giveaway_id: int) -> dict:
    """Получить статистику розыгрыша"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # Общее количество попыток
            cursor = await db.execute(
                "SELECT COUNT(*) FROM nft_attempts WHERE giveaway_id = ?",
                (giveaway_id,)
            )
            total = (await cursor.fetchone())[0]
            
            # Количество уникальных участников
            cursor = await db.execute(
                "SELECT COUNT(DISTINCT user_id) FROM nft_attempts WHERE giveaway_id = ?",
                (giveaway_id,)
            )
            unique = (await cursor.fetchone())[0]
            
            return {"total_attempts": total, "unique_users": unique}
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        return {"total_attempts": 0, "unique_users": 0}
