"""
本地 IPM 專家知識庫：結構化 Schema、別名映射、檢索引擎。

預留 Repository 介面，未來可替換為 SQL 或官方 API 對接。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Protocol

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Schema（與前端/專家系統共用）
# ---------------------------------------------------------------------------


class PreventionProtocol(BaseModel):
    """預防方式（平日保養 🟢）。"""

    cultural_control: list[str] = Field(default_factory=list, description="耕作/栽培管理")
    physical_control: list[str] = Field(default_factory=list, description="物理防治")


class TreatmentProtocol(BaseModel):
    """治療方式（緊急處置 🔴）。"""

    biological_control: list[str] = Field(default_factory=list, description="生物防治/天然資材")
    chemical_control: list[str] = Field(default_factory=list, description="安全化學防治")


# 向後相容舊名稱
PreventionStrategies = PreventionProtocol
TreatmentStrategies = TreatmentProtocol


class DiseaseManagementKnowledge(BaseModel):
    """標準化植物病蟲害整合管理 (IPM) 知識庫模型。"""

    target_id: str
    common_name: str
    scientific_name: str
    host_plants: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    prevention_strategies: PreventionProtocol
    treatment_strategies: TreatmentProtocol
    extension_links: list[str] = Field(default_factory=list)


class ManagementLookupResult(BaseModel):
    matched: bool
    match_score: float = Field(ge=0.0, le=1.0)
    match_method: str
    protocol: DiseaseManagementKnowledge


# ---------------------------------------------------------------------------
# 別名映射 + 權威 Mock 知識庫
# ---------------------------------------------------------------------------

DISEASE_ALIAS_MAP: dict[str, str] = {
    "番茄晚疫病": "tomato_late_blight",
    "晚疫病": "tomato_late_blight",
    "草莓紅蜘蛛": "strawberry_two_spotted_mite",
    "二點葉蟎": "strawberry_two_spotted_mite",
    "紅蜘蛛": "strawberry_two_spotted_mite",
    "葉蟎": "strawberry_two_spotted_mite",
    "柑橘介殼蟲": "citrus_scale_insect",
    "介殼蟲": "citrus_scale_insect",
    "吹綿介殼蟲": "citrus_scale_insect",
    "草莓天牛": "strawberry_longhorn_beetle",
    "天牛": "strawberry_longhorn_beetle",
    "健康": "healthy_plant",
    "無": "healthy_plant",
}

AGRICULTURAL_KNOWLEDGE_BASE: dict[str, DiseaseManagementKnowledge] = {
    "healthy_plant": DiseaseManagementKnowledge(
        target_id="healthy_plant",
        common_name="植物健康",
        scientific_name="N/A",
        prevention_strategies=PreventionProtocol(
            cultural_control=[
                "維持目前良好的灌溉與施肥節奏。",
                "定期清理枯枝落葉，保持田區通風。",
            ],
            physical_control=["定期檢查防蟲網是否有破損。"],
        ),
        treatment_strategies=TreatmentProtocol(
            biological_control=["可定期施用枯草桿菌等益生菌進行保護性保健。"],
            chemical_control=["目前健康，嚴禁預防性濫用化學農藥。"],
        ),
        extension_links=["https://kmweb.moa.gov.tw/"],
    ),
    "tomato_late_blight": DiseaseManagementKnowledge(
        target_id="tomato_late_blight",
        common_name="番茄晚疫病",
        scientific_name="Phytophthora infestans",
        host_plants=["番茄", "馬鈴薯"],
        aliases=["晚疫病", "番茄疫病"],
        prevention_strategies=PreventionProtocol(
            cultural_control=[
                "避免在雨前或清晨進行修剪，減少傷口感染機會。",
                "合理施用氮肥，增施鉀肥以提高植物抗病力。",
                "雨季來臨前，落實田區排水，避免土壤積水。",
            ],
            physical_control=[
                "採用設施栽培（如搭設雨遮），避免葉片直接淋雨。",
                "發現病葉、病果立刻剪除並移出田區燒毀或深埋。",
            ],
        ),
        treatment_strategies=TreatmentProtocol(
            biological_control=[
                "發病初期可連續噴灑 60%-80% 亞磷酸 1000 倍液，每 7 天一次，連續 3 次。",
                "施用枯草桿菌或保粒黴素進行生物防禦。",
            ],
            chemical_control=[
                "可參考植物保護資訊系統推薦之核准藥劑（如烯酰嗎啉、代森錳鋅等）。",
                "化學藥劑須遵守安全採收期（通常 3 至 5 天），切勿超量噴灑。",
            ],
        ),
        extension_links=[
            "https://ppis.tactri.gov.tw/",
            "https://www.tactri.gov.tw/",
        ],
    ),
    "strawberry_two_spotted_mite": DiseaseManagementKnowledge(
        target_id="strawberry_two_spotted_mite",
        common_name="二點葉蟎（草莓紅蜘蛛）",
        scientific_name="Tetranychus urticae",
        host_plants=["草莓", "番茄", "玫瑰"],
        aliases=["紅蜘蛛", "草莓紅蜘蛛"],
        prevention_strategies=PreventionProtocol(
            cultural_control=[
                "保持溫室內適當溼度，高溫乾燥易引發大流行。",
                "清除田區周邊雜草，阻斷蟎類移入宿主。",
            ],
            physical_control=[
                "定期利用高壓水柱沖洗葉背，物理性沖刷蟎體與卵粒。",
                "利用黃色或藍色黏葉板監測害蟲密度。",
            ],
        ),
        treatment_strategies=TreatmentProtocol(
            biological_control=[
                "發病初期釋放捕植蟎（如智利捕植蟎）進行生物防治。",
                "噴灑窄域油 500 倍液或印楝素，包覆蟎體使其窒息。",
            ],
            chemical_control=[
                "可選用專殺蟎劑（如依殺蟎、賜派芬等核准藥劑）。",
                "葉蟎極易抗藥，切勿連續使用同一作用機制，須交替用藥。",
            ],
        ),
        extension_links=["https://kmweb.moa.gov.tw/subject/index.php?id=38"],
    ),
    "citrus_scale_insect": DiseaseManagementKnowledge(
        target_id="citrus_scale_insect",
        common_name="柑橘介殼蟲",
        scientific_name="Coccidae / Diaspididae spp.",
        host_plants=["柑橘", "柳橙", "檸檬", "柚子"],
        aliases=["介殼蟲", "吹綿介殼蟲"],
        prevention_strategies=PreventionProtocol(
            cultural_control=[
                "冬季清園，剪除嚴重受害枝條並銷毀。",
                "合理修剪保持通風透光，避免樹勢衰弱。",
            ],
            physical_control=[
                "低虫口密度時以硬毛刷除或高壓水洗。",
                "果園懸掛黃色黏蟲板監測。",
            ],
        ),
        treatment_strategies=TreatmentProtocol(
            biological_control=[
                "保護瓢蟲、小蜂等天敵，避免廣譜殺蟲劑過度使用。",
                "可施用窄域油、礦物油或苦楝油。",
            ],
            chemical_control=[
                "虫口密度高時選用核准藥劑（如螺蟲乙酯、吡蟲啉等），依標示稀釋。",
                "開花期避免對蜜蜂有毒性藥劑；遵守安全採收期。",
            ],
        ),
        extension_links=["https://ppis.tactri.gov.tw/"],
    ),
    "strawberry_longhorn_beetle": DiseaseManagementKnowledge(
        target_id="strawberry_longhorn_beetle",
        common_name="草莓天牛",
        scientific_name="Anoplophora spp.",
        host_plants=["草莓"],
        aliases=["天牛", "蛀幹害蟲"],
        prevention_strategies=PreventionProtocol(
            cultural_control=[
                "清除園區枯枝與雜木，減少天牛產卵場所。",
                "定期檢查株基部與走莖，及早發現蛀孔或流膠。",
            ],
            physical_control=[
                "發現蛀孔可插入鐵絲刺殺幼蟲，或以黃泥封孔。",
                "成蟲期可夜間人工捕捉。",
            ],
        ),
        treatment_strategies=TreatmentProtocol(
            biological_control=["可尋求寄生蜂或線蟲等生物防治資源（依當地農會建議）。"],
            chemical_control=[
                "幼蟲期可灌注核准藥劑於蛀孔並封孔。",
                "成蟲期噴灑核准藥劑，注意安全採收期。",
            ],
        ),
        extension_links=["https://www.tactri.gov.tw/"],
    ),
}

MOCK_KNOWLEDGE: list[DiseaseManagementKnowledge] = list(AGRICULTURAL_KNOWLEDGE_BASE.values())
ALIAS_TO_TARGET = DISEASE_ALIAS_MAP

DEFAULT_PROTOCOL = DiseaseManagementKnowledge(
    target_id="generic_unknown",
    common_name="未收錄病蟲害",
    scientific_name="Unknown",
    prevention_strategies=PreventionProtocol(
        cultural_control=["加強巡田，維持通風與合理施肥灌溉。"],
        physical_control=["移除並銷毀明顯受害部位。"],
    ),
    treatment_strategies=TreatmentProtocol(
        biological_control=["優先考慮生物製劑或低毒性資材。"],
        chemical_control=[
            "請向當地農會確認最新核准藥劑、稀釋倍數與安全採收期。",
        ],
    ),
    extension_links=["https://ppis.tactri.gov.tw/"],
)

IPM_DISCLAIMER = (
    "本系統之藥劑推薦僅供參考，實際施藥請遵循台灣農業部最新公告之"
    "植物保護資訊系統規範，並嚴格遵守安全採收期。"
)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class KnowledgeBaseRepository(Protocol):
    async def get_by_target_id(self, target_id: str) -> DiseaseManagementKnowledge | None: ...
    async def list_all(self) -> list[DiseaseManagementKnowledge]: ...


class InMemoryKnowledgeBase:
    def __init__(self, entries: dict[str, DiseaseManagementKnowledge] | None = None) -> None:
        self._entries = entries or AGRICULTURAL_KNOWLEDGE_BASE

    async def get_by_target_id(self, target_id: str) -> DiseaseManagementKnowledge | None:
        return self._entries.get(target_id)

    async def list_all(self) -> list[DiseaseManagementKnowledge]:
        return list(self._entries.values())


_default_repository = InMemoryKnowledgeBase()


def set_knowledge_repository(repo: KnowledgeBaseRepository) -> None:
    global _default_repository
    _default_repository = repo


# ---------------------------------------------------------------------------
# 檢索引擎
# ---------------------------------------------------------------------------


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower().strip()
    return re.sub(r"[\s\-_/·、，。；;,.()（）\[\]【】]", "", text)


def _resolve_target_id(disease_name: str) -> tuple[str | None, str]:
    """別名映射 + 包含性模糊比對，回傳 (target_id, match_method)。"""
    clean_name = (disease_name or "").strip()
    if not clean_name:
        return None, "empty"

    if clean_name in DISEASE_ALIAS_MAP:
        return DISEASE_ALIAS_MAP[clean_name], "alias_exact"

    norm = _normalize_text(clean_name)
    for alias, target_id in DISEASE_ALIAS_MAP.items():
        alias_norm = _normalize_text(alias)
        if norm == alias_norm or alias_norm in norm or norm in alias_norm:
            return target_id, "alias_fuzzy"

    return None, "not_in_alias"


def _score_entry(entry: DiseaseManagementKnowledge, disease_name: str, plant_name: str | None) -> float:
    query = _normalize_text(disease_name)
    if not query:
        return 0.0
    candidates = [entry.common_name, entry.scientific_name, *entry.aliases, entry.target_id.replace("_", " ")]
    norm_candidates = [_normalize_text(item) for item in candidates if item]
    if query in norm_candidates:
        return 1.0
    score = 0.0
    for cand in norm_candidates:
        if query in cand or cand in query:
            score = max(score, 0.88)
    if plant_name:
        plant_norm = _normalize_text(plant_name)
        if any(plant_norm in _normalize_text(host) or _normalize_text(host) in plant_norm for host in entry.host_plants):
            score = min(1.0, score + 0.12)
    return score


async def get_management_protocol(
    disease_name: str,
    plant_name: str | None = None,
) -> ManagementLookupResult:
    """依 Gemini 確診名稱檢索 IPM 協議（async 介面）。"""
    clean = (disease_name or "").strip()
    if clean in {"無", "健康", ""}:
        healthy = await _default_repository.get_by_target_id("healthy_plant")
        return ManagementLookupResult(
            matched=True,
            match_score=1.0,
            match_method="healthy_template",
            protocol=healthy or DEFAULT_PROTOCOL,
        )

    target_id, alias_method = _resolve_target_id(clean)
    if target_id:
        protocol = await _default_repository.get_by_target_id(target_id)
        if protocol:
            return ManagementLookupResult(
                matched=True,
                match_score=1.0,
                match_method=alias_method,
                protocol=protocol,
            )

    entries = await _default_repository.list_all()
    best: DiseaseManagementKnowledge | None = None
    best_score = 0.0
    for entry in entries:
        if entry.target_id == "healthy_plant":
            continue
        score = _score_entry(entry, clean, plant_name)
        if score > best_score:
            best_score = score
            best = entry

    if best and best_score >= 0.72:
        return ManagementLookupResult(
            matched=True,
            match_score=round(best_score, 2),
            match_method="fuzzy_match",
            protocol=best,
        )

    return ManagementLookupResult(
        matched=False,
        match_score=round(best_score, 2),
        match_method="fallback_generic",
        protocol=DEFAULT_PROTOCOL,
    )


def flatten_treatment_text(protocol: DiseaseManagementKnowledge) -> str:
    items = protocol.treatment_strategies.biological_control + protocol.treatment_strategies.chemical_control
    return "；".join(items[:4]) if items else "請依當地農會建議處理。"


def flatten_prevention_text(protocol: DiseaseManagementKnowledge) -> str:
    items = protocol.prevention_strategies.cultural_control + protocol.prevention_strategies.physical_control
    return "；".join(items[:4]) if items else "維持良好栽培管理與定期巡查。"


def apply_management_to_app_result(app_result: dict[str, Any], lookup: ManagementLookupResult) -> dict[str, Any]:
    protocol = lookup.protocol
    app_result["authoritative_treatment_knowledge"] = protocol.model_dump()
    app_result["management_protocol"] = protocol.model_dump()
    app_result["management_match"] = {
        "matched": lookup.matched,
        "match_score": lookup.match_score,
        "match_method": lookup.match_method,
        "target_id": protocol.target_id,
    }
    app_result["treatment_strategies"] = protocol.treatment_strategies.model_dump()
    app_result["prevention_strategies"] = protocol.prevention_strategies.model_dump()
    app_result["extension_links"] = protocol.extension_links
    app_result["ipm_disclaimer"] = IPM_DISCLAIMER

    if lookup.matched or protocol.target_id == "healthy_plant":
        app_result["treatment"] = flatten_treatment_text(protocol)
        app_result["prevention"] = flatten_prevention_text(protocol)
        app_result["source"] = "Gemini + IPM 知識庫"
    return app_result


async def enrich_diagnosis_with_management(app_result: dict[str, Any]) -> dict[str, Any]:
    """Gemini 診斷完成後自動附加 IPM 對策。"""
    primary = app_result.get("primary_diagnosis") or app_result.get("issue_name", "")
    health_status = app_result.get("health_status", "")

    if health_status == "疑似生理障礙":
        lookup = await get_management_protocol("generic_unknown", plant_name=app_result.get("crop"))
        return apply_management_to_app_result(app_result, lookup)

    lookup = await get_management_protocol(primary, plant_name=app_result.get("crop"))
    return apply_management_to_app_result(app_result, lookup)
