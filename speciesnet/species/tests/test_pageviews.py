"""
Tests for page view reporting and quarterly archiving ("Page View Tracking — Spec.md"):
period labels, close-out, clear, the Page Views page, CSV export, the command and the task.
"""
import csv
import io
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from pending_actions.tasks import snapshot_page_views_task
from species.models import PageViewCount, PageViewMonthlySnapshot, Species, User
from species.services import pageview_service as service

SPEC = PageViewCount.PageType.SPECIES
CLUB = PageViewCount.PageType.AQUARIST_CLUB
AN = PageViewCount.VisitorType.ANONYMOUS
AU = PageViewCount.VisitorType.AUTHENTICATED


def _count(page_type, object_id, visitor_type, count):
    return PageViewCount.objects.create(page_type=page_type, object_id=object_id, visitor_type=visitor_type, count=count)


class PeriodTests(TestCase):

    def test_labels(self):
        self.assertEqual(service.period_label(2027, 3), '2027 Q1')
        self.assertEqual(service.period_label(2027, 12), '2027 Q4')
        self.assertEqual(service.period_label(2026, 2), '2026-02')
        self.assertEqual(service.period_slug(2027, 6), '2027-Q2')

    def test_previous_and_current_quarter(self):
        self.assertEqual(service.previous_quarter(date(2027, 1, 1)), (2026, 12))
        self.assertEqual(service.previous_quarter(date(2027, 4, 1)), (2027, 3))
        self.assertEqual(service.previous_quarter(date(2027, 6, 30)), (2027, 3))
        self.assertEqual(service.current_quarter(date(2027, 11, 5)), (2027, 12))


class CloseOutAndClearTests(TestCase):

    def setUp(self):
        _count(SPEC, 1, AN, 5)
        _count(SPEC, 1, AU, 2)
        _count(SPEC, 2, AN, 0)

    def test_close_out_archives_then_resets(self):
        result = service.close_out_period(2027, 3)
        self.assertEqual((result['rows'], result['views']), (2, 7))
        self.assertFalse(result['added_to_existing'])
        self.assertEqual(PageViewMonthlySnapshot.objects.get(object_id=1, visitor_type=AN, year=2027, month=3).count, 5)
        self.assertEqual(service.current_totals(), (0, 0))

    def test_closing_out_same_period_twice_adds(self):
        service.close_out_period(2027, 3)
        PageViewCount.objects.filter(object_id=1, visitor_type=AN).update(count=4)
        self.assertTrue(service.close_out_period(2027, 3)['added_to_existing'])
        self.assertEqual(PageViewMonthlySnapshot.objects.get(object_id=1, visitor_type=AN).count, 9)

    def test_dry_run_changes_nothing(self):
        self.assertEqual(service.close_out_period(2027, 3, dry_run=True)['views'], 7)
        self.assertFalse(PageViewMonthlySnapshot.objects.exists())
        self.assertEqual(service.current_totals(), (2, 7))

    def test_clear_deletes_counters_but_not_snapshots(self):
        service.close_out_period(2027, 3)
        _count(SPEC, 3, AN, 8)
        self.assertEqual(service.clear_current_counts()['views'], 8)
        self.assertFalse(PageViewCount.objects.exists())
        self.assertEqual(PageViewMonthlySnapshot.objects.count(), 2)

    def test_ranking_splits_visitor_types_and_limits(self):
        _count(SPEC, 3, AU, 1)
        rows = service.ranking(SPEC)
        self.assertEqual(rows[0], {'object_id': 1, 'total': 7, 'anonymous': 5, 'authenticated': 2})
        self.assertEqual([r['object_id'] for r in rows], [1, 3])      # zero rows left out
        self.assertEqual(len(service.ranking(SPEC, limit=1)), 1)


class CommandAndTaskTests(TestCase):

    def setUp(self):
        _count(SPEC, 1, AN, 5)

    def test_command_defaults_to_previous_quarter(self):
        out = StringIO()
        call_command('snapshot_monthly_views', stdout=out)
        year, month = service.previous_quarter()
        self.assertIn(service.period_label(year, month), out.getvalue())
        self.assertTrue(PageViewMonthlySnapshot.objects.filter(year=year, month=month).exists())

    def test_command_explicit_period_and_dry_run(self):
        out = StringIO()
        call_command('snapshot_monthly_views', '--year', '2027', '--month', '6', '--dry-run', stdout=out)
        self.assertIn('2027 Q2', out.getvalue())
        self.assertFalse(PageViewMonthlySnapshot.objects.exists())

    def test_task_archives_previous_quarter_once(self):
        result = snapshot_page_views_task()
        self.assertEqual(result['views'], 5)
        _count(SPEC, 2, AN, 3)
        self.assertIn('skipped', snapshot_page_views_task())            # duplicate Beat run
        self.assertEqual(service.current_totals(), (1, 3))


