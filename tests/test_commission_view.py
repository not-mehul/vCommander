"""Commission run: outcome, error handling, API-key cleanup, cancellation."""

import asyncio

import pytest
from conftest import Event

import pages.commission_view as cv
from apis.internal_api import ExternalApiKey
from utils import session


class FakeInternal:
    org_short_name, public_api_region, user_id = "lab", "api.eu", "me"

    def __init__(self, fail=(), key_error=None):
        self.fail, self.key_error, self.calls = set(fail), key_error, []

    def create_external_api_key(self):
        self.calls.append("create_external_api_key")
        if self.key_error:
            raise ConnectionError(self.key_error)
        return ExternalApiKey("secret", "kid")

    def __getattr__(self, name):
        def call(*args):
            self.calls.append(name)
            if name in self.fail:
                raise ConnectionError(f"{name} broke")
            return f"{name}-id"

        return call


class FakeExternal:
    def __init__(self, key, org, region):
        self.region = region

    def __getattr__(self, name):
        return lambda *a: f"{name}-id"


@pytest.fixture
def view(page, monkeypatch):
    monkeypatch.setattr(cv, "VerkadaExternalAPIClient", FakeExternal)
    monkeypatch.setattr(cv, "ROLE_PROPAGATION_SECONDS", 0)
    monkeypatch.setattr(cv, "BUILDING_PROVISION_SECONDS", 0)
    v = cv.CommissionView(lambda r: None)
    v.page = page
    return v


def _fill(view, page, template):
    view.template_dropdown.value = template
    view._on_template_change(Event(page))
    for name, field in view._device_fields.items():
        field.value = "PLATE1" if name == "License Plate" else "AAAA-BBBB-CCCC"


def _run(view, page, client, monkeypatch, template="AS"):
    monkeypatch.setattr(cv, "get_internal_client", lambda: client)
    _fill(view, page, template)
    asyncio.run(view._on_commission(Event(page)))


def _banner_text(view):
    report = view._run_section.controls[-1]
    return report.controls[0].content.controls[1].value


def test_a_failed_step_is_reported_as_failed(view, page, monkeypatch):
    client = FakeInternal(fail={"create_wired_output"})
    _run(view, page, client, monkeypatch)
    assert view._failures == [("Configuring Wired Strobe", "create_wired_output broke")]
    assert "completed with errors" in _banner_text(view)
    assert "0 failed" not in _banner_text(view)


def test_clean_run_reports_success_and_deletes_the_key(view, page, monkeypatch):
    client = FakeInternal()
    _run(view, page, client, monkeypatch)
    assert _banner_text(view).startswith("Commission complete")
    assert client.calls[-1] == "delete_external_api_key"
    assert ("done", "Temporary API key deleted") in view._cleanup
    assert session.running_job() is None and session._active_run is None


def test_api_key_failure_ends_in_a_report_not_a_hang(view, page, monkeypatch):
    client = FakeInternal(key_error="exceeded 10 API keys limit")
    _run(view, page, client, monkeypatch, template="ACSE")
    assert view._steps_failed == 1
    assert "exceeded 10 API keys limit" in view._failures[0][1]
    assert view._stepper._current == 3  # Report step
    assert not view.cancel_btn.visible
    assert client.calls == ["create_external_api_key"]  # nothing else attempted
    assert session._active_run is None


def test_external_client_gets_the_org_public_api_region(view, page, monkeypatch):
    seen = {}

    def ext(key, org, region):
        seen["region"] = region
        return FakeExternal(key, org, region)

    monkeypatch.setattr(cv, "VerkadaExternalAPIClient", ext)
    _run(view, page, FakeInternal(), monkeypatch, template="ACSE")
    assert seen["region"] == "api.eu"


def test_cancel_skips_remaining_steps_but_still_deletes_the_key(
    view, page, monkeypatch
):
    client = FakeInternal()
    original = client.__getattr__

    def cancelling(name):
        fn = original(name)
        if name == "enable_custom_roles":
            session.cancel_run()  # what the navigation guard does
        return fn

    client.__getattr__ = cancelling
    monkeypatch.setattr(FakeInternal, "__getattr__", lambda self, n: cancelling(n))
    _run(view, page, client, monkeypatch)
    assert "Commission cancelled" in _banner_text(view)
    assert "create_site" not in client.calls
    assert client.calls[-1] == "delete_external_api_key"


def test_second_run_is_refused_while_one_is_registered(view, page, monkeypatch):
    from utils.cancellation import CancellationToken

    session.begin_run("Decommission", CancellationToken())
    client = FakeInternal()
    _run(view, page, client, monkeypatch)
    assert client.calls == []
    assert view._form_section.visible


def _add_user(view, page, first="", last="", email=""):
    view._add_user_row(Event(page))
    fields = view._user_rows()[-1]
    for field, value in zip(fields, (first, last, email), strict=True):
        field.value = value
    return fields


def test_partial_supporting_user_blocks_review(view, page):
    _fill(view, page, "ACSE")
    fields = _add_user(view, page, first="Ada", email="ada@x.com")
    view._on_review(Event(page))
    assert view._stepper._current == 0  # still on Configure
    assert [f.error for f in fields] == [None, "Required", None]


def test_invalid_supporting_user_email_blocks_review(view, page):
    _fill(view, page, "ACSE")
    fields = _add_user(view, page, "Ada", "Lovelace", "ada-at-x.com")
    view._on_review(Event(page))
    assert fields[2].error == "Enter a valid email"
    assert view._stepper._current == 0


def test_review_counts_exactly_who_will_be_invited(view, page):
    _fill(view, page, "ACSE")
    _add_user(view, page, "Ada", "Lovelace", "ada@x.com")
    _add_user(view, page)  # empty rows are ignored
    view._on_review(Event(page))
    assert view._stepper._current == 1
    assert view._collect_supporting_users() == [("Ada", "Lovelace", "ada@x.com")]
