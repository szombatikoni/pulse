"""A kérdőívszerkesztő végpontjai (M3, A5; F13): a sablon részletei, új verzió
és új kérdőív. A módosítás mindig új, immutabilis verzió; a régi verziók, a
rájuk hivatkozó kitöltések és a már megnyílt alkalmak nem változnak."""

import copy
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models import Question, QuestionnaireTemplate, QuestionnaireVersion, RuleType, Severity
from app.services.questionnaires import (
    QuestionnaireError,
    add_version,
    assign_questionnaire,
    code_from_name,
    create_template,
)
from app.services.rules import create_rule
from seed.questionnaires import WELLBEING_CODE, WELLBEING_NAME, WELLBEING_V1
from tests.factories import assign, make_admin, make_doctor, make_patient

URL = "/api/questionnaires"


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def pid(user) -> str:
    return str(user.patient_profile.id)


@pytest.fixture
def setup(db):
    doctor = make_doctor(db)
    # Másik orvos, akinek nincs betege: a sablonok közösek, ő is szerkesztheti (D1).
    other = make_doctor(db, email="masik@test.example", name="Dr. Másik")
    patient = make_patient(db)
    assign(db, doctor, patient)
    template = create_template(
        db, code=WELLBEING_CODE, name=WELLBEING_NAME, created_by=doctor.id, spec=WELLBEING_V1
    )
    assign_questionnaire(
        db,
        patient_id=patient.patient_profile.id,
        template=template,
        assigned_by=doctor.id,
        start_date=(datetime.now(UTC) - timedelta(days=7)).date(),
    )
    create_rule(
        db,
        patient_id=patient.patient_profile.id,
        created_by=doctor.id,
        rule_type=RuleType.QUESTIONNAIRE,
        params={"questionnaire": WELLBEING_CODE, "bands": ["warning", "critical"]},
        severity=Severity.MODERATE,
    )
    return {
        "doctor": doctor,
        "other": other,
        "patient": patient,
        "admin": make_admin(db),
        "template": template,
    }


def version_body(base: int = 1, **changes) -> dict:
    """A „Közérzet" 1. verziója a szerkesztő alakjában (ahogy a GET adja), a
    megadott mezők felülírásával."""
    body = {"base_version_no": base, **copy.deepcopy(WELLBEING_V1.model_dump())}
    for question in body["questions"]:
        if question["question_type"] == "scale":
            question["options"] = []
    body.update(changes)
    return body


def renamed_first_question(base: int = 1, text: str = "Hogyan aludt az elmúlt héten?") -> dict:
    body = version_body(base)
    body["questions"][0]["text"] = text
    return body


def stored(db, template_id) -> list:
    """A sablon verziói és kérdései az adatbázisból, összehasonlítható alakban."""
    versions = db.scalars(
        select(QuestionnaireVersion)
        .where(QuestionnaireVersion.template_id == template_id)
        .order_by(QuestionnaireVersion.version_no)
        .execution_options(populate_existing=True)
    ).all()
    result = []
    for v in versions:
        questions = db.scalars(
            select(Question)
            .where(Question.version_id == v.id)
            .order_by(Question.order_no)
            .execution_options(populate_existing=True)
        ).all()
        result.append(
            (
                v.id,
                v.version_no,
                v.scoring_thresholds,
                [
                    (q.id, q.question_type, q.text, q.scale_min, q.scale_max, q.good_end)
                    + (q.options_scores,)
                    for q in questions
                ],
            )
        )
    return result


# --- Részletek -----------------------------------------------------------------


