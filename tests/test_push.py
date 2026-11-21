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


def resp(code, status=None):
    return SimpleNamespace(status_code=code, json=lambda: {"error": {"status": status}} if status else {})


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


@pytest.mark.parametrize("code,status,exc", [(404, None, InvalidToken), (404, "UNREGISTERED", InvalidToken),
                                              (400, "INVALID_ARGUMENT", InvalidToken), (500, "INTERNAL", RuntimeError),
                                              (401, "UNAUTHENTICATED", RuntimeError)])
def test_fcm_send_tells_a_dead_token_from_other_failures(code, status, exc):
    with pytest.raises(exc) as e:
        fcm_send(PAYLOAD, "SECRET-TOKEN", SA, post=lambda *a, **k: resp(code, status), access_token="AT")
    assert type(e.value) is exc and "SECRET-TOKEN" not in str(e.value) and "AT" not in str(e.value).split()


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
