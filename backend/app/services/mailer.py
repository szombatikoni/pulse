"""E-mail küldése SMTP-n (M3, A9), a Python beépített smtplib-jével.

A küldés a háttérfolyamat kézbesítő körében fut (services/deliveries.py,
deliver_due), soha nem a kérés vagy a riasztás tranzakciójában. A fejlesztői és
a demókörnyezetben a cél a Mailpit (docker-compose.yml), amely valódi címre nem
továbbít. Üres SMTP_HOST mellett a küldés ki van kapcsolva (sending_enabled).
"""

from email.message import EmailMessage
from email.utils import formatdate
from smtplib import SMTP

from app.core.config import settings

# Egy SMTP-kapcsolat (felépítés és küldés) legfeljebb ennyi másodpercig tarthat.
SMTP_TIMEOUT_SECONDS = 10


def sending_enabled() -> bool:
    """Be van-e állítva SMTP-kiszolgáló (SMTP_HOST nem üres)."""
    return bool(settings.smtp_host.strip())


def build_message(to: str, subject: str, body: str) -> EmailMessage:
    """A levél a feladóval és a dátummal; a nem ASCII fejlécet és törzset az
    email csomag kódolja (UTF-8)."""
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message.set_content(body)
    return message


def send_email(to: str, subject: str, body: str) -> None:
    """Egy levél elküldése a beállított SMTP-kiszolgálón keresztül. Hibánál
    kivételt dob (pl. ConnectionRefusedError, smtplib.SMTPException); az
    újrapróbálkozásról a hívó (deliver_due) dönt."""
    with SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        smtp.send_message(build_message(to, subject, body))
