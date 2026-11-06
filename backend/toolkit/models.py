import re
from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

SCENARIOS = {
    "healthy": "Healthy API", "server_error": "Intermittent 500", "rate_limit": "Rate limit (429)",
    "expired_auth": "Expired credentials", "malformed": "Malformed JSON", "incomplete": "Incomplete record",
    "pagination": "Repeated cursor", "duplicates": "Duplicate records", "timeout": "Network timeout",
    "slow": "Slow pages / interruption",
}

class Mapping(BaseModel):
    id: str = "id"
    name: str = "name"
    status: str = "status"
    amount: str = "amount"
    updated_at: str = "updated_at"

    @model_validator(mode="after")
    def paths(self):
        for path in self.model_dump().values():
            if not re.fullmatch(r"[A-Za-z_][\w]*(\.[A-Za-z_][\w]*)*", path) or len(path) > 120:
                raise ValueError("Use dotted field paths, such as customer.name")
        return self

class Config(BaseModel):
    name: str = Field(default="Demo orders", min_length=1, max_length=80)
    source: Literal["demo", "custom"] = "demo"
    url: str = Field(default="", max_length=2048)
    auth: Literal["none", "bearer", "api_key"] = "none"
    pagination: Literal["cursor", "page", "offset"] = "cursor"
    items_path: str = Field(default="items", pattern=r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$", max_length=120)
    cursor_path: str = Field(default="next_cursor", pattern=r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$", max_length=120)
    more_path: str = Field(default="has_more", pattern=r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$", max_length=120)
    page_size: int = Field(default=5, ge=1, le=100)
    max_pages: int = Field(default=100, ge=1, le=1000)
    timeout: float = Field(default=2, ge=0.1, le=30)
    retries: int = Field(default=3, ge=0, le=5)
    incremental: bool = True
    mapping: Mapping = Field(default_factory=Mapping)

class SaveConfig(BaseModel):
    config: Config
    credential: Optional[str] = Field(default=None, max_length=4096)

class RunInput(BaseModel):
    scenario: str = "healthy"
    full: bool = False

    @model_validator(mode="after")
    def valid_scenario(self):
        if self.scenario not in SCENARIOS:
            raise ValueError("Unknown demonstration scenario")
        return self

class IntegrationError(Exception):
    def __init__(self, code: str, message: str, hint: str):
        super().__init__(message)
        self.code, self.message, self.hint = code, message, hint

def get_path(value, path):
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise IntegrationError("schema", "A required field is missing.", "Check field mapping and the response envelope. No records from this page were committed.")
        value = value[key]
    return value

def normalize(raw, mapping: Mapping):
    import math
    data = {key: get_path(raw, path) for key, path in mapping.model_dump().items()}
    for key in ("id", "name", "status"):
        if isinstance(data[key], bool) or not isinstance(data[key], (str, int)) or not str(data[key]).strip():
            raise IntegrationError("schema", "A record contains an invalid identity or text field.", "Map id, name and status to non-empty scalar values.")
        data[key] = str(data[key]).strip()
        if len(data[key]) > 500:
            raise IntegrationError("schema", "A mapped text field exceeds 500 characters.", "Choose a compact identity and display fields.")
        if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF or ord(char) in (0xFFFE, 0xFFFF) for char in data[key]):
            raise IntegrationError("schema", "A mapped field contains unsupported control characters.", "Normalize source text before importing it.")
    data["status"] = data["status"].lower()
    try:
        if isinstance(data["amount"], bool):
            raise ValueError()
        data["amount"] = round(float(data["amount"]), 2)
        if not math.isfinite(data["amount"]):
            raise ValueError()
        parsed = datetime.fromisoformat(str(data["updated_at"]).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        data["updated_at"] = parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        raise IntegrationError("schema", "A record has an invalid amount or timestamp.", "Use a finite number and an ISO 8601 timestamp with a timezone.")
    return data
