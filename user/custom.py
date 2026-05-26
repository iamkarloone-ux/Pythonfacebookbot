import state_manager
import messenger_api
import language_manager as lang

async def prompt_custom_mod(sender_psid: str, user_lang: str):
    msg = lang.get_text('custom_mod_prompt_choice', user_lang)
    replies = [
        {"title": "💰 Custom Money", "payload": "custom_money"},
        {"title": "✨ Custom Gold", "payload": "custom_gold"},
        {"title": "⬅️ Back to Menu", "payload": "menu"}
    ]
    await messenger_api.send_quick_replies(sender_psid, msg, replies)
    state_manager.set_user_state(sender_psid, 'awaiting_custom_mod_type', lang=user_lang)

async def handle_custom_mod_type(sender_psid: str, text: str, user_lang: str):
    choice = text.strip().lower()
    if choice in ['custom_money', 'money', '1']:
        msg = lang.get_text('custom_mod_prompt_money', user_lang)
        order_type = "Money"
    elif choice in ['custom_gold', 'gold', '2']:
        msg = lang.get_text('custom_mod_prompt_gold', user_lang)
        order_type = "Gold"
    else:
        return await prompt_custom_mod(sender_psid, user_lang)
        
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_custom_mod_amount', orderType=order_type, lang=user_lang)

async def handle_custom_mod_amount(sender_psid: str, text: str, user_lang: str):
    state = state_manager.get_user_state(sender_psid)
    amount = text.strip()
    # (Simplified for length - in production you can parse '5m', '6k' etc to map exact prices)
    price = 150.0 
    
    msg = lang.get_text('custom_mod_prompt_payment', user_lang).replace('{orderAmount}', amount).replace('{orderType}', state['orderType']).replace('{price}', str(price)).replace('{gcashNumber}', "09123963204")
    
    await messenger_api.send_text(sender_psid, msg)
    state_manager.set_user_state(sender_psid, 'awaiting_receipt_for_custom_mod', orderType=state['orderType'], orderAmount=amount, price=price, lang=user_lang)

# The receipt for this state will be caught by the router and sent to the admin.
