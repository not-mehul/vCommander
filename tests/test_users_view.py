import asyncio

from conftest import Event

import pages.users_view as uv
from apis.endpoints import OrgShard
from apis.internal_api import OrgNotFoundError
from utils import db, session


def test_connect_looks_up_the_source_org_region(page, monkeypatch):
    seen = {}

    class FakeExternal:
        def __init__(self, api_key, org, region):
            seen["region"] = region

        def get_sites(self):
            return [{"site_id": "s1", "name": "HQ"}]

    monkeypatch.setattr(uv, "VerkadaExternalAPIClient", FakeExternal)
    monkeypatch.setattr(
        uv,
        "validate_org_short_name",
        lambda org: OrgShard(
            "prod2", "prod2.verkada.com",
            readable_name="EU", org_name="Source Org",
        ),
    )
    view = uv.UsersView(lambda route: None)
    view.page = page
    view._api_key_field.value = "key"
    view._import_org_field.value = "source-org"
    asyncio.run(view._on_connect(Event(page)))
    assert seen["region"] == "api.eu"
    assert db.load_import_settings()["api_region"] == "api.eu"
    assert view._current_step == 1
    assert view._source_org_text.value == "Connected to Source Org · EU"


def test_connect_flags_an_unknown_source_org(page, monkeypatch):
    def not_found(org):
        raise OrgNotFoundError(f"No Verkada org named '{org}' was found.")

    monkeypatch.setattr(uv, "validate_org_short_name", not_found)
    view = uv.UsersView(lambda route: None)
    view.page = page
    view._api_key_field.value = "key"
    view._import_org_field.value = "typo-org"
    asyncio.run(view._on_connect(Event(page)))
    assert view._import_org_field.error == "No Verkada org named 'typo-org' was found."
    assert view._current_step == 0


def test_stopping_an_invite_batch_skips_the_next_chunks(page, monkeypatch):
    # Invites go out PARALLEL_REQUESTS at a time; a stop takes effect before
    # the next chunk (the chunk in flight completes).
    invited = []

    class FakeInternal:
        def get_user_ids_by_email(self):
            return {}

        def invite_user(self, email, first, last):
            invited.append(email)
            session.cancel_run()  # user chose "Stop and continue" mid-batch
            return {"user_id": f"id-{email}"}

    monkeypatch.setattr(uv, "get_internal_client", lambda: FakeInternal())
    view = uv.UsersView(lambda route: None)
    view.page = page
    n = uv.PARALLEL_REQUESTS + 2
    for i in range(n):
        view._participants_column.controls.append(
            view._create_participant_row("First", f"{i}", f"p{i}@x.com")
        )
    asyncio.run(view._on_invite_all(Event(page)))
    assert sorted(invited) == sorted(f"p{i}@x.com" for i in range(uv.PARALLEL_REQUESTS))
    texts = [row.text for row in view._invite_progress.controls if hasattr(row, "text")]
    assert f"Skipped p{n - 1}@x.com (cancelled)" in texts
    assert session._active_run is None


def test_invites_are_sent_in_parallel(page, monkeypatch):
    import threading
    import time

    lock, state = threading.Lock(), {"now": 0, "max": 0}

    class FakeInternal:
        def get_user_ids_by_email(self):
            return {}

        def invite_user(self, email, first, last):
            with lock:
                state["now"] += 1
                state["max"] = max(state["max"], state["now"])
            time.sleep(0.05)
            with lock:
                state["now"] -= 1
            return {"user_id": f"id-{email}"}

    monkeypatch.setattr(uv, "get_internal_client", lambda: FakeInternal())
    view = _view_with_participants(
        page, *[("A", str(i), f"a{i}@x.com") for i in range(4)]
    )
    view._add_to_group_switch.value = False
    asyncio.run(view._on_invite_all(Event(page)))
    assert state["max"] > 1
    assert [r[2] for r in view._invited_records] == [f"a{i}@x.com" for i in range(4)]


def _view_with_participants(page, *rows):
    view = uv.UsersView(lambda route: None)
    view.page = page
    for first, last, email in rows:
        view._participants_column.controls.append(
            view._create_participant_row(first, last, email)
        )
    return view


