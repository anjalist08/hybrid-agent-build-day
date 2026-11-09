"""Shared Pydantic models: what the vision model extracts, and what a query returns.

The UI schema is the "generative UI" contract with the iOS app. It is deliberately flat
(one component type with optional fields, no recursion) so it works with structured
outputs and decodes trivially in Swift. Keep it in sync with ios/Lens/App/GenUI.swift.
"""

from typing import Literal

from pydantic import BaseModel, Field

# ---------- Screen extraction ----------


class VisibleItem(BaseModel):
    kind: Literal["post", "video", "article", "search", "profile", "other"]
    title: str = Field(description="Video title, article headline, search query, or first line of a post")
    author: str | None = Field(description="Account handle, channel, or byline if visible")
    url: str | None = Field(description="URL only if literally visible on screen")
    topics: list[str] = Field(description="1-4 short lowercase topic tags, e.g. 'ai agents', 'f1'")
    summary: str = Field(description="One sentence on what this item is about")


class FrameObservation(BaseModel):
    app: str = Field(description="App or site in view, e.g. 'X', 'YouTube', 'Safari', 'Medium', 'Chrome'")
    screen_kind: Literal["feed", "detail", "search", "profile", "other"]
    sensitive: bool = Field(description="True for banking, passwords, private messages, health, or other private screens")
    items: list[VisibleItem]


# ---------- Generative UI ----------

ComponentType = Literal[
    "header",      # title + optional subtitle
    "text",        # body paragraph
    "card",        # title, subtitle, body, optional url
    "list",        # items[]
    "timeline",    # items[] ordered by time; item.meta holds the time label
    "person",      # title = name/handle, subtitle = platform, body = why they matter, items = their content
    "chips",       # items[] rendered as tags (item.title only)
    "bar_chart",   # bars[]
    "link_button", # title + url
]


class UIItem(BaseModel):
    title: str
    subtitle: str | None = None
    meta: str | None = None
    url: str | None = None


class UIBar(BaseModel):
    label: str
    value: float


class UIComponent(BaseModel):
    type: ComponentType
    title: str | None = None
    subtitle: str | None = None
    body: str | None = None
    url: str | None = None
    items: list[UIItem] | None = None
    bars: list[UIBar] | None = None


class UIScreen(BaseModel):
    title: str
    components: list[UIComponent]


class Action(BaseModel):
    kind: Literal["none", "open_url"]
    url: str | None = None


class LensAnswer(BaseModel):
    speech: str = Field(description="1-3 short conversational sentences to be read aloud")
    ui: UIScreen
    action: Action


class QueryRequest(BaseModel):
    text: str
    # Where the transcript came from, for the routing panel ("device-stt", "siri", "typed").
    source: str = "typed"


class QueryResponse(BaseModel):
    answer: LensAnswer
    route: dict
