import state_manager
import messenger_api
import database as db
import payment_verifier
from config import ADMIN_ID

from user import menu, purchase, account, support, custom, manual

async def handle_user_message(sender_psid: str, event: dict, lower_text: str, received_text: str):
    # 1. Check Paused Status & Maintenance
    if await db.is_user_paused(sender_psid):
        return
        
    user = await db.get_user(sender_psid)
    user_lang = user['lang'] if user else None
    
    if await db.get_maintenance_status():
        return await messenger_api.send_text(sender_psid, lang.get_text('maintenance_mode_message', user_lang or 'en'))

    # 2. Language Selection if New User
    if not user_lang:
        if lower_text in ['lang_en', 'english']: user_lang = 'en'
        elif lower_text in ['lang_tl', 'tagalog']: user_lang = 'tl'
        else:
            prompt = "Please select your language / Pumili ng wika:"
            replies = [{"title": "English", "payload": "lang_en"}, {"title": "Tagalog", "payload": "lang_tl"}]
            await messenger_api.send_quick_replies(sender_psid, prompt, replies)
            return
            
        await db.add_user(sender_psid, user_lang)
        return await menu.show_user_menu(sender_psid, user_lang)

    # 3. Handle 'Menu' Cancel Command
    state_obj = state_manager.get_user_state(sender_psid)
    state = state_obj["state"] if state_obj else None

    if lower_text == 'menu':
        state_manager.clear_user_state(sender_psid)
        return await menu.show_user_menu(sender_psid, user_lang)

    # 4. Handle Image Attachments (Receipts)
    message = event.get("message", {})
    attachments = message.get("attachments", [])
    if attachments and attachments[0].get("type") == "image":
        if not message.get("sticker_id") and state in ['awaiting_receipt_for_purchase', 'awaiting_receipt_for_custom_mod']:
            image_url = attachments[0]["payload"]["url"]
            await messenger_api.send_text(sender_psid, lang.get_text('receipt_analyzing', user_lang))
            
            if state == 'awaiting_receipt_for_custom_mod':
                # Custom Mod -> Forward to admin, don't use AI
                user_name = await messenger_api.get_user_profile(sender_psid)
                await messenger_api.send_text(ADMIN_ID, f"🧾 Custom Order Receipt from {user_name}\nOrder: {state_obj['orderAmount']} {state_obj['orderType']}")
                await messenger_api.send_text(sender_psid, lang.get_text('custom_mod_success', user_lang))
                state_manager.clear_user_state(sender_psid)
            else:
                # Normal Mod -> AI Scanner
                analysis = await payment_verifier.analyze_receipt_with_external_api(image_url)
                if not analysis:
                    analysis = {"extracted_info": {"amount": "0", "reference_number": "Failed"}}
                await purchase.handle_receipt_analysis(sender_psid, analysis, user_lang, image_url)
        return

    # 5. Route by State
    if state:
        if state == 'awaiting_want_mod': return await purchase.handle_want_mod(sender_psid, received_text, user_lang)
        elif state == 'awaiting_email_for_purchase': return await purchase.handle_email_for_purchase(sender_psid, received_text, user_lang)
        elif state == 'awaiting_mod_confirmation': return await purchase.handle_mod_confirmation(sender_psid, lower_text, user_lang)
        elif state == 'awaiting_manual_ref': return await manual.handle_manual_reference(sender_psid, received_text, user_lang)
        elif state == 'awaiting_manual_mod': return await manual.handle_manual_mod_selection(sender_psid, received_text, user_lang)
        elif state == 'awaiting_ref_for_check': return await account.process_check_claims(sender_psid, received_text, user_lang)
        elif state == 'awaiting_ref_for_replacement': return await account.process_replacement_request(sender_psid, received_text, user_lang)
        elif state == 'awaiting_custom_mod_type': return await custom.handle_custom_mod_type(sender_psid, received_text, user_lang)
        elif state == 'awaiting_custom_mod_amount': return await custom.handle_custom_mod_amount(sender_psid, received_text, user_lang)
        elif state == 'awaiting_admin_message': return await support.forward_message_to_admin(sender_psid, received_text, user_lang)
        elif state == 'awaiting_report_ref': return await support.process_report_ref(sender_psid, received_text, user_lang)
        elif state == 'awaiting_report_issue_desc': return await support.process_report_description(sender_psid, received_text, user_lang)
        
        # If user sends text instead of a receipt image
        if state in ['awaiting_receipt_for_purchase', 'awaiting_receipt_for_custom_mod']:
            if received_text:
                await messenger_api.send_text(sender_psid, lang.get_text('receipt_cancelled_text_instead', user_lang))
                state_manager.clear_user_state(sender_psid)
            return

    # 6. Default Menu Options Routing
    commands = {
        '1': lambda: purchase.handle_view_mods(sender_psid, user_lang),
        '2': lambda: account.prompt_check_claims(sender_psid, user_lang),
        '3': lambda: account.prompt_replacement(sender_psid, user_lang),
        '4': lambda: custom.prompt_custom_mod(sender_psid, user_lang),
        '5': lambda: support.prompt_admin_message(sender_psid, user_lang),
        '6': lambda: support.handle_view_proofs(sender_psid, user_lang),
        '7': lambda: support.prompt_report_ref(sender_psid, user_lang),
    }

    action = commands.get(lower_text)
    if action:
        await action()
    elif received_text and not message.get("sticker_id"):
        await menu.show_user_menu(sender_psid, user_lang)
