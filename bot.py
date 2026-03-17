import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.bot import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import API_TOKEN, SOURCES
from parser import get_updates
from database import init_db, is_new, get_all_users, add_user
from aiogram.filters import Command

# Настраиваем сессию
session = AiohttpSession()
bot = Bot(
    token=API_TOKEN, 
    session=session,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

async def send_news():
    print("Запуск проверки новостей...")
    raw_news = get_updates(SOURCES)
    
    # Фильтруем только те новости, которых нет в базе
    new_items = []
    for item in raw_news:
        if is_new(item["link"]):
            new_items.append(item)
    
    users = get_all_users()
    count = len(new_items)

    if count > 0:
        # Текст вступительного сообщения
        summary_text = f"🔔 <b>Найдено новостей: {count}</b>\n(с момента последней проверки)"
        
        for chat_id in users:
            try:
                # Отправляем сначала заголовок с количеством
                await bot.send_message(chat_id, summary_text)
                
                # Затем отправляем сами новости по одной
                for item in new_items:
                    text = f"<b>{item['source']}</b>\n{item['title']}\n{item['link']}"
                    await bot.send_message(chat_id, text)
                    await asyncio.sleep(0.5) # Защита от спам-фильтра Telegram
            except Exception as e:
                print(f"Ошибка при рассылке пользователю {chat_id}: {e}")
        
        print(f"Проверка завершена: разослано {count} новостей.")
    else:
        # Если новостей нет, можно либо молчать, либо логировать в консоль
        print("Проверка завершена: новых новостей не найдено.")

@dp.message(Command("start"))
async def cmd_start(message):
    add_user(message.chat.id)
    await message.answer("Вы подписаны на обновления ecom новостей! Я буду присылать подборки по расписанию.")

async def main():
    init_db()
    scheduler = AsyncIOScheduler()
    
    # Твое расписание
    scheduler.add_job(send_news, "cron", hour=9, minute=0)
    scheduler.add_job(send_news, "cron", hour=13, minute=0)
    scheduler.add_job(send_news, "cron", hour=17, minute=22)
    scheduler.start()

    print("Бот запущен и ждет расписания...") 
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())