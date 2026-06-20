"""
離線輕量化自主檢查規則引擎。

在零網路環境下，手機端可本地執行相同邏輯（前端需鏡像此規則）。
"""

from __future__ import annotations

from typing import Any

from backend.offline_schemas import OfflineRuleEngineResult, OfflineSelfCheckForm


def evaluate_offline_rule_engine(
    crop_name: str,
    self_check: OfflineSelfCheckForm | dict[str, Any],
) -> dict[str, Any]:
    """
    依作物與自主檢查表單，產出離線初步急救建議。

    回傳 dict 以便 JSON 序列化；結構同 OfflineRuleEngineResult。
    """
    if isinstance(self_check, dict):
        check = OfflineSelfCheckForm.model_validate(self_check)
    else:
        check = self_check

    crop = (crop_name or "").strip()
    lower = crop.lower()
    matched: list[str] = []
    result = OfflineRuleEngineResult(
        preliminary_suggestion="外觀特徵不夠典型，請等待連網後 AI 的精準診斷。",
        emergency_action="巡視周邊區域，隔離病灶株，避免盲目噴灑不明藥劑。",
    )

    # --- 番茄 ---
    if "番茄" in crop or "tomato" in lower:
        if check.has_water_soaked_spots and check.affected_part == "leaves":
            matched.append("tomato_water_soaked_leaves")
            result.preliminary_suggestion = (
                "【離線預警】高度疑似真菌性病害（如番茄晚疫病或露菌病）。"
            )
            result.emergency_action = (
                "緊急處置：請立刻剪除受害嚴重葉片並移出設施銷毀。"
                "暫停任何修剪作業，注意排水，切勿讓葉片持續淋雨。"
            )
            if check.after_rain:
                matched.append("tomato_after_rain")
                result.preliminary_suggestion += "（症狀於下雨後出現，與晚疫病高度吻合。）"

        if check.has_white_powder and check.affected_part == "leaves":
            matched.append("tomato_white_powder")
            result.preliminary_suggestion = "【離線預警】疑似白粉病。"
            result.emergency_action = "加強通風、降低葉面濕度，避免過量氮肥。"

    # --- 草莓 ---
    elif "草莓" in crop or "strawberry" in lower:
        if check.has_webbing and check.affected_part == "leaves":
            matched.append("strawberry_spider_mite")
            result.preliminary_suggestion = "【離線預警】高度疑似二點葉蟎（紅蜘蛛）危害。"
            result.emergency_action = (
                "緊急處置：環境乾燥時，可利用清水高壓噴霧沖洗葉背，"
                "物理性降低害蟲密度；避免烈日下施用高濃度化學藥劑以免肥傷。"
            )

    # --- 柑橘 ---
    elif "柑橘" in crop or "citrus" in lower or "柳橙" in crop:
        if check.has_gummosis and check.affected_part == "stems_trunk":
            matched.append("citrus_gummosis")
            result.preliminary_suggestion = "【離線預警】疑似溃疡病或天牛危害導致流膠。"
            result.emergency_action = "檢查樹幹是否有蟲孔與木屑，清除孔內幼蟲並塗抹保護劑。"

    # --- 跨作物通用 ---
    if check.has_gummosis and check.affected_part == "stems_trunk" and not matched:
        matched.append("generic_gummosis")
        result.preliminary_suggestion = "【離線預警】疑似天牛危害或木質部潰瘍流膠病。"
        result.emergency_action = (
            "檢查樹幹基部是否有木屑或蟲孔，可物理清除孔內幼蟲，"
            "或塗抹波爾多液保護主幹傷口。"
        )

    if check.has_white_powder and not matched:
        matched.append("generic_white_powder")
        result.preliminary_suggestion = "【離線預警】疑似白粉病或粉虱分泌物。"
        result.emergency_action = "加強通風、降低濕度，隔離病株。"

    result.matched_rules = matched
    return result.model_dump()
