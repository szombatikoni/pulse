"""Az orvosnak szóló e-mail-értesítés kézbesítése (M3, A9; F19, NF3).

„Kimenő postafiók" minta, két lépésben:

1. Sorba állítás (queue_alert_email): új riasztásnál (CREATED, a
   rules._raise_alert hívja) a beteghez éppen rendelt minden aktív orvosnak egy
   `pending` sor, ugyanabban a tranzakcióban, mint a riasztás. Visszagördülésnél
   sor sincs, commitnál biztosan megvan. Ismételt aktiválódás és
   súlyosság-emelkedés nem küld levelet (a hallgató döntése, D1).
2. Kézbesítés (deliver_due): a háttérfolyamat kézbesítő köre a lejárt
   `pending` sorokat egyenként zárolja (SELECT … FOR UPDATE SKIP LOCKED), elküldi,
   és soronként commitol. Legfeljebb MAX_ATTEMPTS kísérlet, közte
   RETRY_DELAYS várakozással; utána a sor `failed` marad (kézbesítési napló),
   újraküldés nincs (D3).

A levél nem tartalmaz betegadatot (D4): se nevet, se mért értéket, se
pontszámot, se szabálynevet, se azonosítót; csak a súlyosságot, az időpontot és
a Riasztások oldal címét. A szöveg a küldéskor áll elő a riasztásból.

Ismert korlát (legalább egyszeri kézbesítés): ha a küldés sikerül, de az utána
következő commit nem, a sor `pending` marad, és a levél egyszer megismétlődhet.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Alert,
    DeliveryKind,
    DeliveryStatus,
    NotificationDelivery,
    Severity,
    User,
)
from app.models.notification_delivery import LAST_ERROR_MAX
from app.services.access import assigned_doctors_query

# Legfeljebb ennyi küldési kísérlet (D3).
MAX_ATTEMPTS = 3
# Várakozás az 1. és a 2. sikertelen kísérlet után; a 3. után a sor `failed`.
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5))
# Egy kézbesítő kör legfeljebb ennyi sort dolgoz fel (a maradék a következő körre marad).
ROUND_LIMIT = 100

# A hónapok magyar neve a levél időpontjához, a rendszer területi beállításától
# (locale) függetlenül (a hallgató döntése, 2026-11-21).
HU_MONTHS = (
    "január",
    "február",
    "március",
    "április",
    "május",
    "június",
    "július",
    "augusztus",
    "szeptember",
    "október",
    "november",
    "december",
)

# A súlyosság a felület szóhasználatával (a szabályszerkesztő „Súlyosság" mezője).
SEVERITY_LABELS = {Severity.MODERATE: "Közepes", Severity.SEVERE: "Súlyos"}

# A küldő függvény: (címzett, tárgy, törzs). A valódi a mailer.send_email; a
# tesztek hamisat adnak át, amely hibát is szimulálhat.
SendFn = Callable[[str, str, str], None]


def queue_alert_email(db: Session, alert: Alert, now: datetime) -> list[NotificationDelivery]:
    """Egy `pending` kézbesítési sor a beteghez `now` pillanatban rendelt minden
    aktív orvosnak (assigned_doctors_query). A sorokat csak a sessionhöz adja;
    a commit a riasztást létrehozó hívóé, így a sor a riasztással együtt
    születik vagy gördül vissza. A címzett címe a küldéskor olvasódik."""
    doctors = db.scalars(assigned_doctors_query(alert.patient_id, now)).all()
    rows = [
        NotificationDelivery(
            kind=DeliveryKind.ALERT_CREATED,
            alert_id=alert.id,
            recipient_user_id=doctor.user_id,
            status=DeliveryStatus.PENDING,
            attempts=0,
            next_attempt_at=now,
            created_at=now,
        )
        for doctor in doctors
    ]
    db.add_all(rows)
    return rows


def hungarian_datetime(at: datetime) -> str:
    """Időpont a rendszer időzónájában (Europe/Budapest), magyar írásmóddal, pl.
    „2026. október 12. 10:00" (a nap kezdő nulla nélkül)."""
    local = at.astimezone(settings.tz)
    return f"{local.year}. {HU_MONTHS[local.month - 1]} {local.day}. {local:%H:%M}"


def alert_email(alert: Alert) -> tuple[str, str]:
    """A levél tárgya és törzse, betegadat nélkül (D4). Az időpont a rendszer
    időzónájában (Europe/Budapest), magyar írásmóddal (hungarian_datetime)."""
    severity = SEVERITY_LABELS[alert.severity]
    when = hungarian_datetime(alert.created_at)
    link = f"{settings.app_base_url.rstrip('/')}/doctor/alerts"
    subject = f"PULSE: új riasztás ({severity})"
    body = (
        "Egy betegénél új riasztás keletkezett.\n"
        "\n"
        f"Súlyosság: {severity}\n"
        f"Időpont: {when} (magyar idő szerint)\n"
        "\n"
        f"A részletek bejelentkezés után: {link}\n"
        "\n"
        "Ez a PULSE demonstrációs rendszer automatikus levele, kizárólag mesterséges "
        "adatokkal. A rendszer nem orvosi eszköz, és nem helyettesíti az orvosi döntést. "
        "Kérjük, erre a levélre ne válaszoljon.\n"
    )
    return subject, body


