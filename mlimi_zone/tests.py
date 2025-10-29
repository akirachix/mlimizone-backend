from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch
from decimal import Decimal
from mlimi_zone.models import (
    User, Crop, MarketPrice, ProduceListing, Cart, Order, Payment, USSDSession
)


class USSDTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.phone = '254704503769'
        self.session_id = 'test-session-123'

        self.crop_maize = Crop.objects.create(crop_name='Maize')
        MarketPrice.objects.create(
            crop=self.crop_maize,
            location='Southern Region',
            price_per_unit=Decimal('100')
        )

        self.sms_patch = patch('mlimi_zone.sms.send_sms',
                               return_value={'status_code': 200})
        self.stk_patch = patch(
            'mlimi_zone.daraja.DarajaClient.stk_push',
            return_value={'ResponseCode': '0', 'CheckoutRequestID': 'test-id'}
        )
        self.sms_patch.start()
        self.stk_patch.start()

    def tearDown(self):
        self.sms_patch.stop()
        self.stk_patch.stop()

    def test_wholesaler_registration_and_payment_flow(self):
        self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '2'
        })
        self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '2*Jane Doe'
        })
        resp = self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '2*Jane Doe*Blantyre'
        })
        self.assertContains(resp, "Welcome to MlimiZone Wholesaler")

        user = User.objects.get(phone_number=self.phone)
        self.assertEqual(user.role, 'wholesaler')

        farmer = User.objects.create(
            name='John Mwangi',
            role='farmer',
            location='Blantyre',
            phone_number='254783781799'
        )
        ProduceListing.objects.create(
            farmer=farmer,
            crop=self.crop_maize,
            quantity=Decimal('50')
        )

        self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '2'
        })
        self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '2*1'
        })
        self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '2*1*1'
        })
        resp = self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '2*1*1*1'
        })
        self.assertContains(resp, "Booking successful")

        resp = self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '3'
        })
        self.assertContains(resp, "Your unpaid orders")
        self.assertContains(resp, "Maize")

        resp = self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '3*1'
        })
        self.assertContains(resp, "Confirm payment")

        resp = self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '3*1*1'
        })
        self.assertContains(resp, "request is being processed")

        resp = self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': self.session_id,
            'phoneNumber': self.phone,
            'text': '3'
        })
        self.assertContains(resp, "You have no booked crops to pay for")

    def test_view_all_orders_with_star(self):
        wholesaler = User.objects.create(
            name='Big Buyer',
            role='wholesaler',
            location='Lilongwe',
            phone_number='254704503769'
        )
        farmer = User.objects.create(
            name='Many Farmer',
            role='farmer',
            location='Lilongwe',
            phone_number='254783781799'
        )
        crop = Crop.objects.create(crop_name='Rice')
        MarketPrice.objects.create(crop=crop, location='Central Region', price_per_unit=150)

        resp = self.client.post(reverse('mlimi_zone:ussd'), {
            'sessionId': 'star-session',
            'phoneNumber': wholesaler.phone_number,
            'text': '3'
        })
  
      