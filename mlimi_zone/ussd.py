from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from .models import ProduceListing, Cart, Order, Payment, MarketPrice, Crop, User, USSDSession, SMSLogs
from .sms import send_sms
from .daraja import DarajaClient
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

DISTRICT_TO_REGION = {
    'Blantyre': 'Southern Region', 'Zomba': 'Southern Region', 'Mulanje': 'Southern Region',
    'Thyolo': 'Southern Region', 'Chiradzulu': 'Southern Region', 'Nsanje': 'Southern Region',
    'Chikwawa': 'Southern Region', 'Phalombe': 'Southern Region', 'Mwanza': 'Southern Region',
    'Balaka': 'Southern Region', 'Mangochi': 'Southern Region', 'Machinga': 'Southern Region',
    'Neno': 'Southern Region',
    'Lilongwe': 'Central Region', 'Salima': 'Central Region', 'Dowa': 'Central Region',
    'Ntchisi': 'Central Region', 'Nkhotakota': 'Central Region', 'Kasungu': 'Central Region',
    'Mchinji': 'Central Region', 'Dedza': 'Central Region', 'Ntcheu': 'Central Region',
    'Mzimba': 'Northern Region', 'Karonga': 'Northern Region', 'Chitipa': 'Northern Region',
    'Rumphi': 'Northern Region', 'Nkhata Bay': 'Northern Region', 'Likoma': 'Northern Region'
}

def normalize_phone(phone):
    if not phone or not isinstance(phone, str):
        logger.error(f"Invalid phone input: {phone}")
        return ""
    phone = phone.replace('+', '').replace(' ', '').lstrip('0')
    if len(phone) < 9:
        logger.error(f"Phone number too short: {phone}")
        return ""
    if phone.startswith('254') and len(phone) == 12:
        return phone
    phone = '254' + phone[-9:]
    if len(phone) != 12 or not phone.startswith('254'):
        logger.error(f"Invalid phone number format after normalization: {phone}")
        return ""
    return phone