def test_invalid_email_blocks_inviting(page, monkeypatch):
    monkeypatch.setattr(uv, "get_internal_client", lambda: None)
    view = _view_with_participants(page, ("A", "B", "not-an-email"))
    asyncio.run(view._on_invite_all(Event(page)))
    email_field = view._participants_column.controls[0].controls[2]
    assert email_field.error == "Enter a valid email"
    assert view._current_step == 0  # never advanced to the invite step
    assert session._active_run is None


def test_back_buttons_step_backwards(page):
    view = _view_with_participants(page)
    view._go_to_step(2, page)
    back = view._steps[2].controls[-1].controls[0]
    back.on_click(Event(page))
    assert view._current_step == 1
    back = view._steps[1].controls[-1].controls[0]
    back.on_click(Event(page))
    assert view._current_step == 0


def test_invite_progress_reaches_the_total(page, monkeypatch):
    class FakeInternal:
        def get_user_ids_by_email(self):
            return {}

        def invite_user(self, email, first, last):
            return {"user_id": None}

    monkeypatch.setattr(uv, "get_internal_client", lambda: FakeInternal())
    view = _view_with_participants(
        page, ("A", "1", "a1@x.com"), ("A", "2", "a2@x.com"), ("A", "3", "")
    )
    view._add_to_group_switch.value = False
    asyncio.run(view._on_invite_all(Event(page)))
    assert view._invite_header.label == "2 / 2"
    assert view._invite_result.visible


class GroupOrg:
    """Fake org for the participant groups: users, both groups, roles."""

    def __init__(self, existing=(), command_members=None, access_members=None,
                 roles=(), fail=()):
        self.existing = dict(existing)  # email -> user id
        self.groups = {}  # kind -> {"id", "member_ids"}
        if command_members is not None:
            self.groups["command"] = {"id": "g1", "member_ids": set(command_members)}
        if access_members is not None:
            self.groups["access"] = {"id": "ag1", "member_ids": set(access_members)}
        self.roles, self.fail, self.calls, self.invited = set(roles), set(fail), [], []

    def _maybe_fail(self, name):
        if name in self.fail:
            raise ConnectionError(f"{name} broke")

    def get_user_ids_by_email(self):
        return {e.lower(): i for e, i in self.existing.items()}

    def invite_user(self, email, first, last):
        self.invited.append(email)
        return {"user_id": f"id-{email}"}

    def _find(self, kind):
        group = self.groups.get(kind)
        return None if group is None else {"id": group["id"], "member_ids": set(group["member_ids"])}

    def _create(self, kind, name):
        self.calls.append(f"create_{kind}")
        self.groups[kind] = {"id": f"new-{kind}", "member_ids": set()}
        return f"new-{kind}"

    def _add(self, kind, user_ids, group_id):
        self._maybe_fail(f"add_{kind}")
        assert group_id == self.groups[kind]["id"]
        self.calls.append(f"add_{kind}:{sorted(user_ids)}")
        self.groups[kind]["member_ids"] |= set(user_ids)

    def find_group(self, name):
        assert name == uv.PARTICIPANTS_GROUP_NAME
        return self._find("command")

    def find_access_group(self, name):
        assert "access_admin" in "".join(self.calls[-1:]) or self.roles, "needs a role"
        self._maybe_fail("find_access_group")
        return self._find("access")

    def create_group(self, name):
        return self._create("command", name)

    def create_access_group(self, name):
        return self._create("access", name)

    def add_users_to_group(self, user_ids, group_id):
        self._add("command", user_ids, group_id)

    def add_users_to_access_group(self, user_ids, group_id):
        self._add("access", user_ids, group_id)

    def get_org_role_keys(self):
        return set(self.roles)

    def enable_access_admin(self, roles):
        self._maybe_fail("enable_access_admin")
        self.calls.append("access_admin_on:" + ",".join(roles))

    def disable_access_admin(self, roles):
        self.calls.append("access_admin_off:" + ",".join(roles))


