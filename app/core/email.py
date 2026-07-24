"""
Service d'envoi d'email via SMTP (Outlook Office365 ou autre).

Configuration via variables d'environnement :
  SMTP_HOST     : smtp.office365.com (Outlook) ou smtp.gmail.com
  SMTP_PORT     : 587 (STARTTLS)
  SMTP_USER     : votre adresse email
  SMTP_PASSWORD : votre mot de passe ou App Password
  SMTP_FROM     : adresse expéditeur affichée (défaut = SMTP_USER)
  SMTP_STARTTLS : true (recommandé)

Si SMTP_HOST est vide, les emails sont loggés mais non envoyés (mode dev).
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def send_email(to: str, subject: str, html_body: str) -> bool:
    """Envoie un email HTML. Retourne True si succès, False sinon."""
    if not settings.SMTP_HOST or not settings.SMTP_USER:
        logger.warning(
            "email.not_configured",
            to=to,
            subject=subject,
            hint="Définissez SMTP_HOST, SMTP_USER, SMTP_PASSWORD dans .env",
        )
        return False
    try:
        await asyncio.to_thread(_send_sync, to, subject, html_body)
        logger.info("email.sent", to=to, subject=subject)
        return True
    except Exception as exc:
        logger.error("email.send_failed", to=to, subject=subject, error=str(exc))
        return False


def _send_sync(to: str, subject: str, html_body: str) -> None:
    from_addr = settings.SMTP_FROM or settings.SMTP_USER
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    ctx = ssl.create_default_context()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        smtp.ehlo()
        if settings.SMTP_STARTTLS:
            smtp.starttls(context=ctx)
            smtp.ehlo()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.sendmail(from_addr, [to], msg.as_string())


# ── Templates HTML ────────────────────────────────────────────────────────────

def _base_layout(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f9;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:14px;border:1px solid #e2e8f0;overflow:hidden;">
        <!-- Header -->
        <tr><td style="background:linear-gradient(135deg,#1E318A,#6366f1);padding:28px 36px;">
          <h1 style="margin:0;font-size:26px;font-weight:900;color:#fff;letter-spacing:-0.5px;">aria</h1>
          <p style="margin:4px 0 0;font-size:11px;color:rgba(255,255,255,0.65);text-transform:uppercase;letter-spacing:2px;">Intelligence API Inversée</p>
        </td></tr>
        <!-- Body -->
        <tr><td style="padding:36px;">
          <h2 style="margin:0 0 16px;font-size:20px;font-weight:700;color:#1e293b;">{title}</h2>
          {content}
          <hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0 16px;">
          <p style="margin:0;font-size:12px;color:#94a3b8;">© 2026 ARIA · PFE — Cet email a été envoyé automatiquement, ne pas répondre.</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


async def send_password_reset_email(to: str, full_name: str, reset_link: str) -> bool:
    content = f"""
    <p style="margin:0 0 20px;color:#475569;font-size:15px;line-height:1.6;">
      Bonjour <strong>{full_name}</strong>,<br><br>
      Vous avez demandé la réinitialisation de votre mot de passe ARIA.
      Cliquez sur le bouton ci-dessous pour choisir un nouveau mot de passe.
      Ce lien est valable <strong>1 heure</strong>.
    </p>
    <table cellpadding="0" cellspacing="0" style="margin:0 0 24px;">
      <tr><td style="border-radius:10px;background:linear-gradient(135deg,#6366f1,#8b5cf6);">
        <a href="{reset_link}" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:700;color:#fff;text-decoration:none;">
          Réinitialiser mon mot de passe →
        </a>
      </td></tr>
    </table>
    <p style="margin:0;font-size:13px;color:#94a3b8;">
      Si vous n'avez pas fait cette demande, ignorez cet email — votre mot de passe reste inchangé.
    </p>"""
    return await send_email(
        to=to,
        subject="ARIA — Réinitialisation de votre mot de passe",
        html_body=_base_layout("Réinitialiser votre mot de passe", content),
    )
