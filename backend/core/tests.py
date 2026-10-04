import threading
from datetime import timedelta
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import ClothRoll, DipRun, HygrometerSticker, Loft

User = get_user_model()


def make_user(username, role):
    return User.objects.create_user(username=username, password="pw123456", role=role)


class StickerGateTests(TestCase):
    """写固化时长的贴纸闸：无贴纸 / 过止日中文挡住；止日当天仍有效。"""

    def setUp(self):
        self.loft = Loft.objects.create(name="北岸帆布间")
        self.roll = ClothRoll.objects.create(
            loft=self.loft, roll_code="R-01", status=ClothRoll.STATUS_DIPPING
        )
        self.admin = make_user("admin1", User.ROLE_ADMIN)
        self.worker = make_user("worker1", User.ROLE_WORKER)
        self.client = APIClient()
        self.client.force_authenticate(self.worker)
        self.today = timezone.localdate()

    def _stick(self, stop_date):
        return HygrometerSticker.objects.create(
            loft=self.loft,
            instrument_no="HYG-01",
            stop_date=stop_date,
            pasted_by=self.admin,
        )

    def _dip_payload(self, **over):
        payload = {
            "rollId": self.roll.pk,
            "startedAt": timezone.now().isoformat(),
            "resinPct": "28.50",
            "cureHours": None,
            "notes": "",
        }
        payload.update(over)
        return payload

    def test_no_sticker_blocks_writing_hours(self):
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours="13.00"), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("尚未粘贴湿度计止日贴纸", resp.data["cureHours"][0])

    def test_expired_sticker_blocks_writing_hours(self):
        self._stick(self.today - timedelta(days=1))
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours="13.00"), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("已过止日", resp.data["cureHours"][0])

    def test_stop_date_day_itself_still_valid(self):
        self._stick(self.today)
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours="13.00"), format="json")
        self.assertEqual(resp.status_code, 201)

    def test_future_stop_date_allows_writing_hours(self):
        self._stick(self.today + timedelta(days=7))
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours="13.00"), format="json")
        self.assertEqual(resp.status_code, 201)

    def test_new_dip_with_empty_hours_skips_sticker_check(self):
        # 无贴纸也不拦：登记新浸渍且时长留空
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours=None), format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.data["cureHours"])

    def test_patch_backfill_hours_blocked_when_expired(self):
        self._stick(self.today + timedelta(days=1))
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours=None), format="json")
        dip_id = resp.data["id"]
        sticker = HygrometerSticker.objects.get(pk=self.loft.hygrometer_stickers.first().pk)
        sticker.stop_date = self.today - timedelta(days=1)
        sticker.save()
        resp = self.client.patch(f"/api/dips/{dip_id}/", {"cureHours": "13.00"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("已过止日", resp.data["cureHours"][0])

    def test_patch_rewrite_hours_blocked_without_sticker(self):
        self._stick(self.today + timedelta(days=1))
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours="13.00"), format="json")
        dip_id = resp.data["id"]
        HygrometerSticker.objects.all().delete()
        resp = self.client.patch(f"/api/dips/{dip_id}/", {"cureHours": "14.00"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("尚未粘贴湿度计止日贴纸", resp.data["cureHours"][0])

    def test_patch_hours_allowed_when_sticker_valid(self):
        self._stick(self.today + timedelta(days=1))
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours=None), format="json")
        dip_id = resp.data["id"]
        resp = self.client.patch(f"/api/dips/{dip_id}/", {"cureHours": "12.50"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["cureHours"], "12.50")

    def test_patch_notes_only_not_blocked_by_expired_sticker(self):
        self._stick(self.today + timedelta(days=1))
        resp = self.client.post("/api/dips/", self._dip_payload(cureHours="13.00"), format="json")
        dip_id = resp.data["id"]
        sticker = HygrometerSticker.objects.get()
        sticker.stop_date = self.today - timedelta(days=2)
        sticker.save()
        resp = self.client.patch(f"/api/dips/{dip_id}/", {"notes": "仅改备注"}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_mark_cured_still_requires_12h_even_with_valid_sticker(self):
        # 贴纸不替代时长：有效贴纸 + 时长 4h，仍不可标已固化
        self._stick(self.today + timedelta(days=1))
        self.client.post("/api/dips/", self._dip_payload(cureHours="4.00"), format="json")
        resp = self.client.patch(f"/api/rolls/{self.roll.pk}/", {"status": "cured"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("12", resp.data["status"][0])

    def test_mark_cured_ok_with_12h_and_valid_sticker(self):
        self._stick(self.today + timedelta(days=1))
        self.client.post("/api/dips/", self._dip_payload(cureHours="12.00"), format="json")
        resp = self.client.patch(f"/api/rolls/{self.roll.pk}/", {"status": "cured"}, format="json")
        self.assertEqual(resp.status_code, 200)


class StickerAdminTests(TestCase):
    """贴纸的粘贴 / 续期 / 作废权限与现行唯一性。"""

    def setUp(self):
        self.loft = Loft.objects.create(name="东仓帆布间")
        self.admin = make_user("admin2", User.ROLE_ADMIN)
        self.worker = make_user("worker2", User.ROLE_WORKER)
        self.today = timezone.localdate()

    def _as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _paste(self, client, **over):
        payload = {
            "loftId": self.loft.pk,
            "instrumentNo": "HYG-02",
            "stopDate": (self.today + timedelta(days=30)).isoformat(),
        }
        payload.update(over)
        return client.post("/api/stickers/", payload, format="json")

    def test_worker_cannot_paste_renew_void(self):
        worker = self._as(self.worker)
        resp = self._paste(worker)
        self.assertEqual(resp.status_code, 403)
        self.assertIn("仅管理员", resp.data["detail"])

        sticker = HygrometerSticker.objects.create(
            loft=self.loft, instrument_no="HYG-02",
            stop_date=self.today + timedelta(days=30), pasted_by=self.admin,
        )
        resp = worker.post(
            f"/api/stickers/{sticker.pk}/renew/",
            {"stopDate": (self.today + timedelta(days=60)).isoformat()},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
        resp = worker.post(f"/api/stickers/{sticker.pk}/void/")
        self.assertEqual(resp.status_code, 403)

    def test_worker_can_read_stickers_and_write_hours(self):
        HygrometerSticker.objects.create(
            loft=self.loft, instrument_no="HYG-02",
            stop_date=self.today + timedelta(days=30), pasted_by=self.admin,
        )
        worker = self._as(self.worker)
        self.assertEqual(worker.get("/api/stickers/").status_code, 200)
        roll = ClothRoll.objects.create(loft=self.loft, roll_code="R-09")
        resp = worker.post(
            "/api/dips/",
            {
                "rollId": roll.pk,
                "startedAt": timezone.now().isoformat(),
                "resinPct": "27.00",
                "cureHours": "13.00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)

    def test_admin_paste_records_paster(self):
        resp = self._paste(self._as(self.admin))
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["pastedBy"], "admin2")
        self.assertTrue(resp.data["isCurrent"])
        self.assertFalse(resp.data["isExpired"])

    def test_paste_rejected_when_current_exists(self):
        admin = self._as(self.admin)
        self.assertEqual(self._paste(admin).status_code, 201)
        resp = self._paste(admin, instrumentNo="HYG-03")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("已有现行贴纸", resp.data["detail"])
        self.assertEqual(
            HygrometerSticker.objects.filter(loft=self.loft, voided_at__isnull=True).count(), 1
        )

    def test_db_rejects_second_current_sticker(self):
        HygrometerSticker.objects.create(
            loft=self.loft, instrument_no="HYG-02",
            stop_date=self.today, pasted_by=self.admin,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                HygrometerSticker.objects.create(
                    loft=self.loft, instrument_no="HYG-99",
                    stop_date=self.today, pasted_by=self.admin,
                )

    def test_renew_updates_stop_date_in_place(self):
        admin = self._as(self.admin)
        sticker_id = self._paste(admin).data["id"]
        new_date = (self.today + timedelta(days=90)).isoformat()
        resp = admin.post(
            f"/api/stickers/{sticker_id}/renew/",
            {"stopDate": new_date, "instrumentNo": "HYG-08"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], sticker_id)
        self.assertEqual(resp.data["stopDate"], new_date)
        self.assertEqual(resp.data["instrumentNo"], "HYG-08")
        # 库里只留一版：同一行更新，不产生新贴纸
        self.assertEqual(HygrometerSticker.objects.filter(loft=self.loft).count(), 1)

    def test_renew_requires_stop_date(self):
        admin = self._as(self.admin)
        sticker_id = self._paste(admin).data["id"]
        resp = admin.post(f"/api/stickers/{sticker_id}/renew/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("stopDate", resp.data)

    def test_renew_voided_sticker_rejected(self):
        admin = self._as(self.admin)
        sticker_id = self._paste(admin).data["id"]
        admin.post(f"/api/stickers/{sticker_id}/void/")
        resp = admin.post(
            f"/api/stickers/{sticker_id}/renew/",
            {"stopDate": (self.today + timedelta(days=10)).isoformat()},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("已作废", resp.data["detail"])

    def test_void_then_hours_blocked_and_repaste_allowed(self):
        admin = self._as(self.admin)
        sticker_id = self._paste(admin).data["id"]
        resp = admin.post(f"/api/stickers/{sticker_id}/void/")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.data["voidedAt"])
        self.assertFalse(resp.data["isCurrent"])

        # 作废后该间无现行贴纸，写时长被中文挡住
        roll = ClothRoll.objects.create(loft=self.loft, roll_code="R-10")
        resp = admin.post(
            "/api/dips/",
            {
                "rollId": roll.pk,
                "startedAt": timezone.now().isoformat(),
                "resinPct": "27.00",
                "cureHours": "13.00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("尚未粘贴湿度计止日贴纸", resp.data["cureHours"][0])

        # 作废后可重新粘贴
        self.assertEqual(self._paste(admin, instrumentNo="HYG-05").status_code, 201)
        self.assertEqual(
            HygrometerSticker.objects.filter(loft=self.loft, voided_at__isnull=True).count(), 1
        )

    def test_void_twice_rejected(self):
        admin = self._as(self.admin)
        sticker_id = self._paste(admin).data["id"]
        admin.post(f"/api/stickers/{sticker_id}/void/")
        resp = admin.post(f"/api/stickers/{sticker_id}/void/")
        self.assertEqual(resp.status_code, 400)


class StickerConcurrencyTests(TestCase):
    """交叉改同一间现行止日：无论顺序还是并发，库里只留一版。"""

    def setUp(self):
        self.loft = Loft.objects.create(name="并发帆布间")
        self.admin_a = make_user("meter_a", User.ROLE_ADMIN)
        self.admin_b = make_user("meter_b", User.ROLE_ADMIN)
        self.sticker = HygrometerSticker.objects.create(
            loft=self.loft,
            instrument_no="HYG-01",
            stop_date=timezone.localdate() + timedelta(days=10),
            pasted_by=self.admin_a,
        )

    def _renew(self, user, sticker_pk, stop_date):
        client = APIClient()
        client.force_authenticate(user)
        return client.post(
            f"/api/stickers/{sticker_pk}/renew/", {"stopDate": stop_date}, format="json"
        )

    def test_sequential_cross_renew_leaves_single_version(self):
        date_a = (timezone.localdate() + timedelta(days=40)).isoformat()
        date_b = (timezone.localdate() + timedelta(days=80)).isoformat()
        self.assertEqual(self._renew(self.admin_a, self.sticker.pk, date_a).status_code, 200)
        self.assertEqual(self._renew(self.admin_b, self.sticker.pk, date_b).status_code, 200)
        # 只留一版：该间全表仅一行，现行恰好一张，止日为后写者
        self.assertEqual(HygrometerSticker.objects.filter(loft=self.loft).count(), 1)
        current = HygrometerSticker.objects.filter(loft=self.loft, voided_at__isnull=True)
        self.assertEqual(current.count(), 1)
        self.assertEqual(current.first().stop_date.isoformat(), date_b)


@skipUnless(
    connection.features.has_select_for_update,
    "需要支持行级锁的数据库（如 PostgreSQL）来串行化并发续期",
)
class StickerThreadedConcurrencyTests(TransactionTestCase):
    """两名仪表工真正同时提交续期：行锁串行化后库里只留一版。"""

    def setUp(self):
        self.loft = Loft.objects.create(name="并发帆布间")
        self.admin_a = make_user("meter_a", User.ROLE_ADMIN)
        self.admin_b = make_user("meter_b", User.ROLE_ADMIN)
        self.sticker = HygrometerSticker.objects.create(
            loft=self.loft,
            instrument_no="HYG-01",
            stop_date=timezone.localdate() + timedelta(days=10),
            pasted_by=self.admin_a,
        )

    def test_cross_renew_leaves_single_version(self):
        date_a = (timezone.localdate() + timedelta(days=40)).isoformat()
        date_b = (timezone.localdate() + timedelta(days=80)).isoformat()
        outcomes = []

        def renew(user, stop_date):
            try:
                client = APIClient()
                client.force_authenticate(user)
                resp = client.post(
                    f"/api/stickers/{self.sticker.pk}/renew/",
                    {"stopDate": stop_date},
                    format="json",
                )
                outcomes.append(resp.status_code)
            finally:
                connections.close_all()

        t1 = threading.Thread(target=renew, args=(self.admin_a, date_a))
        t2 = threading.Thread(target=renew, args=(self.admin_b, date_b))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(sorted(outcomes), [200, 200])
        # 只留一版：全表该间只有这一张贴纸，且现行恰好一张
        self.assertEqual(HygrometerSticker.objects.filter(loft=self.loft).count(), 1)
        current = HygrometerSticker.objects.filter(loft=self.loft, voided_at__isnull=True)
        self.assertEqual(current.count(), 1)
        self.assertIn(current.first().stop_date.isoformat(), {date_a, date_b})


class SeedDataTests(TestCase):
    def test_seed_expired_sticker_and_open_dip_idempotent(self):
        call_command("seed_data")
        loft = Loft.objects.order_by("id").first()
        self.assertIsNotNone(loft)

        # 一间浸渍中卷、最近浸渍时长仍空
        dipping = loft.rolls.get(status=ClothRoll.STATUS_DIPPING)
        latest = dipping.dip_runs.order_by("-started_at", "-id").first()
        self.assertIsNone(latest.cure_hours)

        # 现行贴纸止日为昨天（已过期）
        sticker = loft.hygrometer_stickers.get(voided_at__isnull=True)
        self.assertEqual(sticker.stop_date, timezone.localdate() - timedelta(days=1))

        # 再跑一遍不重复贴
        call_command("seed_data")
        self.assertEqual(
            loft.hygrometer_stickers.filter(voided_at__isnull=True).count(), 1
        )
