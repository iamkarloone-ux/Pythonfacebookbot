# user/menu.py
import database as db
import messenger_api
import language_manager as lang

async def show_user_menu(sender_psid: str, user_lang: str = 'en'):
    admin_info = await db.get_admin_info()
    is_online = admin_info and admin_info.get('is_online')
    
    initial_msg = lang.get_text('admin_online', user_lang) if is_online else lang.get_text('admin_offline', user_lang)
    await messenger_api.send_text(sender_psid, initial_msg)
    
    menu_text = f"{lang.get_text('welcome_message', user_lang)}\n\n"
    for i in range(1, 9):
        menu_text += f"{lang.get_text(f'menu_option_{i}', user_lang)}\n"
    menu_text += f"\n{lang.get_text('menu_suffix', user_lang)}"
    
    replies = [{"title": lang.get_text(f'menu_option_{i}_button', user_lang), "payload": str(i)} for i in range(1, 9)]
    await messenger_api.send_quick_replies(sender_psid, menu_text, replies)