@dataclass
class DeliveryRound:
    """Egy kézbesítő kör eredménye."""

    sent: int = 0
    retrying: int = 0  # sikertelen, de még újrapróbálandó
    failed: int = 0  # végleg sikertelen (az utolsó kísérlet után)
    skipped: int = 0  # küldés nélkül lezárva (a címzett már nem aktív)

    @property
    def processed(self) -> int:
        return self.sent + self.retrying + self.failed + self.skipped


def claim_next(db: Session, now: datetime) -> NotificationDelivery | None:
    """A legrégebben esedékes, lejárt `pending` sor, sorzárral. A más tranzakció
    által már zárolt sort átugorja (SKIP LOCKED), így két egyidejű kör nem
    küldi el ugyanazt a sort kétszer."""
    return db.scalar(
        select(NotificationDelivery)
        .where(
            NotificationDelivery.status == DeliveryStatus.PENDING,
            NotificationDelivery.next_attempt_at <= now,
        )
        .order_by(NotificationDelivery.next_attempt_at, NotificationDelivery.id)
        .limit(1)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )


def _short_error(exc: Exception) -> str:
    """A hiba rövid leírása a naplóba. A levél nem tartalmaz betegadatot, így
    az SMTP-hibaüzenet sem tartalmazhat."""
    return f"{type(exc).__name__}: {exc}"[:LAST_ERROR_MAX]


def _deliver(
    db: Session, row: NotificationDelivery, now: datetime, send: SendFn, result: DeliveryRound
) -> None:
    recipient = db.get(User, row.recipient_user_id)
    if recipient is None or not recipient.is_active:
        # A sorba állítás óta letiltott fiókra nem küldünk; a sor lezárul,
        # különben minden körben újra felvennénk.
        row.status = DeliveryStatus.FAILED
        row.last_error = "a címzett nem aktív; küldés nélkül lezárva"
        result.skipped += 1
        return
    row.attempts += 1
    row.last_attempt_at = now
    try:
        # A levél összeállítása is a kísérlet része: ha bármi váratlan hiba
        # történik (pl. hiányzó riasztás vagy súlyosság-felirat), az is
        # sikertelen kísérletnek számít. Így egy hibás sor nem ragad a sor
        # elején, a kör a többit is kézbesíti.
        alert = db.get(Alert, row.alert_id) if row.alert_id is not None else None
        if alert is None:
            raise LookupError("a sorhoz nem tartozik riasztás")
        subject, body = alert_email(alert)
        send(recipient.email, subject, body)
    except Exception as exc:
        row.last_error = _short_error(exc)
        if row.attempts >= MAX_ATTEMPTS:
            row.status = DeliveryStatus.FAILED
            result.failed += 1
        else:
            row.next_attempt_at = now + RETRY_DELAYS[row.attempts - 1]
            result.retrying += 1
        return
    row.status = DeliveryStatus.SENT
    result.sent += 1


def deliver_due(
    db: Session, now: datetime | None, send: SendFn, limit: int = ROUND_LIMIT
) -> DeliveryRound:
    """Egy kézbesítő kör: a lejárt `pending` sorok egyenként (claim_next),
    mindegyik után commit.

    Az idő: `now=None` esetén (a háttérfolyamat így hívja) minden sor a saját
    kísérletének tényleges idejét kapja (last_attempt_at, és ebből számítódik
    az újrapróbálás ideje); a tesztek rögzített, szimulált időt adnak át.

    A soronkénti commit szándékos (eltér a szolgáltatások „csak flush, a commit
    a hívóé" szokásától): a zár csak az épp küldött soron van, egy későbbi sor
    hibája nem görgeti vissza a már elküldöttek állapotát, és egy megszakadt
    kör legfeljebb egy levelet ismételhet meg. A sikertelen sor
    next_attempt_at-je a jövőbe kerül (RETRY_DELAYS), így rögzített `now`
    mellett ugyanebben a körben nem jön újra; `now=None` esetén csak akkor,
    ha a kör tovább tart, mint a várakozás (akkor is legfeljebb a kísérletek
    számáig, és a kör legfeljebb ROUND_LIMIT sort dolgoz fel)."""
    result = DeliveryRound()
    for _ in range(limit):
        at = now or datetime.now(UTC)
        row = claim_next(db, at)
        if row is None:
            break
        _deliver(db, row, at, send, result)
        db.commit()
    return result
