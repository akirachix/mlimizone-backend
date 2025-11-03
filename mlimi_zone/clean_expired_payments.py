from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from mlimi_zone.models import Payment 

class Command(BaseCommand):
    help = "Mark pending payments older than 10 minutes as FAILED"

    def handle(self, *args, **options):
        timeout_minutes = 10
        cutoff = timezone.now() - timedelta(minutes=timeout_minutes)

        expired = Payment.objects.filter(
            payment_status='pending',
            created_at__lt=cutoff
        )

        count = expired.update(payment_status='failed')
        if count:
            self.stdout.write(
                self.style.SUCCESS(f"Marked {count} pending payment(s) as FAILED")
            )
        else:
            self.stdout.write("No expired payments.")