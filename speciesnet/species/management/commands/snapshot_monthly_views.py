import logging
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from species.models import PageViewCount, PageViewMonthlySnapshot

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Snapshot monthly page view counts into PageViewMonthlySnapshot and reset "
        "PageViewCount.count to 0. Defaults to the previous calendar month."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Year to snapshot (default: previous month's year)",
        )
        parser.add_argument(
            "--month",
            type=int,
            default=None,
            help="Month to snapshot, 1–12 (default: previous month)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be written without modifying the database",
        )

    def handle(self, *args, **options):
        # Determine target year/month
        if options["year"] is not None and options["month"] is not None:
            year = options["year"]
            month = options["month"]
        else:
            today = date.today()
            if today.month == 1:
                year = today.year - 1
                month = 12
            else:
                year = today.year
                month = today.month - 1

        dry_run = options["dry_run"]

        self.stdout.write(f"{'[DRY RUN] ' if dry_run else ''}Snapshotting page views for {year}/{month:02d} ...")
        logger.info("snapshot_monthly_views started: year=%s month=%s dry_run=%s", year, month, dry_run)

        rows_processed = 0
        total_count = 0

        if dry_run:
            # Read-only preview — no transaction needed
            qs = PageViewCount.objects.filter(count__gt=0)
            for row in qs:
                self.stdout.write(
                    f"  Would snapshot: {row.get_page_type_display()} "
                    f"({row.object_id}) [{row.get_visitor_type_display()}] "
                    f"= {row.count} views → {year}/{month:02d}"
                )
                rows_processed += 1
                total_count += row.count

            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] Would process {rows_processed} rows totalling {total_count} views. No changes made."
                )
            )
            logger.info("snapshot_monthly_views dry-run complete: rows=%s total=%s", rows_processed, total_count)
            return

        # Live run — atomic block with select_for_update to prevent races
        with transaction.atomic():
            qs = PageViewCount.objects.select_for_update().filter(count__gt=0)

            for row in qs:
                delta = row.count

                summary, created = PageViewMonthlySnapshot.objects.get_or_create(
                    page_type=row.page_type,
                    object_id=row.object_id,
                    visitor_type=row.visitor_type,
                    year=year,
                    month=month,
                    defaults={"count": 0},
                )
                summary.count += delta
                summary.save(update_fields=["count"])

                row.count = 0
                row.save(update_fields=["count"])

                self.stdout.write(
                    f"  Snapshotted: {row.get_page_type_display()} "
                    f"({row.object_id}) [{row.get_visitor_type_display()}] "
                    f"= {delta} views → {year}/{month:02d} "
                    f"({'created' if created else 'updated'})"
                )
                rows_processed += 1
                total_count += delta

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Processed {rows_processed} rows totalling {total_count} views for {year}/{month:02d}."
            )
        )
        logger.info(
            "snapshot_monthly_views complete: year=%s month=%s rows=%s total=%s",
            year,
            month,
            rows_processed,
            total_count,
        )
