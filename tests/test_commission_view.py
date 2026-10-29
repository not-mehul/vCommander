"""Commission run: outcome, error handling, API-key cleanup, cancellation."""

import asyncio

import pytest
from conftest import Event

import pages.commission_view as cv
from apis.internal_api import ExternalApiKey, normalize_serial
from utils import session


class FakeInternal:
    org_short_name, public_api_region, user_id = "lab", "api.eu", "me"

    def __init__(self, fail=(), key_error=None):
        self.fail, self.key_error, self.calls = set(fail), key_error, []
        self.args = {}
        self.removable = []  # get_removable_permissions

    def create_external_api_key(self):
        self.calls.append("create_external_api_key")
        if self.key_error:
            raise ConnectionError(self.key_error)
        return ExternalApiKey("secret", "kid")

    def add_devices(self, devices):
        self.calls.append("add_devices")
        self.args["add_devices"] = ((devices,), {})
        if "add_devices" in self.fail:
            raise ConnectionError("add_devices broke")
        return {
            normalize_serial(serial): (
                ConnectionError(f"{name} rejected") if serial in self.fail else f"{name}-id"
            )
            for name, serial in devices
        }

    def get_removable_permissions(self):
        self.calls.append("get_removable_permissions")
        return self.removable

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append(name)
            self.args[name] = (args, kwargs)
            if name in self.fail:
                raise ConnectionError(f"{name} broke")
            return f"{name}-id"

        return call


@pytest.fixture
def view(page, monkeypatch):
    monkeypatch.setattr(cv, "ROLE_PROPAGATION_SECONDS", 0)
    v = cv.CommissionView(lambda r: None)
    v.page = page
    return v


def _fill(view, page, template):
    view.template_dropdown.value = template
    view._on_template_change(Event(page))
    for i, (name, field) in enumerate(view._device_fields.items()):
        field.value = "PLATE1" if name == "License Plate" else f"AAAA-BBBB-CCC{i}"


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


def test_clean_run_reports_success_and_needs_no_api_key(view, page, monkeypatch):
    client = FakeInternal()
    _run(view, page, client, monkeypatch)
    assert _banner_text(view).startswith("Commission complete")
    assert not [c for c in client.calls if "external_api_key" in c]
    assert session.running_job() is None and session._active_run is None


def test_a_failed_first_step_ends_in_a_report_not_a_hang(view, page, monkeypatch):
    client = FakeInternal(fail={"enable_custom_roles"})
    _run(view, page, client, monkeypatch, template="ACSE")
    assert view._steps_failed == 1
    assert "enable_custom_roles broke" in view._failures[0][1]
    assert view._stepper._current == 3  # Report step
    assert not view.cancel_btn.visible
    assert session._active_run is None


def test_vssl_access_group_and_plate_use_the_internal_api(view, page, monkeypatch):
    # The Command web app makes these calls through the internal API too, so
    # no template needs the public API (or a temporary key) any more.
    client = FakeInternal()
    _run(view, page, client, monkeypatch, template="VSSL")
    for name in (
        "create_access_group",
        "add_user_to_access_group",
        "add_license_plate_to_user",
    ):
        assert name in client.calls
    assert client.args["add_license_plate_to_user"][0] == ("me", "PLATE1")


