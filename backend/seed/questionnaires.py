"""A demókérdőív: a működési szabályok példája (07_mukodesi_szabalyok.md, 4. rész).

Pontozás: több pont = rosszabb állapot, a skála jobb vége 0 pont. A
legnagyobb elérhető pontszám 4 + 4 + 5 = 13. A kiértékelési sávok a verzió
részei: 0–5 rendben, 6–10 figyelmeztető, 11–13 kritikus.
"""

from app.services.questionnaires import VersionSpec

WELLBEING_CODE = "wellbeing"
WELLBEING_NAME = "Közérzet"

WELLBEING_V1 = VersionSpec.model_validate(
    {
        "questions": [
            {
                "question_type": "scale",
                "text": "Hogyan aludt az elmúlt éjszaka?",
                "scale_min": 1,
                "scale_max": 5,
                "good_end": "max",
                "min_label": "nagyon rosszul",
                "max_label": "nagyon jól",
            },
            {
                "question_type": "scale",
                "text": "Mennyire fáradt ma?",
                "scale_min": 1,
                "scale_max": 5,
                "good_end": "min",
                "min_label": "egyáltalán nem",
                "max_label": "nagyon",
            },
            {
                "question_type": "single",
                "text": "Tapasztalt-e szédülést az elmúlt héten?",
                "options": [
                    {"value": "never", "label": "Nem", "score": 0},
                    {"value": "rarely", "label": "Ritkán", "score": 2},
                    {"value": "daily", "label": "Naponta", "score": 5},
                ],
            },
        ],
        "scoring_thresholds": [
            {"band": "normal", "min": 0, "max": 5},
            {"band": "warning", "min": 6, "max": 10},
            {"band": "critical", "min": 11, "max": 13},
        ],
    }
)
