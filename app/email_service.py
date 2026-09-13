import os
import smtplib
import ssl
from email.message import EmailMessage
from html import escape


def send_verification_email(
    recipient,
    name,
    code,
):
    smtp_email = (
        os.getenv("SMTP_EMAIL", "")
        .strip()
        .lower()
    )

    smtp_password = (
        os.getenv("SMTP_APP_PASSWORD", "")
        .replace(" ", "")
        .strip()
    )

    if not smtp_email:
        raise RuntimeError(
            "SMTP_EMAIL não foi configurado."
        )

    if not smtp_password:
        raise RuntimeError(
            "SMTP_APP_PASSWORD não foi configurado."
        )

    if len(smtp_password) != 16:
        raise RuntimeError(
            "SMTP_APP_PASSWORD deve possuir "
            "16 caracteres, sem espaços."
        )

    safe_name = escape(
        str(name).strip() or "usuário"
    )

    recipient_email = (
        str(recipient)
        .strip()
        .lower()
    )

    message = EmailMessage()

    message["Subject"] = (
        "Confirme seu e-mail — "
        "Controle de Aulas"
    )

    message["From"] = (
        f"Controle de Aulas <{smtp_email}>"
    )

    message["To"] = recipient_email

    message.set_content(
        (
            f"Olá, {safe_name}!\n\n"
            f"Seu código de confirmação é: "
            f"{code}\n\n"
            "O código expira em 10 minutos.\n\n"
            "Se você não solicitou esta conta, "
            "ignore esta mensagem."
        )
    )

    message.add_alternative(
        f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
            <body
                style="
                    margin: 0;
                    padding: 32px;
                    background: #080d1a;
                    font-family: Arial, sans-serif;
                    color: #e5e7eb;
                "
            >
                <div
                    style="
                        max-width: 520px;
                        margin: auto;
                        padding: 28px;
                        background: #0f1629;
                        border: 1px solid #273249;
                        border-radius: 20px;
                    "
                >
                    <h1
                        style="
                            margin: 0 0 12px;
                            color: #ffffff;
                            font-size: 24px;
                        "
                    >
                        Olá, {safe_name}!
                    </h1>

                    <p
                        style="
                            color: #aeb7c7;
                            line-height: 1.6;
                        "
                    >
                        Use o código abaixo para
                        confirmar seu e-mail no
                        Controle de Aulas.
                    </p>

                    <div
                        style="
                            padding: 22px 0;
                            color: #a78bfa;
                            font-size: 34px;
                            font-weight: 700;
                            letter-spacing: 8px;
                            text-align: center;
                        "
                    >
                        {code}
                    </div>

                    <p
                        style="
                            color: #aeb7c7;
                            line-height: 1.6;
                        "
                    >
                        O código expira em 10 minutos.
                        Se você não solicitou esta conta,
                        ignore esta mensagem.
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html",
    )

    ssl_context = ssl.create_default_context()

    with smtplib.SMTP_SSL(
        host="smtp.gmail.com",
        port=465,
        context=ssl_context,
        timeout=20,
    ) as smtp:
        smtp.login(
            user=smtp_email,
            password=smtp_password,
        )

        refused_recipients = smtp.send_message(
            message
        )

        if refused_recipients:
            raise RuntimeError(
                "O servidor recusou o destinatário."
            )