import hashlib
import secrets

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Generate a new ASN Partner API key (see 'ASN Partner Species API — "
        "Requirements.md'). Prints the raw key once and the 'label:hash' "
        "entry to add to PARTNER_API_KEYS in .env. Stores nothing - the raw "
        "key cannot be recovered if lost, only regenerated under a new label."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'label',
            help="Partner key label, e.g. 'auctionfish' or 'auctionfish-next' for key rotation",
        )

    def handle(self, *args, **options):
        label = options['label'].strip()
        if not label:
            raise CommandError('label must not be empty')
        if ':' in label or ',' in label:
            raise CommandError("label must not contain ':' or ',' - those separate PARTNER_API_KEYS entries")

        raw_key = 'asn_partner_' + secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        self.stdout.write('')
        self.stdout.write(self.style.WARNING('Raw key (shown once - save it securely now):'))
        self.stdout.write(f'  {raw_key}')
        self.stdout.write('')
        self.stdout.write('Add this entry to PARTNER_API_KEYS in .env (comma-separate multiple entries):')
        self.stdout.write(f'  {label}:{key_hash}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            'Nothing was stored. Restart the Django container after updating .env, '
            'then give the raw key to the partner over a secure channel.'
        ))