def test_detail_gives_the_editor_form_of_the_current_version(client, setup):
    response = client.get(f"{URL}/{WELLBEING_CODE}", headers=auth(setup["doctor"]))
    assert response.status_code == 200
    data = response.json()
    assert (data["code"], data["name"]) == (WELLBEING_CODE, WELLBEING_NAME)
    current = data["current"]
    assert (current["version_no"], current["max_score"]) == (1, 13)
    sleep, fatigue, dizziness = current["questions"]
    # A skála végfeliratai a tárolt válaszcímkékből visszabontva, pontok nélkül.
    assert sleep == {
        "question_type": "scale",
        "text": "Hogyan aludt az elmúlt éjszaka?",
        "scale_min": 1,
        "scale_max": 5,
        "good_end": "max",
        "min_label": "nagyon rosszul",
        "max_label": "nagyon jól",
        "options": [],
    }
    assert (fatigue["good_end"], fatigue["min_label"], fatigue["max_label"]) == (
        "min",
        "egyáltalán nem",
        "nagyon",
    )
    assert dizziness["options"] == [
        {"value": "never", "label": "Nem", "score": 0},
        {"value": "rarely", "label": "Ritkán", "score": 2},
        {"value": "daily", "label": "Naponta", "score": 5},
    ]
    assert current["scoring_thresholds"] == [
        {"band": "normal", "min": 0, "max": 5},
        {"band": "warning", "min": 6, "max": 10},
        {"band": "critical", "min": 11, "max": 13},
    ]
    assert [v["version_no"] for v in data["versions"]] == [1]


def test_detail_round_trips_into_an_identical_version(client, db, setup):
    # A GET alakja változtatás nélkül visszaküldve ugyanazt a tartalmat menti
    # (a skála végfeliratai is megmaradnak).
    current = client.get(f"{URL}/{WELLBEING_CODE}", headers=auth(setup["doctor"])).json()["current"]
    body = {
        "base_version_no": 1,
        "questions": current["questions"],
        "scoring_thresholds": current["scoring_thresholds"],
    }
    response = client.post(
        f"{URL}/{WELLBEING_CODE}/versions", json=body, headers=auth(setup["doctor"])
    )
    assert response.status_code == 201
    (_, _, bands1, q1), (_, _, bands2, q2) = stored(db, setup["template"].id)
    assert bands1 == bands2
    assert [q[1:] for q in q1] == [q[1:] for q in q2]


def test_unknown_questionnaire_is_404(client, setup):
    headers = auth(setup["doctor"])
    assert client.get(f"{URL}/nincs_ilyen", headers=headers).status_code == 404
    response = client.post(f"{URL}/nincs_ilyen/versions", json=version_body(), headers=headers)
    assert response.status_code == 404


# --- Új verzió -----------------------------------------------------------------


def test_new_version_leaves_the_old_one_untouched(client, db, setup):
    template_id = setup["template"].id
    before = stored(db, template_id)
    body = version_body()
    body["questions"][2]["options"][1]["score"] = 4  # „Ritkán" 2 → 4 pont
    body["scoring_thresholds"] = [
        {"band": "normal", "min": 0, "max": 3},
        {"band": "warning", "min": 4, "max": 10},
        {"band": "critical", "min": 11, "max": 13},
    ]
    response = client.post(
        f"{URL}/{WELLBEING_CODE}/versions", json=body, headers=auth(setup["doctor"])
    )
    assert response.status_code == 201
    data = response.json()
    assert (data["current"]["version_no"], data["current"]["max_score"]) == (2, 13)
    assert [v["version_no"] for v in data["versions"]] == [2, 1]

    after = stored(db, template_id)
    assert after[0] == before[0]  # az 1. verzió sorai bájtra azonosak
    assert after[1][1] == 2
    assert after[1][2][0]["max"] == 3


def test_old_submission_and_open_occurrence_keep_their_version(client, db, setup):
    patient, doctor = setup["patient"], setup["doctor"]
    url = f"/api/patients/{pid(patient)}/questionnaires"
    # A beteg megnyitja és kitölti (v1): 1 + 3 + 2 = 6 pont, figyelmeztető.
    [questionnaire] = client.get(url, headers=auth(patient)).json()
    q1, q2, q3 = questionnaire["questions"]
    created = client.post(
        f"/api/patients/{pid(patient)}/submissions",
        json={
            "questionnaire_code": WELLBEING_CODE,
            "answers": {q1["id"]: "4", q2["id"]: "4", q3["id"]: "rarely"},
        },
        headers=auth(patient),
    )
    assert created.status_code == 201
    subs_url = f"/api/patients/{pid(patient)}/submissions"
    before = client.get(subs_url, headers=auth(doctor)).json()

    # Új verzió: más kérdésszöveg, a „Ritkán" 4 pontot ér, más sávok.
    body = renamed_first_question()
    body["questions"][2]["options"][1]["score"] = 4
    body["questions"][2]["options"][1]["label"] = "Néha"
    body["scoring_thresholds"] = [
        {"band": "normal", "min": 0, "max": 7},
        {"band": "warning", "min": 8, "max": 10},
        {"band": "critical", "min": 11, "max": 13},
    ]
    response = client.post(f"{URL}/{WELLBEING_CODE}/versions", json=body, headers=auth(doctor))
    assert response.status_code == 201

    # A régi kitöltés pontszáma, sávja és válaszcímkéi változatlanok.
    after = client.get(subs_url, headers=auth(doctor)).json()
    assert after == before
    [sub] = after
    assert (sub["version_no"], sub["total_score"], sub["band"]) == (1, 6, "warning")
    assert sub["answers"][2]["label"] == "Ritkán"
    # A már megnyílt alkalom a régi verziót adja a betegnek (a következő időszak kapja az újat).
    [still] = client.get(url, headers=auth(patient)).json()
    assert still["version_no"] == 1
    assert still["questions"][0]["text"] == "Hogyan aludt az elmúlt éjszaka?"


