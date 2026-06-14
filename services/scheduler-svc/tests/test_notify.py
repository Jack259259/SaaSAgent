"""通知:白名单模板渲染、非白名单拒、频控、webhook 未配置 NOT_CONFIGURED。"""

from __future__ import annotations

from pathlib import Path

import pytest

from contracts import UserCtx
from scheduler_svc import (
    ConsoleChannel,
    NotifyService,
    RateLimiter,
    TemplateStore,
    WebhookChannel,
)
from scheduler_svc.notify import (
    ChannelNotConfiguredError,
    RateLimitedError,
    TemplateNotFoundError,
)

_TEMPLATES = Path(__file__).parents[3] / "assets" / "notify-templates"


def _uc() -> UserCtx:
    return UserCtx(
        tenant_id="t1", user_id="u1", roles=["analyst"], data_scope={}, permissions=["*"]
    )


def _params() -> dict[str, str]:
    return {"report_name": "月报", "period": "2026-05"}


def test_whitelist_template_renders() -> None:
    channel = ConsoleChannel()
    svc = NotifyService(channel=channel, templates=TemplateStore(_TEMPLATES))
    assert svc.send(_uc(), template_id="report-ready", channel="inapp", params=_params())
    assert channel.sent and "月报" in channel.sent[0][2]  # 渲染了参数


def test_non_whitelist_template_rejected() -> None:
    svc = NotifyService(templates=TemplateStore(_TEMPLATES))
    with pytest.raises(TemplateNotFoundError):
        svc.send(_uc(), template_id="evil-template", channel="inapp", params={})


def test_rate_limit_triggers() -> None:
    svc = NotifyService(
        channel=ConsoleChannel(),
        templates=TemplateStore(_TEMPLATES),
        rate_limiter=RateLimiter(per_hour=2),
    )
    uc = _uc()
    svc.send(uc, template_id="report-ready", channel="inapp", params=_params())
    svc.send(uc, template_id="report-ready", channel="inapp", params=_params())
    with pytest.raises(RateLimitedError):
        svc.send(uc, template_id="report-ready", channel="inapp", params=_params())


def test_webhook_not_configured() -> None:
    with pytest.raises(ChannelNotConfiguredError):
        WebhookChannel(url="").send(channel="im", recipient="u1", body="hi")
