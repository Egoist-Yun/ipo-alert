from types import SimpleNamespace

import pytest

import ipo.notify as notify
from ipo.main import run
from ipo.notify import Target, send, target_from_env
from ipo.push import fcm_message, fcm_send
from ipo.push import main as push_main
from tests.test_main import NOW, Rec, fake_fetch

SA = {"project_id": "proj", "client_email": "x@proj.iam.gserviceaccount.com", "private_key": "KEY"}
PAYLOAD = {"title": "제목", "message": "내용", "click": "https://s/#2352"}


def resp(code, status=None, details=None):
    err = {"status": status, **({"details": details} if details is not None else {})}
    return SimpleNamespace(status_code=code, json=lambda: {"error": err} if status or details else {})


UNREGISTERED = [{"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "UNREGISTERED"}]


def test_fcm_message_goes_to_the_topic_not_a_token_and_cuts_the_body():
    msg = fcm_message({"title": "t", "message": "가" * 1500})["message"]
    assert msg["topic"] == "ipo-alerts" and "token" not in msg
    assert msg["notification"] == {"title": "t", "body": "가" * 1000}
    assert msg["data"] == {"url": ""}                                          # no click: empty string, not missing
    assert msg["android"] == {"priority": "high", "notification": {"channel_id": "ipo-alerts"}}
    assert fcm_message(PAYLOAD)["message"]["data"] == {"url": "https://s/#2352"}


def test_fcm_send_posts_to_the_project_url_with_the_bearer_token():
    seen = {}

    def post(url, json, headers, timeout):
        seen.update(url=url, json=json, headers=headers, timeout=timeout)
        return resp(200)
    fcm_send(PAYLOAD, SA, post=post, access_token="AT")
    assert seen["url"] == "https://fcm.googleapis.com/v1/projects/proj/messages:send"
    assert seen["headers"] == {"Authorization": "Bearer AT"} and seen["timeout"] == 10
    assert seen["json"]["message"]["topic"] == "ipo-alerts"


@pytest.mark.parametrize("code,status,details", [
    (404, "NOT_FOUND", UNREGISTERED), (400, "INVALID_ARGUMENT", None), (404, None, None), (500, "INTERNAL", None),
    (401, "UNAUTHENTICATED", None)])
def test_every_fcm_error_is_a_runtime_error_with_only_code_status_and_error_code(code, status, details):
    with pytest.raises(RuntimeError) as e:
        fcm_send(PAYLOAD, SA, post=lambda *a, **k: resp(code, status, details), access_token="AT")
    expected = f"FCM {code} {status or ''} {'UNREGISTERED' if details else ''}".replace("  ", " ").strip()
    assert str(e.value) == expected


class Calls:
    def __init__(self, fcm_exc=None):
        self.fcm, self.ntfy, self.fcm_exc = [], [], fcm_exc

    def fcm_send(self, payload, sa, **kw):
        self.fcm.append(payload)
        if self.fcm_exc:
            raise self.fcm_exc

    def post(self, url, json, timeout):
        self.ntfy.append(json)


@pytest.fixture
def calls(monkeypatch):
    c = Calls()
    monkeypatch.setattr(notify, "fcm_send", c.fcm_send)
    return c


FCM_TARGET = dict(topic="nt", fcm_sa=SA)


def test_fcm_success_does_not_touch_ntfy(calls):
    send(PAYLOAD, Target(**FCM_TARGET), post=calls.post)
    assert calls.fcm == [PAYLOAD] and calls.ntfy == []


def test_fcm_failure_falls_back_to_ntfy(calls):
    calls.fcm_exc = RuntimeError("FCM 500")
    send(PAYLOAD, Target(**FCM_TARGET), post=calls.post)
    assert calls.ntfy == [{**PAYLOAD, "topic": "nt"}]


def test_fcm_failure_without_ntfy_raises(calls):
    calls.fcm_exc = RuntimeError("FCM 500")
    with pytest.raises(RuntimeError):
        send(PAYLOAD, Target(topic=None, fcm_sa=SA), post=calls.post)


def test_without_fcm_only_ntfy_is_used(calls):
    send(PAYLOAD, Target(topic="nt"), post=calls.post)
    assert calls.fcm == [] and len(calls.ntfy) == 1
    send(PAYLOAD, Target(topic="nt", fcm_sa=None), post=calls.post)                      # no service account: no FCM
    assert calls.fcm == [] and len(calls.ntfy) == 2


def test_nothing_configured_is_falsy_and_run_sends_nothing(tmp_path, calls):
    assert not Target() and Target(topic="x") and Target(fcm_sa=SA) and Target(**FCM_TARGET)
    rec = Rec()
    assert run(tmp_path, Target(), "", NOW, fetch=fake_fetch, post=rec) == 0
    assert rec.calls == [] and calls.fcm == [] and calls.ntfy == []


def test_run_sends_through_fcm_when_configured(tmp_path, calls):
    rec = Rec()
    assert run(tmp_path, Target(**FCM_TARGET), "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    assert calls.fcm and rec.calls == []                                       # everything went through FCM


def test_target_from_env_reads_the_two_variables():
    import json
    t = target_from_env({"NTFY_TOPIC": "nt", "FCM_SERVICE_ACCOUNT": json.dumps(SA)})
    assert (t.topic, t.fcm_sa) == ("nt", SA)
    assert not target_from_env({}) and not target_from_env({"FCM_TOKEN": "OLD"})        # the token variable no longer matters


def test_a_broken_service_account_uses_ntfy_only_says_so_once_and_prints_no_value(capsys):
    rec = Rec()
    secret = '{"private_key": "TOP-SECRET'
    t = target_from_env({"NTFY_TOPIC": "nt", "FCM_SERVICE_ACCOUNT": secret}, post=rec)
    assert t.fcm_sa is None and not t.fcm and t.topic == "nt"
    assert [(c["title"], c["message"]) for c in rec.calls] == [("공모주 달력", "설정 오류 · FCM_SERVICE_ACCOUNT를 읽지 못해 ntfy로만 보내요")]
    out = capsys.readouterr()
    assert "TOP-SECRET" not in out.out + out.err


def test_a_service_account_without_the_needed_fields_counts_as_broken():
    rec = Rec()
    t = target_from_env({"NTFY_TOPIC": "nt", "FCM_SERVICE_ACCOUNT": '{"project_id": "p"}'}, post=rec)
    assert not t.fcm and len(rec.calls) == 1


def test_target_repr_hides_the_secrets():
    assert "KEY" not in repr(Target(**FCM_TARGET)) and "proj" not in repr(Target(**FCM_TARGET))


def test_the_cli_sends_one_alert_and_does_nothing_without_a_target(calls, capsys):
    assert push_main(["제목", "내용"], env={"NTFY_TOPIC": "nt"}, post=calls.post) == 0
    assert calls.ntfy == [{"title": "제목", "message": "내용", "topic": "nt"}]
    assert push_main(["제목", "내용"], env={}, post=calls.post) == 0 and len(calls.ntfy) == 1
    assert push_main(["only-one"], env={}, post=calls.post) == 2


def test_the_fcm_failure_log_is_one_short_line_without_a_traceback(calls, capsys):
    calls.fcm_exc = RuntimeError("FCM 500 INTERNAL")
    send(PAYLOAD, Target(**FCM_TARGET), post=calls.post)
    out = capsys.readouterr()
    assert "FCM failed: RuntimeError: FCM 500 INTERNAL" in out.out and "Traceback" not in out.out + out.err


def test_the_cli_returns_1_when_the_send_fails_so_the_workflow_can_fall_back(calls):
    def boom(url, json, timeout):
        raise ConnectionError("down")
    assert push_main(["제목", "내용"], env={"NTFY_TOPIC": "nt"}, post=boom) == 1