class PageViewsPageTests(TestCase):

    def setUp(self):
        self.staff = User.objects.create_user(username='staff', email='staff@example.com', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        self.species = Species.objects.create(name='Betta macrostoma', category='ANA', global_region='SEA')
        _count(SPEC, self.species.id, AN, 5)
        _count(SPEC, self.species.id, AU, 2)
        _count(SPEC, 99999, AN, 1)
        _count(CLUB, 7, AU, 4)
        self.url = reverse('pageviewsTopRanking')

    def test_page_shows_split_columns_and_current_label(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Betta macrostoma')
        self.assertContains(response, '(deleted #99999)')
        self.assertContains(response, 'since tracking began or the last Clear')
        self.assertEqual(response.context['results'][0]['authenticated'], 2)
        self.assertEqual(response.context['limit'], '100')

    def test_limit_choices(self):
        self.assertEqual(len(self.client.get(self.url, {'limit': '50'}).context['results']), 2)
        self.assertEqual(self.client.get(self.url, {'limit': 'bogus'}).context['limit'], '100')
        self.assertEqual(len(self.client.get(self.url, {'limit': 'all'}).context['results']), 2)

    def test_snapshot_source_shows_quarter_and_old_monthly_links_work(self):
        service.close_out_period(2027, 3)
        response = self.client.get(self.url, {'source': 'snapshot'})
        self.assertContains(response, 'Showing archived period 2027 Q1')
        self.assertEqual(response.context['results'][0]['total'], 7)
        self.assertEqual(self.client.get(self.url, {'source': 'monthly'}).context['source'], 'snapshot')
        self.assertContains(self.client.get(self.url), 'since the last close-out (2027 Q1)')

    def test_csv_export_current_single_and_all_types(self):
        response = self.client.get(reverse('pageviewsExportCsv'), {'page_type': SPEC})
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('pageviews_current_SPEC.csv', response['Content-Disposition'])
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(rows[0], ['period', 'page_type', 'page_type_label', 'object_id', 'name', 'url',
                                   'anonymous', 'authenticated', 'total'])
        self.assertEqual(rows[1][:5], ['current', 'SPEC', 'Species', str(self.species.id), 'Betta macrostoma'])
        self.assertTrue(rows[1][5].startswith('http://testserver/'))
        self.assertEqual(rows[1][6:], ['5', '2', '7'])
        everything = list(csv.reader(io.StringIO(self.client.get(reverse('pageviewsExportCsv'), {'page_type': 'all'}).content.decode())))
        self.assertEqual({row[1] for row in everything[1:]}, {'SPEC', 'AQCL'})

    def test_csv_export_snapshot(self):
        service.close_out_period(2027, 3)
        response = self.client.get(reverse('pageviewsExportCsv'), {'page_type': 'all', 'source': 'snapshot', 'year': 2027, 'month': 3})
        self.assertIn('pageviews_2027-Q1_all.csv', response['Content-Disposition'])
        self.assertIn('2027 Q1', response.content.decode())

    def test_close_out_needs_confirm_and_allowed_period(self):
        year, month = service.previous_quarter()
        self.client.post(reverse('pageviewsCloseOut'), {'period': f'{year}-{month}'})
        self.client.post(reverse('pageviewsCloseOut'), {'period': '1999-3', 'confirm': 'on'})
        self.assertFalse(PageViewMonthlySnapshot.objects.exists())
        response = self.client.post(reverse('pageviewsCloseOut'), {'period': f'{year}-{month}', 'confirm': 'on'})
        self.assertRedirects(response, f'{self.url}?source=snapshot&year={year}&month={month}', fetch_redirect_response=False)
        self.assertEqual(service.current_totals(), (0, 0))

    def test_clear_needs_typed_confirmation(self):
        self.client.post(reverse('pageviewsClear'), {'confirm_text': 'yes'})
        self.assertTrue(PageViewCount.objects.exists())
        self.client.post(reverse('pageviewsClear'), {'confirm_text': 'clear'})
        self.assertFalse(PageViewCount.objects.exists())

    def test_staff_only_and_post_only(self):
        self.assertEqual(self.client.get(reverse('pageviewsClear')).status_code, 405)
        plain = User.objects.create_user(username='plain', email='plain@example.com', password='pw')
        self.client.force_login(plain)
        for name in ('pageviewsTopRanking', 'pageviewsExportCsv'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)    # to admin login
        self.client.post(reverse('pageviewsClear'), {'confirm_text': 'CLEAR'})
        self.assertTrue(PageViewCount.objects.exists())
