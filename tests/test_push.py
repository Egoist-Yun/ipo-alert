from types import SimpleNamespace

import pytest

import ipo.notify as notify
from ipo.main import run
from ipo.notify import Target, send, target_from_env
from ipo.push import InvalidToken, fcm_message, fcm_send
from ipo.push import main as push_main
from tests.test_main import NOW, Rec, fake_fetch

SA = {"project_id": "proj", "client_email": "x@proj.iam.gserviceaccount.com", "private_key": "KEY"}
PAYLOAD = {"title": "제목", "message": "내용", "click": "https://s/#2352"}


def resp(code, status=None, details=None):
    err = {"status": status, **({"details": details} if details is not None else {})}
    return SimpleNamespace(status_code=code, json=lambda: {"error": err} if status or details else {})


UNREGISTERED = [{"@type": "type.googleapis.com/google.firebase.fcm.v1.FcmError", "errorCode": "UNREGISTERED"}]
BAD_TOKEN_FIELD = [{"@type": "type.googleapis.com/google.rpc.BadRequest",
                    "fieldViolations": [{"field": "message.token", "description": "invalid"}]}]
BAD_OTHER_FIELD = [{"@type": "type.googleapis.com/google.rpc.BadRequest",
                    "fieldViolations": [{"field": "message.android.notification.channel_id", "description": "invalid"}]}]


def test_fcm_message_has_the_agreed_shape_and_cuts_the_body():
    msg = fcm_message({"title": "t", "message": "가" * 1500}, "TOK")["message"]
    assert msg["token"] == "TOK" and msg["notification"] == {"title": "t", "body": "가" * 1000}
    assert msg["data"] == {"url": ""}                                          # no click: empty string, not missing
    assert msg["android"] == {"priority": "high", "notification": {"channel_id": "ipo-alerts"}}
    assert fcm_message(PAYLOAD, "T")["message"]["data"] == {"url": "https://s/#2352"}


def test_fcm_send_posts_to_the_project_url_with_the_bearer_token():
    seen = {}

    def post(url, json, headers, timeout):
        seen.update(url=url, json=json, headers=headers, timeout=timeout)
        return resp(200)
    fcm_send(PAYLOAD, "TOK", SA, post=post, access_token="AT")
    assert seen["url"] == "https://fcm.googleapis.com/v1/projects/proj/messages:send"
    assert seen["headers"] == {"Authorization": "Bearer AT"} and seen["timeout"] == 10
    assert seen["json"]["message"]["token"] == "TOK"


@pytest.mark.parametrize("code,status,details,exc", [
    (404, "NOT_FOUND", UNREGISTERED, InvalidToken),                 # FcmError UNREGISTERED
    (400, "INVALID_ARGUMENT", BAD_TOKEN_FIELD, InvalidToken),       # the violation is on the token field
    (400, "INVALID_ARGUMENT", None, RuntimeError),                  # a bare INVALID_ARGUMENT can be a wrong payload
    (400, "INVALID_ARGUMENT", BAD_OTHER_FIELD, RuntimeError),
    (404, None, None, RuntimeError),                                 # a bare 404 can be a wrong project id
    (404, "NOT_FOUND", None, RuntimeError),
    (500, "INTERNAL", None, RuntimeError),
    (401, "UNAUTHENTICATED", None, RuntimeError)])
def test_fcm_send_tells_a_dead_token_from_other_failures(code, status, details, exc):
    with pytest.raises(exc) as e:
        fcm_send(PAYLOAD, "SECRET-TOKEN", SA, post=lambda *a, **k: resp(code, status, details), access_token="AT")
    assert type(e.value) is exc and "SECRET-TOKEN" not in str(e.value)
    assert str(e.value).startswith(f"FCM {code}")


def test_the_error_text_carries_only_code_status_and_error_code():
    with pytest.raises(InvalidToken) as e:
        fcm_send(PAYLOAD, "T", SA, post=lambda *a, **k: resp(404, "NOT_FOUND", UNREGISTERED), access_token="AT")
    assert str(e.value) == "FCM 404 NOT_FOUND UNREGISTERED"


class Calls:
    def __init__(self, fcm_exc=None):
        self.fcm, self.ntfy, self.fcm_exc = [], [], fcm_exc

    def fcm_send(self, payload, token, sa, **kw):
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


FCM_TARGET = dict(topic="nt", fcm_token="TOK", fcm_sa=SA)


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
        send(PAYLOAD, Target(topic=None, fcm_token="TOK", fcm_sa=SA), post=calls.post)


def test_a_dead_token_sends_the_alert_plus_exactly_one_notice_per_run(calls):
    calls.fcm_exc = InvalidToken("FCM 404")
    target = Target(**FCM_TARGET)
    send(PAYLOAD, target, post=calls.post)
    send(PAYLOAD, target, post=calls.post)
    titles = [n["title"] for n in calls.ntfy]
    assert titles.count("앱 알림 토큰이 무효예요") == 1 and titles.count("제목") == 2
    assert "FCM_TOKEN" in next(n["message"] for n in calls.ntfy if n["title"].startswith("앱 알림"))