def test_band_rule_still_alerts_on_the_new_version(client, db, setup):
    # A három rögzített sávnév (D2) miatt a meglévő sávszabály az új verzión is riaszt.
    patient, doctor = setup["patient"], setup["doctor"]
    response = client.post(
        f"{URL}/{WELLBEING_CODE}/versions", json=renamed_first_question(), headers=auth(doctor)
    )
    assert response.status_code == 201
    # Az időszak alkalma még nem nyílt meg, így az első lekérés már az új verziót rögzíti.
    [questionnaire] = client.get(
        f"/api/patients/{pid(patient)}/questionnaires", headers=auth(patient)
    ).json()
    assert questionnaire["version_no"] == 2
    q1, q2, q3 = questionnaire["questions"]
    assert q1["text"] == "Hogyan aludt az elmúlt héten?"
    created = client.post(
        f"/api/patients/{pid(patient)}/submissions",
        json={
            "questionnaire_code": WELLBEING_CODE,
            "answers": {q1["id"]: "1", q2["id"]: "5", q3["id"]: "daily"},  # 13 pont
        },
        headers=auth(patient),
    )
    assert created.status_code == 201
    [alert] = client.get(f"/api/patients/{pid(patient)}/alerts", headers=auth(doctor)).json()
    trigger = alert["events"][0]["triggers"][0]
    assert trigger["band"] == "critical"
    assert trigger["submission"]["version_no"] == 2


