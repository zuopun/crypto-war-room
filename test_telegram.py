import asyncio
import aiohttp

TELEGRAM_TOKEN = "8368203057:AAECjZIhHJKcid-itLTMhVbfpV2ko6vU4HU " 
TELEGRAM_CHAT_ID = "1510241198"

async def send_telegram(text):
    """發送 Telegram 訊息"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN.strip()}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, json=payload) as response:
                result = await response.json()
                if result.get('ok'):
                    print("✅ 訊息發送成功！")
                else:
                    print(f"❌ 發送失敗: {result}")
        except Exception as e:
            print(f"❌ Telegram 發送失敗: {e}")

async def main():
    test_msg = "✅ 測試訊息：監控機器人連線成功！\n時間: " + __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    await send_telegram(test_msg)

if __name__ == "__main__":
    asyncio.run(main())