def test_without_fcm_only_ntfy_is_used(calls):
    send(PAYLOAD, Target(topic="nt"), post=calls.post)
    assert calls.fcm == [] and len(calls.ntfy) == 1
    send(PAYLOAD, Target(topic="nt", fcm_token="TOK", fcm_sa=None), post=calls.post)      # token alone is not enough
    assert calls.fcm == [] and len(calls.ntfy) == 2


def test_nothing_configured_is_falsy_and_run_sends_nothing(tmp_path, calls):
    assert not Target() and not Target(fcm_token="T") and Target(topic="x") and Target(**FCM_TARGET)
    rec = Rec()
    assert run(tmp_path, Target(), "", NOW, fetch=fake_fetch, post=rec) == 0
    assert rec.calls == [] and calls.fcm == [] and calls.ntfy == []


def test_run_sends_through_fcm_when_configured(tmp_path, calls):
    rec = Rec()
    assert run(tmp_path, Target(**FCM_TARGET), "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    assert calls.fcm and rec.calls == []                                       # everything went through FCM


def test_target_from_env_reads_the_three_variables():
    import json
    t = target_from_env({"NTFY_TOPIC": "nt", "FCM_TOKEN": "TOK", "FCM_SERVICE_ACCOUNT": json.dumps(SA)})
    assert (t.topic, t.fcm_token, t.fcm_sa) == ("nt", "TOK", SA)
    assert not target_from_env({})


def test_a_broken_service_account_uses_ntfy_only_says_so_once_and_prints_no_value(capsys):
    rec = Rec()
    secret = '{"private_key": "TOP-SECRET'
    t = target_from_env({"NTFY_TOPIC": "nt", "FCM_TOKEN": "TOK", "FCM_SERVICE_ACCOUNT": secret}, post=rec)
    assert t.fcm_sa is None and not t.fcm and t.topic == "nt"
    assert [c["title"] for c in rec.calls] == ["공모주 FCM 설정 읽기 실패"]
    out = capsys.readouterr()
    assert "TOP-SECRET" not in out.out + out.err and "TOK" not in out.out + out.err


def test_a_service_account_without_the_needed_fields_counts_as_broken():
    rec = Rec()
    t = target_from_env({"NTFY_TOPIC": "nt", "FCM_TOKEN": "TOK", "FCM_SERVICE_ACCOUNT": '{"project_id": "p"}'}, post=rec)
    assert not t.fcm and len(rec.calls) == 1


def test_target_repr_hides_the_secrets():
    assert "TOK" not in repr(Target(**FCM_TARGET)) and "KEY" not in repr(Target(**FCM_TARGET))


def test_the_cli_sends_one_alert_and_does_nothing_without_a_target(calls, capsys):
    assert push_main(["제목", "내용"], env={"NTFY_TOPIC": "nt"}, post=calls.post) == 0
    assert calls.ntfy == [{"title": "제목", "message": "내용", "topic": "nt"}]
    assert push_main(["제목", "내용"], env={}, post=calls.post) == 0 and len(calls.ntfy) == 1
    assert push_main(["only-one"], env={}, post=calls.post) == 2


def test_a_failing_token_notice_does_not_make_send_fail_and_the_alert_goes_out_once(calls, capsys):
    calls.fcm_exc = InvalidToken("FCM 404")
    sent = []

    def post(url, json, timeout):
        sent.append(json["title"])
        if json["title"].startswith("앱 알림"):
            raise ConnectionError("ntfy down")
    send(PAYLOAD, Target(**FCM_TARGET), post=post)                              # no exception
    assert sent == ["제목", "앱 알림 토큰이 무효예요"]
    assert "ConnectionError" in capsys.readouterr().out


def test_each_target_announces_a_dead_token_once_it_is_not_a_global_flag(calls):
    calls.fcm_exc = InvalidToken("FCM 404")
    for _ in range(2):
        send(PAYLOAD, Target(**FCM_TARGET), post=calls.post)
    assert [n["title"] for n in calls.ntfy].count("앱 알림 토큰이 무효예요") == 2


def test_the_fcm_failure_log_is_one_short_line_without_a_traceback(calls, capsys):
    calls.fcm_exc = RuntimeError("FCM 500 INTERNAL")
    send(PAYLOAD, Target(**FCM_TARGET), post=calls.post)
    out = capsys.readouterr()
    assert "FCM failed: RuntimeError: FCM 500 INTERNAL" in out.out and "Traceback" not in out.out + out.err


def test_the_cli_returns_1_when_the_send_fails_so_the_workflow_can_fall_back(calls):
    def boom(url, json, timeout):
        raise ConnectionError("down")
    assert push_main(["제목", "내용"], env={"NTFY_TOPIC": "nt"}, post=boom) == 1