def test_stale_base_version_is_409(client, db, setup):
    headers = auth(setup["doctor"])
    first = client.post(f"{URL}/{WELLBEING_CODE}/versions", json=version_body(1), headers=headers)
    assert first.status_code == 201
    # Egy másik orvos még az 1. verzióból indult: az ő mentése nem írhatja felül a 2.-at.
    stale = client.post(
        f"{URL}/{WELLBEING_CODE}/versions",
        json=renamed_first_question(1),
        headers=auth(setup["other"]),
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == {"code": "stale_version", "current_version_no": 2}
    assert len(stored(db, setup["template"].id)) == 2
    # A friss verzióból indulva már menthető.
    fresh = client.post(
        f"{URL}/{WELLBEING_CODE}/versions",
        json=renamed_first_question(2),
        headers=auth(setup["other"]),
    )
    assert fresh.status_code == 201
    assert fresh.json()["current"]["version_no"] == 3


def test_add_version_checks_the_base_under_the_lock(db, setup):
    template = setup["template"]
    with pytest.raises(QuestionnaireError) as error:
        add_version(db, template, WELLBEING_V1, base_version_no=2)
    assert (error.value.code, error.value.conflict) == ("stale_version", True)
    assert add_version(db, template, WELLBEING_V1, base_version_no=1).version_no == 2


# --- Jogosultság ---------------------------------------------------------------


@pytest.mark.parametrize("role", ["patient", "admin"])
def test_only_doctors_use_the_editor(client, setup, role):
    headers = auth(setup[role])
    assert client.get(f"{URL}/{WELLBEING_CODE}", headers=headers).status_code == 403
    assert (
        client.post(
            f"{URL}/{WELLBEING_CODE}/versions", json=version_body(), headers=headers
        ).status_code
        == 403
    )
    new = {**version_body(), "name": "Tünetnapló"}
    assert client.post(URL, json=new, headers=headers).status_code == 403


def test_editor_requires_login(client, setup):
    assert client.get(f"{URL}/{WELLBEING_CODE}").status_code == 401
    assert client.post(f"{URL}/{WELLBEING_CODE}/versions", json=version_body()).status_code == 401
    assert client.post(URL, json={**version_body(), "name": "X"}).status_code == 401


def test_any_doctor_may_edit_shared_templates(client, setup):
    # D1: a sablonok közösek; a betegtelen orvos is ment új verziót.
    response = client.post(
        f"{URL}/{WELLBEING_CODE}/versions", json=version_body(), headers=auth(setup["other"])
    )
    assert response.status_code == 201


# --- Ellenőrzés, határesetek ---------------------------------------------------


def _scale(**fields) -> dict:
    return {
        "question_type": "scale",
        "text": "Hogy érzi magát?",
        "scale_min": 1,
        "scale_max": 5,
        "good_end": "max",
        **fields,
    }


def _single(options: list[dict]) -> dict:
    return {"question_type": "single", "text": "Szédült?", "options": options}


def _bands(warning: int, critical: int, top: int) -> list[dict]:
    return [
        {"band": "normal", "min": 0, "max": warning - 1},
        {"band": "warning", "min": warning, "max": critical - 1},
        {"band": "critical", "min": critical, "max": top},
    ]


OPTS = [{"value": "a", "label": "Nem", "score": 0}, {"value": "b", "label": "Igen", "score": 3}]


@pytest.mark.parametrize(
    ("questions", "bands"),
    [
        pytest.param([_scale(good_end=None)], _bands(2, 3, 4), id="skala-jobb-veg-nelkul"),
        pytest.param([_scale(scale_max=7)], _bands(2, 4, 6), id="skala-1-7"),
        pytest.param([_scale(scale_min=0)], _bands(2, 4, 5), id="skala-0-5"),
        pytest.param([_scale(options=OPTS)], _bands(2, 3, 4), id="skala-lehetoseggel"),
        pytest.param([_single(OPTS[:1]), _scale()], _bands(2, 3, 4), id="egy-lehetoseg"),
        pytest.param(
            [_single([OPTS[0], {**OPTS[1], "value": "a"}])], _bands(1, 2, 3), id="ismetlodo"
        ),
        pytest.param(
            [_single([OPTS[0], {**OPTS[1], "score": 11}])], _bands(2, 6, 11), id="pont-11"
        ),
        pytest.param(
            [_single([OPTS[0], {**OPTS[1], "score": -1}])], _bands(1, 2, 3), id="pont-negativ"
        ),
        pytest.param(
            [_single([{**OPTS[0], "value": f"v{i}"} for i in range(11)])],
            _bands(1, 2, 3),
            id="11-lehetoseg",
        ),
        pytest.param([_scale()], _bands(2, 3, 5), id="sav-a-maximumon-tul"),
        pytest.param([_scale()], _bands(3, 2, 4), id="fordított-hatarok"),
        pytest.param(
            [_scale()],
            [
                {"band": "normal", "min": 0, "max": 1},
                {"band": "high", "min": 2, "max": 2},
                {"band": "critical", "min": 3, "max": 4},
            ],
            id="ismeretlen-savnev",
        ),
        pytest.param(
            [_scale()],
            [
                {"band": "warning", "min": 0, "max": 1},
                {"band": "normal", "min": 2, "max": 2},
                {"band": "critical", "min": 3, "max": 4},
            ],
            id="savok-rossz-sorrendben",
        ),
        pytest.param(
            [_scale()],
            [{"band": "normal", "min": 0, "max": 1}, {"band": "critical", "min": 2, "max": 4}],
            id="ket-sav",
        ),
        pytest.param([], _bands(1, 2, 3), id="ures-kerdeslista"),
        pytest.param([_scale()] * 21, _bands(2, 40, 84), id="21-kerdes"),
        pytest.param([_scale(text="x" * 301)], _bands(2, 3, 4), id="301-karakter"),
        pytest.param([_scale(text="   ")], _bands(2, 3, 4), id="ures-szoveg"),
        pytest.param([_scale(min_label="x" * 101)], _bands(2, 3, 4), id="hosszu-vegfelirat"),
    ],
)
def test_invalid_versions_are_422(client, db, setup, questions, bands):
    before = stored(db, setup["template"].id)
    body = {"base_version_no": 1, "questions": questions, "scoring_thresholds": bands}
    response = client.post(
        f"{URL}/{WELLBEING_CODE}/versions", json=body, headers=auth(setup["doctor"])
    )
    assert response.status_code == 422
    assert stored(db, setup["template"].id) == before


@pytest.mark.parametrize(
    ("questions", "bands"),
    [
        pytest.param([_scale(scale_max=10)], _bands(3, 6, 9), id="skala-1-10"),
        pytest.param([_scale()] * 20, _bands(2, 40, 80), id="20-kerdes"),
        pytest.param([_scale(text="x" * 300)], _bands(2, 3, 4), id="300-karakter"),
        pytest.param(
            [_single([OPTS[0], {**OPTS[1], "score": 10}])], _bands(1, 10, 10), id="pont-10"
        ),
        pytest.param(
            [{"question_type": "multi", "text": "Tünetek?", "options": OPTS}],
            _bands(1, 3, 3),
            id="tobbvalasztos",
        ),
    ],
)
def test_limits_are_inclusive(client, setup, questions, bands):
    body = {"base_version_no": 1, "questions": questions, "scoring_thresholds": bands}
    response = client.post(
        f"{URL}/{WELLBEING_CODE}/versions", json=body, headers=auth(setup["doctor"])
    )
    assert response.status_code == 201, response.json()


# --- Új kérdőív ----------------------------------------------------------------


def test_doctor_creates_a_questionnaire(client, db, setup):
    body = {
        "name": "  Új kérdőív  ",
        "questions": [_scale(), _single(OPTS)],
        "scoring_thresholds": _bands(2, 5, 7),
    }
    response = client.post(URL, json=body, headers=auth(setup["other"]))
    assert response.status_code == 201
    data = response.json()
    assert (data["code"], data["name"]) == ("uj_kerdoiv", "Új kérdőív")
    assert (data["current"]["version_no"], data["current"]["max_score"]) == (1, 7)
    template = db.scalar(
        select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == data["code"])
    )
    assert template.created_by == setup["other"].id
    listed = client.get(URL, headers=auth(setup["doctor"])).json()
    assert {"code": "uj_kerdoiv", "name": "Új kérdőív", "version_no": 1}.items() <= next(
        x for x in listed if x["code"] == "uj_kerdoiv"
    ).items()


