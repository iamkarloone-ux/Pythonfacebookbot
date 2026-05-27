# messenger_api.py
import httpx
from config import PAGE_ACCESS_TOKEN

user_profile_cache = {}

async def send_text(psid: str, text: str):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": psid},
        "message": {"text": text}
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload)
        except Exception as e:
            print(f"Error sending text: {e}")

async def send_quick_replies(psid: str, text: str, replies: list):
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    quick_replies = [
        {"content_type": "text", "title": r["title"], "payload": r["payload"]}
        for r in replies
    ]
    payload = {
        "recipient": {"id": psid},
        "message": {"text": text, "quick_replies": quick_replies}
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload)
        except Exception as e:
            print(f"Error sending quick replies: {e}")

async def send_image(psid: str, image_url: str):
    """Sends a visual image attachment bubble to Facebook Messenger."""
    url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
    payload = {
        "recipient": {"id": psid},
        "message": {
            "attachment": {
                "type": "image",
                "payload": {
                    "url": image_url,
                    "is_reusable": True
                }
            }
        }
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, json=payload)
        except Exception as e:
            print(f"Error sending image message: {e}")

async def get_user_profile(psid: str) -> str:
    if psid in user_profile_cache:
        return user_profile_cache[psid]
        
    url = f"https://graph.facebook.com/v19.0/{psid}?fields=first_name,last_name&access_token={PAGE_ACCESS_TOKEN}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            data = response.json()
            full_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
            if full_name:
                user_profile_cache[psid] = full_name
                return full_name
        except Exception:
            pass
    return psid
