"""[1] Storyboard Generator — 把主題/大綱拆成結構化分鏡 JSON。

README 指定 LLM 擇一(OpenAI 或 Anthropic)。這裡預設 Anthropic,
用 Messages API 的 structured outputs(output_config.format)強制輸出合法 JSON。
dry-run 模式不呼叫 API,直接產生一份可用的假分鏡,好驗證後續資料流。
"""

from __future__ import annotations

from .config import Config
from .models import CostEntry, Shot, Storyboard

# Anthropic Opus 4.8 每 1M token 定價(input $5 / output $25),用於粗估成本。
_ANTHROPIC_INPUT_PER_TOKEN = 5.0 / 1_000_000
_ANTHROPIC_OUTPUT_PER_TOKEN = 25.0 / 1_000_000

_SYSTEM = (
    "你是短影音分鏡師。把使用者給的主題拆成一連串分鏡,"
    "每個分鏡要能直接餵給文生圖模型。畫面描述具體、有畫面感,"
    "並標記鏡頭類型與是否需要動態。輸出繁體中文。"
)

# structured outputs 的 JSON schema。注意:不使用 minItems/maxLength 這類
# 不被支援的約束,改在 prompt 說明數量。
_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "shot_type": {
                        "type": "string",
                        "enum": ["wide", "medium", "close"],
                    },
                    "needs_motion": {"type": "boolean"},
                    "duration": {"type": "number"},
                    "motion_hint": {"type": "string"},
                },
                "required": [
                    "description",
                    "shot_type",
                    "needs_motion",
                    "duration",
                    "motion_hint",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "shots"],
    "additionalProperties": False,
}


def generate_storyboard(
    prompt: str,
    cfg: Config,
    costs: list[CostEntry],
    num_shots: int = 3,
) -> Storyboard:
    """產生分鏡。會把成本紀錄 append 進 `costs`。"""
    if cfg.dry_run:
        return _dry_run_storyboard(prompt, num_shots, costs)

    if cfg.llm_provider != "anthropic":
        raise NotImplementedError(
            f"目前只實作 anthropic 分鏡 Provider(收到 {cfg.llm_provider!r})。"
            " OpenAI 版留待擴充。"
        )
    return _anthropic_storyboard(prompt, cfg, costs, num_shots)


def _anthropic_storyboard(
    prompt: str, cfg: Config, costs: list[CostEntry], num_shots: int
) -> Storyboard:
    import json

    try:
        import anthropic
    except ImportError as exc:  # noqa: TRY003
        raise RuntimeError(
            "需要 anthropic 套件才能呼叫分鏡 LLM:pip install anthropic"
            "(或改用 --dry-run)。"
        ) from exc

    if not cfg.anthropic_api_key:
        raise RuntimeError("未設定 ANTHROPIC_API_KEY(或改用 --dry-run)。")

    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
    user_msg = (
        f"主題/大綱:{prompt}\n\n"
        f"請拆成剛好 {num_shots} 個分鏡,總長度適合直式短影音(15~40 秒)。"
    )
    resp = client.messages.create(
        model=cfg.llm_model,
        max_tokens=8000,
        system=_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[{"role": "user", "content": user_msg}],
    )

    text = next((b.text for b in resp.content if b.type == "text"), "")
    data = json.loads(text)

    usage = resp.usage
    cost = (
        usage.input_tokens * _ANTHROPIC_INPUT_PER_TOKEN
        + usage.output_tokens * _ANTHROPIC_OUTPUT_PER_TOKEN
    )
    costs.append(
        CostEntry(
            stage="storyboard",
            provider=f"anthropic/{cfg.llm_model}",
            unit_cost_usd=round(cost, 6),
            detail=f"in={usage.input_tokens} out={usage.output_tokens} tokens",
        )
    )
    return _build(prompt, data)


def _build(prompt: str, data: dict) -> Storyboard:
    shots = [
        Shot.from_dict(s, index=i)
        for i, s in enumerate(data.get("shots", []))
    ]
    return Storyboard(
        prompt=prompt,
        title=str(data.get("title", "未命名")).strip() or "未命名",
        shots=shots,
    )


def _dry_run_storyboard(
    prompt: str, num_shots: int, costs: list[CostEntry]
) -> Storyboard:
    """離線假分鏡:不花錢、不連網,純粹驗證資料流是否跑得通。"""
    costs.append(
        CostEntry(
            stage="storyboard",
            provider="dry-run",
            unit_cost_usd=0.0,
            detail="離線假分鏡",
        )
    )
    shots = [
        Shot(
            index=i,
            description=f"{prompt} — 分鏡 {i + 1}",
            shot_type=["wide", "medium", "close"][i % 3],
            needs_motion=True,
            duration=5.0,
            motion_hint="緩慢推近",
        )
        for i in range(num_shots)
    ]
    return Storyboard(prompt=prompt, title=f"[dry-run] {prompt}"[:60], shots=shots)