_BOTH = "ACCESS_CONTROL_SYSTEM_ADMIN,ACCESS_CONTROL_USER_ADMIN"


def _invite(page, monkeypatch, org, *emails):
    monkeypatch.setattr(uv, "get_internal_client", lambda: org)
    view = _view_with_participants(page, *[("P", str(i), e) for i, e in enumerate(emails)])
    view._add_to_group_switch.value = True
    asyncio.run(view._on_invite_all(Event(page)))
    return view, [row.text for row in view._invite_progress.controls if hasattr(row, "text")]


def test_first_run_creates_both_groups_and_adds_everyone(page, monkeypatch):
    org = GroupOrg()
    _invite(page, monkeypatch, org, "a@x.com", "b@x.com")
    assert org.calls == [
        "create_command",
        "add_command:['id-a@x.com', 'id-b@x.com']",
        f"access_admin_on:{_BOTH}",
        "create_access",
        "add_access:['id-a@x.com', 'id-b@x.com']",
        f"access_admin_off:{_BOTH}",
    ]


def test_rerun_adds_only_people_missing_from_each_group(page, monkeypatch):
    org = GroupOrg(
        existing={"Old@x.com": "id-old"},
        command_members={"id-old"},
        access_members=set(),
        roles={"ACCESS_CONTROL_SYSTEM_ADMIN", "ACCESS_CONTROL_USER_ADMIN"},
    )
    _invite(page, monkeypatch, org, "old@x.com", "new@x.com")
    assert org.invited == ["new@x.com"]
    assert org.calls == [
        "add_command:['id-new@x.com']",
        "add_access:['id-new@x.com', 'id-old']",
    ]  # no group created, no role change: the user held both roles


def test_rerun_with_everyone_in_both_groups_adds_nobody(page, monkeypatch):
    org = GroupOrg(
        existing={"a@x.com": "id-a", "b@x.com": "id-b"},
        command_members={"id-a", "id-b", "id-other"},
        access_members={"id-a", "id-b"},
        roles={"ACCESS_CONTROL_USER_ADMIN"},
    )
    _, texts = _invite(page, monkeypatch, org, "a@x.com", "b@x.com")
    assert org.invited == []
    assert org.calls == [
        "access_admin_on:ACCESS_CONTROL_SYSTEM_ADMIN",
        "access_admin_off:ACCESS_CONTROL_SYSTEM_ADMIN",
    ]
    assert f"All 2 already in group '{uv.PARTICIPANTS_GROUP_NAME}'" in texts
    assert f"All 2 already in access group '{uv.PARTICIPANTS_GROUP_NAME}'" in texts


def test_roles_are_revoked_even_when_the_access_group_step_fails(page, monkeypatch):
    org = GroupOrg(fail={"find_access_group"})
    _, texts = _invite(page, monkeypatch, org, "a@x.com")
    assert org.calls[-1] == f"access_admin_off:{_BOTH}"
    assert any(t.startswith("Failed: access group lookup") for t in texts)


def test_access_group_is_skipped_when_the_role_grant_fails(page, monkeypatch):
    org = GroupOrg(fail={"enable_access_admin"})
    view, texts = _invite(page, monkeypatch, org, "a@x.com")
    assert "create_access" not in org.calls
    assert "create_command" in org.calls  # the Command group still happened
    assert any(t.startswith("Failed: granting access admin roles") for t in texts)


def test_a_failed_command_group_add_does_not_block_the_access_group(page, monkeypatch):
    org = GroupOrg(fail={"add_command"})
    _invite(page, monkeypatch, org, "a@x.com")
    assert "add_access:['id-a@x.com']" in org.calls


def test_a_participant_listed_twice_is_invited_once(page, monkeypatch):
    org = GroupOrg()
    view, texts = _invite(page, monkeypatch, org, "a@x.com", "A@X.com ", "b@x.com")
    assert sorted(org.invited) == ["a@x.com", "b@x.com"]
    assert view._invite_header.label == "2 / 2"
    assert any(t.startswith("Listed twice:") for t in texts)
    assert org.calls[1] == "add_command:['id-a@x.com', 'id-b@x.com']"
