"""帆布浸渍防水台业务规则。"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from .models import ClothRoll, DipRun, HygrometerSticker, Loft

MIN_CURE_HOURS_FOR_CURED = Decimal("12")


def latest_dip_run(roll: ClothRoll) -> DipRun | None:
    return roll.dip_runs.order_by("-started_at", "-id").first()


def can_mark_roll_cured(roll: ClothRoll) -> tuple[bool, str]:
    """
    布卷转为「已固化」(cured) 的前提：
    最近一条浸渍记录的固化时长已记录，且 >= 12 小时。
    """
    latest = latest_dip_run(roll)
    if latest is None:
        return False, "该布卷尚无浸渍记录，不能标记为已固化"
    if latest.cure_hours is None:
        return False, "最近浸渍记录尚未填写固化时长，不能标记为已固化"
    if latest.cure_hours < MIN_CURE_HOURS_FOR_CURED:
        return (
            False,
            f"最近浸渍固化时长 {latest.cure_hours} 小时低于 {MIN_CURE_HOURS_FOR_CURED} 小时，不能标记为已固化",
        )
    return True, ""


def current_sticker(loft: Loft) -> HygrometerSticker | None:
    """该帆布间现行（未作废）的湿度计止日贴纸，没有则 None。"""
    return loft.hygrometer_stickers.filter(voided_at__isnull=True).first()


def cure_hours_block_message(loft: Loft, today=None) -> str | None:
    """
    给浸渍补写/改写固化时长前的贴纸检查：
    无现行贴纸、或止日已过（止日当天仍有效）时返回中文拦截语，否则返回 None。
    贴纸只把关「写时长」，不替代「标已固化需满 12 小时」的时长规则。
    """
    sticker = current_sticker(loft)
    if sticker is None:
        return f"帆布间「{loft.name}」尚未粘贴湿度计止日贴纸，禁止填写固化时长"
    if today is None:
        today = timezone.localdate()
    if sticker.stop_date < today:
        return (
            f"帆布间「{loft.name}」湿度计止日贴纸已过止日"
            f"（{sticker.stop_date.isoformat()}），禁止补写或改写固化时长"
        )
    return None