def test_cancel_skips_remaining_steps(
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
    assert "create_or_reuse_site" not in client.calls
    assert session._active_run is None


@pytest.mark.parametrize("template", ["ESS", "ACSL"])
def test_access_station_pro_door_needs_no_separate_face_unlock(
    view, page, monkeypatch, template
):
    # The door is created with face-unlock-enabled in its configs, as the
    # Command web app does; the old follow-up door/config/set was redundant.
    client = FakeInternal()
    _run(view, page, client, monkeypatch, template=template)
    assert "create_access_station_pro_door" in client.calls
    assert "enable_door_face_unlock" not in client.calls
    assert view._steps_failed == 0


def test_acsl_creates_the_door_with_its_mfa_modes(view, page, monkeypatch):
    client = FakeInternal()
    _run(view, page, client, monkeypatch, template="ACSL")
    assert client.args["create_access_station_pro_door"][1] == {"mfa": True}
    assert not [c for c in client.calls if c.startswith("enable_door_mfa")]
    assert "create_mfa_schedule" in client.calls


def test_as_strobe_goes_on_output_1(view, page, monkeypatch):
    # pinNum is 0-based: Command shows pinNum 0 as the panel's "Output 1".
    client = FakeInternal()
    _run(view, page, client, monkeypatch, template="AS")
    assert client.args["create_wired_output"][0][-1] == 0


def test_access_station_pro_door_configs_carry_face_unlock():
    from apis.endpoints import _ACCESS_STATION_PRO_DOOR_CREATE_CONFIGS as configs

    assert {"paramName": "face-unlock-enabled", "paramValue": "True"} in configs


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


def test_devices_are_claimed_in_one_call_with_a_row_each(view, page, monkeypatch):
    client = FakeInternal()
    _run(view, page, client, monkeypatch, template="AS")
    assert client.calls.count("add_devices") == 1
    (devices,), _ = client.args["add_devices"]
    assert len(devices) == 4
    assert sum(line.startswith("[ok]   Adding") for line in view._run_log) == 4


def test_one_rejected_serial_fails_only_its_own_row(view, page, monkeypatch):
    client = FakeInternal()
    _fill(view, page, "VSSE")
    view._device_fields["Fisheye"].value = "FISH-0000-0001"
    client.fail.add("FISH-0000-0001")
    monkeypatch.setattr(cv, "get_internal_client", lambda: client)
    asyncio.run(view._on_commission(Event(page)))
    assert [label for label, _ in view._failures] == ["Adding Fisheye (FISH-0000-0001)"]
    assert client.calls.count("add_devices") == 1
    (cameras, *_), _ = client.args["configure_cameras"]
    assert len(cameras) == 2  # the rejected camera isn't configured


def test_a_failed_claim_call_fails_every_device_row_once(view, page, monkeypatch):
    client = FakeInternal(fail={"add_devices"})
    _run(view, page, client, monkeypatch, template="VSSE")
    assert client.calls.count("add_devices") == 1
    assert [label.split(" (")[0] for label, _ in view._failures] == [
        "Adding Dome",
        "Adding Bullet",
        "Adding Fisheye",
    ]


def test_supporting_users_already_in_the_org_are_not_reinvited(view, page, monkeypatch):
    client = FakeInternal()
    client.get_user_ids_by_email = lambda: {"ada@x.com": "id-ada"}
    invited = []
    client.invite_user = lambda email, *rest: invited.append(email)
    monkeypatch.setattr(cv, "get_internal_client", lambda: client)
    _fill(view, page, "AS")
    _add_user(view, page, "Ada", "Lovelace", "Ada@x.com")
    _add_user(view, page, "Alan", "Turing", "alan@x.com")
    asyncio.run(view._on_commission(Event(page)))
    assert invited == ["alan@x.com"]
    assert "[ok]   Adding user Ada Lovelace" in view._run_log
    assert view._failures == []


def test_the_same_serial_in_two_fields_blocks_review(view, page, monkeypatch):
    toasts = []
    monkeypatch.setattr(cv, "show_toast", lambda page, msg, **kw: toasts.append(msg))
    _fill(view, page, "VSSE")
    first, second = list(view._device_fields)[:2]
    view._device_fields[second].value = view._device_fields[first].value
    view._on_review(Event(page))
    assert view._stepper._current == 0
    assert toasts == [f"{first} and {second} have the same serial number."]


def test_a_supporting_user_listed_twice_is_invited_once(view, page):
    _fill(view, page, "ACSE")
    _add_user(view, page, "Ada", "Lovelace", "ada@x.com")
    _add_user(view, page, "Ada", "L", "ADA@x.com")
    assert view._collect_supporting_users() == [("Ada", "Lovelace", "ada@x.com")]


@pytest.mark.parametrize("template", ["ESS", "AS"])
def test_strobe_on_output_1_is_linked_to_the_default_response(view, page, monkeypatch, template):
    client = FakeInternal()
    client.create_wired_output = lambda *args: (client.args.__setitem__("strobe", args), "strobe-id")[1]
    _run(view, page, client, monkeypatch, template=template)
    name, _system, _panel, pin = client.args["strobe"]
    assert (name, pin) == ("Strobe Light", 0)
    (site, response, device_ids), _ = client.args["set_alarm_response_outputs"]
    assert (site, response, device_ids) == ("create_or_reuse_site-id", "create_alarm_site-id", ["strobe-id"])
    assert "[ok]   Linking Strobe to Default Response" in view._run_log


@pytest.mark.parametrize("group_id, expected", [("ap-id", "ap-id"), (None, "")])
def test_ess_af64_access_level_grants_all_participants_when_it_exists(
    view, page, monkeypatch, group_id, expected
):
    client = FakeInternal()
    client.find_access_group_id = lambda name: group_id
    _run(view, page, client, monkeypatch, template="ESS")
    (door, name, site, group), _ = client.args["create_access_level"]
    assert (door, name, site, group) == (
        "create_access_station_pro_door-id", "[DO NOT TOUCH] AF64", "create_or_reuse_site-id", expected,
    )
    assert view._failures == []



def test_acse_removes_user_permissions_before_anything_else(view, page, monkeypatch):
    client = FakeInternal()
    client.removable = [
        {"id": f"u{i}", "name": f"User {i}", "revoke": [{"entityId": "org", "permission": "X"}]}
        for i in range(cv.PARALLEL_REQUESTS + 1)
    ]
    revoked = []
    client.revoke_user_permissions = lambda uid, rv: revoked.append((uid, rv))
    _run(view, page, client, monkeypatch, template="ACSE")
    assert client.calls[0] == "get_removable_permissions"
    assert client.calls.index("enable_custom_roles") > 0
    assert sorted(u for u, _ in revoked) == sorted(u["id"] for u in client.removable)
    assert "[ok]   Removing 1 permission from User 0" in view._run_log
    assert view._failures == []


def test_acse_permission_reset_is_skipped_when_switched_off(view, page, monkeypatch):
    client = FakeInternal()
    monkeypatch.setattr(cv, "get_internal_client", lambda: client)
    _fill(view, page, "ACSE")
    assert view.reset_permissions_switch.visible and view.reset_permissions_switch.value
    view.reset_permissions_switch.value = False
    asyncio.run(view._on_commission(Event(page)))
    assert "get_removable_permissions" not in client.calls


def test_permission_reset_is_only_offered_for_acse(view, page):
    _fill(view, page, "VSSL")
    assert not view.reset_permissions_switch.visible
