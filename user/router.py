# user/router.py
import state_manager
import messenger_api
import database as db
import payment_verifier
import language_manager as lang
from config import ADMIN_ID

from user import menu, purchase, account, support, custom, manual, car_injector, reseller_tool

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

    # 3. Handle 'Menu' Cancel Command (Isolated for Active Resellers)
    state_obj = state_manager.get_user_state(sender_psid)
    state = state_obj["state"] if state_obj else None

    if lower_text == 'menu':
        # If active in a reseller session, return to Reseller Menu instead of exiting
        if state_obj and state_obj["state"].startswith("awaiting_reseller_") and state_obj.get("target_email") and state_obj.get("target_pass"):
            return await reseller_tool.show_reseller_patch_menu(sender_psid, user_lang, state_obj)
        else:
            state_manager.clear_user_state(sender_psid)
            return await menu.show_user_menu(sender_psid, user_lang)

    # 4. Handle Image Attachments (Receipts)
    message = event.get("message", {})
    attachments = message.get("attachments", [])
    if attachments and attachments[0].get("type") == "image":
        if not message.get("sticker_id") and state in ['awaiting_receipt_for_purchase', 'awaiting_receipt_for_custom_mod', 'awaiting_receipt_for_car_injector']:
            image_url = attachments[0]["payload"]["url"]
            
            await messenger_api.send_text(sender_psid, lang.get_text('receipt_analyzing', user_lang))
            
            if state == 'awaiting_receipt_for_custom_mod':
                user_name = await messenger_api.get_user_profile(sender_psid)
                await messenger_api.send_text(ADMIN_ID, f"🧾 Custom Order Receipt from {user_name}\nOrder: {state_obj['orderAmount']} {state_obj['orderType']}")
                await messenger_api.send_text(sender_psid, lang.get_text('custom_mod_success', user_lang))
                state_manager.clear_user_state(sender_psid)
            elif state == 'awaiting_receipt_for_car_injector':
                analysis = await payment_verifier.analyze_receipt_with_external_api(image_url)
                if not analysis:
                    analysis = {"extracted_info": {"amount": "0", "reference_number": "Failed"}}
                await car_injector.handle_car_receipt_analysis(sender_psid, analysis, user_lang, image_url)
            else:
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
        elif state == 'awaiting_car_inject_email': return await car_injector.handle_car_injector_email(sender_psid, received_text, user_lang)
        elif state == 'awaiting_car_inject_password': return await car_injector.handle_car_injector_password(sender_psid, received_text, user_lang)
        elif state == 'awaiting_car_inject_choice': return await car_injector.handle_car_selection(sender_psid, received_text, user_lang)
        
        # Reseller Panel States
        elif state == 'awaiting_reseller_key': return await reseller_tool.handle_reseller_key(sender_psid, received_text, user_lang)
        elif state == 'awaiting_reseller_target_email': return await reseller_tool.handle_reseller_email(sender_psid, received_text, user_lang)
        elif state == 'awaiting_reseller_target_pass': return await reseller_tool.handle_reseller_password(sender_psid, received_text, user_lang)
        elif state == 'awaiting_reseller_patch_choice': return await reseller_tool.handle_reseller_patch_choice(sender_psid, received_text, user_lang)
        
        # Reseller Loopback State
        elif state == 'awaiting_reseller_post_patch_choice':
            choice = lower_text.strip()
            if choice in ['patch_again', '1', 'apply another patch']:
                return await reseller_tool.show_reseller_patch_menu(sender_psid, user_lang, state_obj)
            elif choice in ['reseller_switch_account', '2', 'switch account']:
                return await reseller_tool.handle_reseller_key(sender_psid, state_obj['license_key'], user_lang)
            else:
                state_manager.clear_user_state(sender_psid)
                return await menu.show_user_menu(sender_psid, user_lang)
        
        # Reseller Custom Resource Inputs
        elif state == 'awaiting_reseller_custom_silver': return await reseller_tool.handle_reseller_custom_silver(sender_psid, received_text, user_lang)
        elif state == 'awaiting_reseller_custom_gold': return await reseller_tool.handle_reseller_custom_gold(sender_psid, received_text, user_lang)
        elif state == 'awaiting_reseller_custom_xp': return await reseller_tool.handle_reseller_custom_xp(sender_psid, received_text, user_lang)
        
        # Reseller Nitro Sub-flows
        elif state == 'awaiting_reseller_nitro_choice': return await reseller_tool.handle_reseller_nitro_choice(sender_psid, lower_text, user_lang)
        elif state == 'awaiting_reseller_single_nitro_id': return await reseller_tool.handle_reseller_single_nitro_id(sender_psid, received_text, user_lang)
        
        # Reseller Car ID Input
        elif state == 'awaiting_reseller_car_id': 
            choice = lower_text.strip()
            if choice == 'patch_again':
                return await reseller_tool.show_reseller_patch_menu(sender_psid, user_lang, state_obj)
            return await reseller_tool.handle_reseller_car_id(sender_psid, received_text, user_lang)
        
        # Text instead of image fallback
        if state in ['awaiting_receipt_for_purchase', 'awaiting_receipt_for_custom_mod', 'awaiting_receipt_for_car_injector']:
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
        '8': lambda: car_injector.prompt_car_injector(sender_psid, user_lang),
        '9': lambda: reseller_tool.prompt_reseller_tool(sender_psid, user_lang),
    }

    action = commands.get(lower_text)
    if action:
        await action()
    elif received_text and not message.get("sticker_id"):
        await menu.show_user_menu(sender_psid, user_lang)