class USSDView(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        logger.info(f"Received request: {request.data or request.POST}")
        session_id = request.data.get('sessionId') or request.POST.get('sessionId')
        service_code = request.data.get('serviceCode') or request.POST.get('serviceCode')
        phone = normalize_phone(request.data.get('phoneNumber') or request.POST.get('phoneNumber'))
        if not phone.startswith('254') or len(phone) != 12:
            logger.error(f"Invalid phone number format: {phone}")
            return HttpResponse("END Invalid phone number format. Use 254XXXXXXXXX.", content_type='text/plain')
        text = (request.data.get('text') or request.POST.get('text') or '').strip()
        logger.info(f"Parsed: sessionId={session_id}, serviceCode={service_code}, phoneNumber={phone}, text={text}")
        parts = text.split('*') if text else []

        if parts and parts[-1] == '0':
            parts = parts[:-1]

        user = User.objects.filter(phone_number=phone).first()

        if not user:
            return self.handle_registration(parts, phone, session_id)

        if user.role == 'farmer':
            return farmer_ussd_callback(request)
        elif user.role == 'wholesaler':
            return wholesaler_ussd_callback(request)
        else:
            return HttpResponse('END Role not supported.', content_type='text/plain')

    def handle_registration(self, parts, phone, session_id):
        try:
            session = USSDSession.objects.get(session_id=session_id)
            session_data = session.data or {'level': 'reg_1'}
        except USSDSession.DoesNotExist:
            session_data = {'level': 'reg_1'}
            session = USSDSession.objects.create(session_id=session_id, phone_number=phone, data=session_data)

        if session_data['level'] == 'reg_1':
            if len(parts) == 0:
                response = "CON Welcome to MlimiZone. Register as:\n1. Farmer\n2. Wholesaler"
            else:
                role_choice = parts[0]
                if role_choice not in ['1', '2']:
                    response = "CON Invalid choice.\n1. Farmer\n2. Wholesaler"
                else:
                    session_data['level'] = 'reg_2'
                    session_data['role_choice'] = role_choice
                    response = "CON Enter your full name:"
                    session.data = session_data
                    session.save()
        elif session_data['level'] == 'reg_2':
            if len(parts) < 2:
                response = "CON Enter your full name:"
            else:
                name = parts[1].strip()
                session_data['name'] = name
                session_data['level'] = 'reg_3'
                response = "CON Enter your district (e.g., Blantyre, Lilongwe, Mzimba):"
                session.data = session_data
                session.save()
        elif session_data['level'] == 'reg_3':
            if len(parts) < 3:
                response = "CON Enter your district (e.g., Blantyre, Lilongwe, Mzimba):"
            else:
                district = parts[2].strip().title()
                if district not in DISTRICT_TO_REGION:
                    response = "CON Invalid district. Enter your district (e.g., Blantyre, Lilongwe, Mzimba):"
                else:
                    role_choice = session_data.get('role_choice')
                    name = session_data.get('name')
                    role = 'farmer' if role_choice == '1' else 'wholesaler'
                    user = User.objects.create(name=name, role=role, location=district, phone_number=phone)
                    message_body = f"Welcome to MlimiZone, {name}! You are registered as a {role}."
                    sms_response = send_sms(phone, message_body)
                    SMSLogs.objects.create(
                        user=user,
                        message_body=message_body,
                        status='delivered' if sms_response.get('status_code') == 200 else 'failed'
                    )
                    USSDSession.objects.filter(session_id=session_id).delete()
                    self.request.POST._mutable = True
                    self.request.POST['text'] = ''
                    if role == 'farmer':
                        return farmer_ussd_callback(self.request)
                    else:
                        return wholesaler_ussd_callback(self.request)

        if 'END' not in response:
            session.data = session_data
            session.save()
        return HttpResponse(response, content_type='text/plain')

@csrf_exempt
def farmer_ussd_callback(request):
    try:
        if request.method != 'POST':
            return HttpResponse("Method Not Allowed", status=405)

        session_id = request.POST.get('sessionId', '')
        phone_number = normalize_phone(request.POST.get('phoneNumber', '').strip())
        text = request.POST.get('text', '').strip()
        inputs = text.split('*') if text else ['']

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return HttpResponse("END Please register first.", content_type='text/plain')

        user_region = DISTRICT_TO_REGION.get(user.location, 'Southern Region')

        try:
            session = USSDSession.objects.get(session_id=session_id)
            session_data = session.data or {'level': 1, 'previous_levels': []}
        except USSDSession.DoesNotExist:
            session_data = {'level': 1, 'previous_levels': []}
            session = USSDSession.objects.create(session_id=session_id, phone_number=phone_number, data=session_data)

        level = session_data.get('level', 1)

        if level == 1:
            if not text:
                response = "CON Welcome to MlimiZone Farmers\n1. See market prices\n2. List your produce\n00. Main menu"
            elif inputs[0] == '1':
                session_data['previous_levels'].append(1)
                session_data['level'] = 1.1
                response = "CON Select crop for market prices:\n1. Maize\n2. Peas\n3. Rice\n4. Ground nuts\n0. Back\n00. Main menu"
            elif inputs[0] == '2':
                session_data['previous_levels'].append(1)
                session_data['level'] = 2.1
                response = "CON Select crop to list:\n1. Maize\n2. Peas\n3. Rice\n4. Ground nuts\n0. Back\n00. Main menu"
            elif inputs[0] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Farmers\n1. See market prices\n2. List your produce\n00. Main menu"
            else:
                response = "END Invalid option."
                USSDSession.objects.filter(session_id=session_id).delete()

        elif level == 1.1:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Welcome to MlimiZone Farmers\n1. See market prices\n2. List your produce\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Farmers\n1. See market prices\n2. List your produce\n00. Main menu"
            else:
                crop_map = {'1': 'Maize', '2': 'Peas', '3': 'Rice', '4': 'Ground nuts'}
                if inputs[-1] in crop_map:
                    session_data['crop'] = crop_map[inputs[-1]]
                    session_data['previous_levels'].append(1.1)
                    session_data['level'] = 1.2
                    prices = MarketPrice.objects.filter(crop__crop_name=session_data['crop']).order_by('location')
                    if not prices:
                        response = f"CON No prices available for {session_data['crop']}.\n0. Back\n00. Main menu"
                    else:
                        price_list = "\n".join([f"{price.crop.crop_name}: {price.location} {price.price_per_unit} MWK" for price in prices])
                        response = f"CON Prices for {session_data['crop']}:\n{price_list}\n0. Back\n00. Main menu"
                else:
                    response = "END Invalid crop selection"
                    USSDSession.objects.filter(session_id=session_id).delete()

        elif level == 1.2:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Select crop for market prices:\n1. Maize\n2. Peas\n3. Rice\n4. Ground nuts\n0. Back\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Farmers\n1. See market prices\n2. List your produce\n00. Main menu"
            else:
                response = "END Invalid option"
                USSDSession.objects.filter(session_id=session_id).delete()

        elif level == 2.1:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Welcome to MlimiZone Farmers\n1. See market prices\n2. List your produce\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Farmers\n1. See market prices\n2. List your produce\n00. Main menu"
            else:
                crop_map = {'1': 'Maize', '2': 'Peas', '3': 'Rice', '4': 'Ground nuts'}
                selected_crop = crop_map.get(inputs[-1])
                if selected_crop:
                    session_data['crop'] = selected_crop
                    session_data['previous_levels'].append(2.1)
                    session_data['level'] = 2.2
                    response = f"CON Enter quantity in KG for {selected_crop}:\n0. Back\n00. Main menu"
                else:
                    response = "END Invalid crop option."
                    USSDSession.objects.filter(session_id=session_id).delete()

        elif level == 2.2:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Select crop to list:\n1. Maize\n2. Peas\n3. Rice\n4. Ground nuts\n0. Back\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Farmers\n1. See market prices\n2. List your produce\n00. Main menu"
            else:
                try:
                    quantity = Decimal(inputs[-1])
                    if quantity <= 0:
                        response = f"CON Invalid quantity. Enter a number above 0 for {session_data.get('crop')}:\n0. Back\n00. Main menu"
                    else:
                        crop_name = session_data.get('crop')
                        crop = Crop.objects.get(crop_name=crop_name)
                        price_obj = MarketPrice.objects.filter(crop=crop, location=user_region).first()
                        if not price_obj:
                            response = f"CON No market price for {crop_name} in {user_region}. Try another crop or contact support.\n0. Back\n00. Main menu"
                        else:
                            price_per_kg = price_obj.price_per_unit
                            listing = ProduceListing.objects.create(
                                farmer=user,
                                crop=crop,
                                quantity=quantity
                            )
                            total_price = quantity * price_per_kg
                            message_body = f"Listed {quantity} KG of {crop_name} at {price_per_kg} MWK/kg. Total: {total_price} MWK"
                            sms_response = send_sms(user.phone_number, message_body)
                            SMSLogs.objects.create(
                                user=user,
                                message_body=message_body,
                                status='delivered' if sms_response.get('status_code') == 200 else 'failed'
                            )
                            response = f"CON You have listed {quantity} KG of {crop_name} at {price_per_kg} MWK/kg. Total: {total_price} MWK.\n0. Back\n00. Main menu"
                            session_data['level'] = 2.1  # Reset to crop selection
                            session_data['previous_levels'] = [1]
                except (ValueError, Crop.DoesNotExist):
                    response = f"CON Invalid quantity or crop. Enter quantity in KG for {session_data.get('crop')}:\n0. Back\n00. Main menu"

        else:
            response = "END Invalid session state."
            USSDSession.objects.filter(session_id=session_id).delete()

        if 'END' not in response:
            session.data = session_data
            session.save()

        logger.info(f"Sending response: {response}")
        return HttpResponse(response, content_type='text/plain')

    except Exception as e:
        logger.error(f"Error in farmer_ussd_callback: {e}")
        USSDSession.objects.filter(session_id=session_id).delete()
        return HttpResponse("END Session error", status=500)

@csrf_exempt
def wholesaler_ussd_callback(request):
    try:
        if request.method != 'POST':
            logger.warning(f"Invalid request method: {request.method}")
            return HttpResponse("Method Not Allowed", status=405)

        session_id = request.POST.get('sessionId', '')
        phone_number = normalize_phone(request.POST.get('phoneNumber', '').strip())
        service_code = request.POST.get('serviceCode', '')
        text = request.POST.get('text', '').strip()
        inputs = text.split('*') if text else ['']

        logger.info(f"Received USSD request: sessionId={session_id}, phoneNumber={phone_number}, serviceCode={service_code}, text={text}")

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            return HttpResponse("END Please register first.", content_type='text/plain')

        if not user.phone_number:
            logger.error(f"User {user.name} has no phone number")
            return HttpResponse("END Invalid user phone number. Contact support.", content_type='text/plain')

        user_region = DISTRICT_TO_REGION.get(user.location, 'Southern Region')

        try:
            session = USSDSession.objects.get(session_id=session_id)
            session_data = session.data or {'level': 1, 'previous_levels': []}
        except USSDSession.DoesNotExist:
            session_data = {'level': 1, 'previous_levels': []}
            session = USSDSession.objects.create(session_id=session_id, phone_number=phone_number, data=session_data)

        if session_data.get('level') == 1:
            if not text:
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            elif inputs[0] == '1':
                session_data['previous_levels'].append(1)
                session_data['level'] = 1.1
                response = "CON Select crop for market prices:\n1. Maize\n2. Peas\n3. Rice\n4. Ground nuts\n0. Back\n00. Main menu"
            elif inputs[0] == '2':
                session_data['previous_levels'].append(1)
                session_data['level'] = 2
                response = "CON Which crop do you want to book?\n1. Maize\n2. Peas\n3. Rice\n4. Ground nuts\n0. Back\n00. Main menu"
            elif inputs[0] == '3':
                session_data['previous_levels'].append(1)
                session_data['level'] = 5
                orders = Order.objects.filter(wholesaler=user, status='unpaid')
                if not orders:
                    response = "END You have no unpaid orders."
                    USSDSession.objects.filter(session_id=session_id).delete()
                else:
                    session_data['orders'] = [order.order_id for order in orders]
                    order_list = "\n".join([f"{i+1}. {order.croplisting.crop.crop_name} from {order.croplisting.farmer.phone_number} - {order.croplisting.quantity} KG" for i, order in enumerate(orders)])
                    response = f"CON Your unpaid orders:\n{order_list}\n0. Back\n00. Main menu"
            elif inputs[0] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            else:
                response = "END Invalid option"
                USSDSession.objects.filter(session_id=session_id).delete()

        elif session_data.get('level') == 1.1:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            else:
                crop_map = {'1': 'Maize', '2': 'Peas', '3': 'Rice', '4': 'Ground nuts'}
                if inputs[-1] in crop_map:
                    session_data['crop'] = crop_map[inputs[-1]]
                    session_data['previous_levels'].append(1.1)
                    session_data['level'] = 1.2
                    prices = MarketPrice.objects.filter(crop__crop_name=session_data['crop']).order_by('location')
                    if not prices:
                        response = f"CON No prices available for {session_data['crop']}.\n0. Back\n00. Main menu"
                    else:
                        price_list = "\n".join([f"{price.crop.crop_name}: {price.location} {price.price_per_unit} MWK" for price in prices])
                        response = f"CON Prices for {session_data['crop']}:\n{price_list}\n0. Back\n00. Main menu"
                else:
                    response = "END Invalid crop selection"
                    USSDSession.objects.filter(session_id=session_id).delete()

        elif session_data.get('level') == 1.2:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Select crop for market prices:\n1. Maize\n2. Peas\n3. Rice\n4. Ground nuts\n0. Back\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            else:
                response = "END Invalid option"
                USSDSession.objects.filter(session_id=session_id).delete()

        elif session_data.get('level') == 2:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            else:
                crop_map = {'1': 'Maize', '2': 'Peas', '3': 'Rice', '4': 'Ground nuts'}
                if inputs[-1] in crop_map:
                    session_data['crop'] = crop_map[inputs[-1]]
                    session_data['previous_levels'].append(2)
                    session_data['level'] = 3
                    try:
                        crop = Crop.objects.get(crop_name=session_data['crop'])
                        listings = ProduceListing.objects.filter(crop=crop).exclude(order__isnull=False)
                        if not listings:
                            response = f"END No available {session_data['crop']} listings."
                            USSDSession.objects.filter(session_id=session_id).delete()
                        else:
                            session_data['listings'] = [listing.croplisting_id for listing in listings]
                            listing_str = "\n".join([f"{i+1}. {listing.farmer.phone_number} - {listing.quantity} KG at {MarketPrice.objects.filter(crop=crop, location=DISTRICT_TO_REGION.get(listing.farmer.location, 'Southern Region')).first().price_per_unit} MWK" for i, listing in enumerate(listings)])
                            response = f"CON Available {session_data['crop']} for sale:\n{listing_str}\n0. Back\n00. Main menu"
                    except Crop.DoesNotExist:
                        response = "END Invalid crop."
                        USSDSession.objects.filter(session_id=session_id).delete()
                else:
                    response = "END Invalid crop selection"
                    USSDSession.objects.filter(session_id=session_id).delete()

        elif session_data.get('level') == 3:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Which crop do you want to book?\n1. Maize\n2. Peas\n3. Rice\n4. Ground nuts\n0. Back\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            else:
                try:
                    selection = int(inputs[-1]) - 1
                    if 0 <= selection < len(session_data.get('listings', [])):
                        listing_id = session_data['listings'][selection]
                        listing = ProduceListing.objects.get(croplisting_id=listing_id)
                        session_data['selected_listing'] = listing_id
                        session_data['previous_levels'].append(3)
                        session_data['level'] = 4
                        price_per_kg = MarketPrice.objects.filter(crop=listing.crop, location=DISTRICT_TO_REGION.get(listing.farmer.location, 'Southern Region')).first()
                        if not price_per_kg:
                            logger.error(f"No price found for crop {listing.crop.crop_name} in {DISTRICT_TO_REGION.get(listing.farmer.location, 'Southern Region')}")
                            response = "CON No market price available. Contact support.\n0. Back\n00. Main menu"
                            return HttpResponse(response, content_type='text/plain')
                        price_per_kg = price_per_kg.price_per_unit
                        response = f"CON Confirm booking for {listing.crop.crop_name} from {listing.farmer.phone_number} - {listing.quantity} KG at {price_per_kg} MWK?\n1. Yes\n2. No\n0. Back\n00. Main menu"
                    else:
                        response = "END Invalid selection"
                        USSDSession.objects.filter(session_id=session_id).delete()
                except (ValueError, ProduceListing.DoesNotExist):
                    response = "END Invalid input"
                    USSDSession.objects.filter(session_id=session_id).delete()

        elif session_data.get('level') == 4:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                try:
                    crop = Crop.objects.get(crop_name=session_data.get('crop', 'Maize'))
                    listings = ProduceListing.objects.filter(crop=crop).exclude(order__isnull=False)
                    if not listings:
                        response = f"END No available {session_data.get('crop', 'Maize')} listings."
                        USSDSession.objects.filter(session_id=session_id).delete()
                    else:
                        session_data['listings'] = [listing.croplisting_id for listing in listings]
                        listing_str = "\n".join([f"{i+1}. {listing.farmer.phone_number} - {listing.quantity} KG at {MarketPrice.objects.filter(crop=crop, location=DISTRICT_TO_REGION.get(listing.farmer.location, 'Southern Region')).first().price_per_unit} MWK" for i, listing in enumerate(listings)])
                        response = f"CON Available {session_data['crop']} for sale:\n{listing_str}\n0. Back\n00. Main menu"
                except Crop.DoesNotExist:
                    response = "END Invalid crop."
                    USSDSession.objects.filter(session_id=session_id).delete()
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            else:
                if inputs[-1] == '1':
                    listing_id = session_data.get('selected_listing')
                    if listing_id:
                        try:
                            listing = ProduceListing.objects.get(croplisting_id=listing_id)
                            cart, created = Cart.objects.get_or_create(wholesaler=user)
                            price_per_kg = MarketPrice.objects.filter(crop=listing.crop, location=DISTRICT_TO_REGION.get(listing.farmer.location, 'Southern Region')).first()
                            if not price_per_kg:
                                logger.error(f"No price found for crop {listing.crop.crop_name} in {DISTRICT_TO_REGION.get(listing.farmer.location, 'Southern Region')}")
                                response = "CON No market price available. Contact support.\n0. Back\n00. Main menu"
                                return HttpResponse(response, content_type='text/plain')
                            price_per_kg = price_per_kg.price_per_unit
                            order = Order.objects.create(
                                cart=cart,
                                wholesaler=user,
                                croplisting=listing,
                                price=listing.quantity * price_per_kg,
                                status='unpaid'
                            )
                            message_body = f"Booked {listing.quantity} KG of {listing.crop.crop_name} from {listing.farmer.phone_number} for {order.price} MWK"
                            sms_response = send_sms(user.phone_number, message_body)
                            SMSLogs.objects.create(
                                user=user,
                                message_body=message_body,
                                status='delivered' if sms_response.get('status_code') == 200 else 'failed'
                            )
                            farmer_message = f"Your {listing.quantity} KG of {listing.crop.crop_name} has been booked by {user.name}. Expect payment of {order.price} MWK soon."
                            farmer_sms = send_sms(listing.farmer.phone_number, farmer_message)
                            SMSLogs.objects.create(
                                user=listing.farmer,
                                message_body=farmer_message,
                                status='delivered' if farmer_sms.get('status_code') == 200 else 'failed'
                            )
                            response = f"CON Booking successful. Go to Pay to complete payment.\n0. Back\n00. Main menu"
                            session_data['level'] = 2
                            session_data['previous_levels'] = [1]
                        except (ProduceListing.DoesNotExist, Cart.DoesNotExist) as e:
                            logger.error(f"Booking error: {str(e)}")
                            response = "END Error booking."
                            USSDSession.objects.filter(session_id=session_id).delete()
                    else:
                        response = "END Error booking."
                        USSDSession.objects.filter(session_id=session_id).delete()
                else:
                    response = "END Booking cancelled."
                    USSDSession.objects.filter(session_id=session_id).delete()

        elif session_data.get('level') == 5:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            else:
                try:
                    selection = int(inputs[-1]) - 1
                    if 0 <= selection < len(session_data.get('orders', [])):
                        order_id = session_data['orders'][selection]
                        order = Order.objects.get(order_id=order_id)
                        session_data['selected_order'] = order_id
                        session_data['previous_levels'].append(5)
                        session_data['level'] = 6
                        response = f"CON Confirm payment for {order.croplisting.crop.crop_name} from {order.croplisting.farmer.phone_number} - {order.croplisting.quantity} KG ({order.price} MWK)?\n1. Yes\n2. No\n0. Back\n00. Main menu"
                    else:
                        response = "END Invalid selection"
                        USSDSession.objects.filter(session_id=session_id).delete()
                except (ValueError, Order.DoesNotExist):
                    response = "END Invalid input"
                    USSDSession.objects.filter(session_id=session_id).delete()

        elif session_data.get('level') == 6:
            if inputs[-1] == '0':
                session_data['level'] = session_data['previous_levels'].pop() if session_data['previous_levels'] else 1
                orders = Order.objects.filter(wholesaler=user, status='unpaid')
                if not orders:
                    response = "END You have no unpaid orders."
                    USSDSession.objects.filter(session_id=session_id).delete()
                else:
                    session_data['orders'] = [order.order_id for order in orders]
                    order_list = "\n".join([f"{i+1}. {order.croplisting.crop.crop_name} from {order.croplisting.farmer.phone_number} - {order.croplisting.quantity} KG" for i, order in enumerate(orders)])
                    response = f"CON Your unpaid orders:\n{order_list}\n0. Back\n00. Main menu"
            elif inputs[-1] == '00':
                session_data['level'] = 1
                session_data['previous_levels'] = []
                response = "CON Welcome to MlimiZone Wholesaler\n1. See market prices\n2. Book produce\n3. Pay for orders\n00. Main menu"
            else:
                if inputs[-1] == '1':
                    order_id = session_data.get('selected_order')
                    if not order_id:
                        logger.error("No selected order found")
                        response = "END No order selected."
                        USSDSession.objects.filter(session_id=session_id).delete()
                        return HttpResponse(response, content_type='text/plain')
                    try:
                        order = Order.objects.get(order_id=order_id)
                        if not order.price or order.price <= 0:
                            logger.error(f"Invalid order price for order {order_id}: {order.price}")
                            response = "CON Invalid order price. Contact support.\n0. Back\n00. Main menu"
                            return HttpResponse(response, content_type='text/plain')
                        phone_number = normalize_phone(user.phone_number)
                        if not phone_number:
                            logger.error(f"Invalid phone number for user {user.name}: {user.phone_number}")
                            response = "CON Invalid phone number. Contact support.\n0. Back\n00. Main menu"
                            return HttpResponse(response, content_type='text/plain')
                        amount = int(float(order.price))  # Ensure integer for M-Pesa
                        if amount <= 0:
                            logger.error(f"Invalid payment amount: {amount}")
                            response = "CON Invalid payment amount. Contact support.\n0. Back\n00. Main menu"
                            return HttpResponse(response, content_type='text/plain')
                        daraja = DarajaClient()
                        stk_response = daraja.stk_push(
                            phone_number=phone_number,
                            amount=amount,
                            account_reference=f"Order_{order.order_id}",
                            transaction_desc=f"Payment for {order.croplisting.crop.crop_name}"
                        )
                        logger.info(f"STK Push request: phone={phone_number}, amount={amount}")
                        logger.info(f"STK Push response: {stk_response}")
                        if 'ResponseCode' in stk_response and stk_response['ResponseCode'] == '0':
                            Payment.objects.create(
                                order=order,
                                amount=order.price,
                                payment_status='pending',
                                transaction_ref=stk_response['CheckoutRequestID']
                            )
                            message_body = f"M-Pesa payment of {order.price} MWK for order {order.order_id} initiated. Check your phone."
                            sms_response = send_sms(user.phone_number, message_body)
                            SMSLogs.objects.create(
                                user=user,
                                message_body=message_body,
                                status='delivered' if sms_response.get('status_code') == 200 else 'failed'
                            )
                            farmer_message = f"Payment of {order.price} MWK for {order.croplisting.quantity} KG of {order.croplisting.crop.crop_name} initiated by {user.name}."
                            farmer_sms = send_sms(order.croplisting.farmer.phone_number, farmer_message)
                            SMSLogs.objects.create(
                                user=order.croplisting.farmer,
                                message_body=farmer_message,
                                status='delivered' if farmer_sms.get('status_code') == 200 else 'failed'
                            )
                            response = "END M-Pesa payment initiated. Check your phone for PIN prompt."
                            USSDSession.objects.filter(session_id=session_id).delete()
                        else:
                            error_message = stk_response.get('error', 'Unknown error')
                            logger.error(f"STK Push failed: {error_message}")
                            response = f"CON Payment failed: {error_message}. Try again.\n0. Back\n00. Main menu"
                    except Exception as payment_error:
                        logger.error(f"Payment error: {str(payment_error)}")
                        response = f"CON Error processing payment: {str(payment_error)}. Try again.\n0. Back\n00. Main menu"
                else:
                    response = "END Payment cancelled."
                    USSDSession.objects.filter(session_id=session_id).delete()
        else:
            response = "END Invalid option"
            USSDSession.objects.filter(session_id=session_id).delete()

        if 'END' not in response:
            session.data = session_data
            session.save()

        logger.info(f"Sending response: {response}")
        return HttpResponse(response, content_type='text/plain')

    except Exception as e:
        logger.error(f"Error in wholesaler_ussd_callback: {str(e)}")
        try:
            USSDSession.objects.filter(session_id=session_id).delete()
        except Exception as cleanup_error:
            logger.error(f"Error cleaning up session: {str(cleanup_error)}")
        return HttpResponse("END Session error", status=500)