def test_taken_code_is_409(client, setup):
    # A „Wellbeing" név kódja a meglévő „wellbeing".
    body = {"name": "Wellbeing", "questions": [_scale()], "scoring_thresholds": _bands(2, 3, 4)}
    response = client.post(URL, json=body, headers=auth(setup["doctor"]))
    assert response.status_code == 409
    assert response.json()["detail"] == {"code": "code_taken"}


@pytest.mark.parametrize("name", ["!!!", "New", "   "])
def test_name_without_a_usable_code_is_422(client, setup, name):
    body = {"name": name, "questions": [_scale()], "scoring_thresholds": _bands(2, 3, 4)}
    response = client.post(URL, json=body, headers=auth(setup["doctor"]))
    assert response.status_code == 422


def test_invalid_new_questionnaire_leaves_nothing_behind(client, db, setup):
    body = {"name": "Hibás", "questions": [_scale()], "scoring_thresholds": _bands(2, 3, 9)}
    assert client.post(URL, json=body, headers=auth(setup["doctor"])).status_code == 422
    assert (
        db.scalar(select(QuestionnaireTemplate).where(QuestionnaireTemplate.code == "hibas"))
        is None
    )


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("Közérzet", "kozerzet"),
        ("Fáradtság (heti) – PHQ-2", "faradtsag_heti_phq_2"),
        ("ŐŰ  öü", "ou_ou"),
        ("A" * 60, "a" * 50),
        ("new", ""),
        ("?!", ""),
    ],
)
def test_code_from_name(name, code):
    assert code_from_name(name) == code
