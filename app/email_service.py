import os
import smtplib
import ssl
from email.message import EmailMessage
from html import escape


def get_required_environment(name):
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"A variável {name} não foi configurada."
        )

    return value


def send_verification_email(
    recipient,
    name,
    code,
):
    smtp_host = os.getenv(
        "SMTP_HOST",
        "smtp-relay.brevo.com",
    ).strip()

    smtp_port_value = os.getenv(
        "SMTP_PORT",
        "587",
    ).strip()

    smtp_username = (
        get_required_environment(
            "SMTP_USERNAME"
        )
    )

    smtp_password = (
        get_required_environment(
            "SMTP_PASSWORD"
        )
    )

    sender_email = (
        get_required_environment(
            "SMTP_EMAIL"
        )
        .lower()
    )

    recipient_email = (
        str(recipient)
        .strip()
        .lower()
    )

    if not recipient_email:
        raise RuntimeError(
            "O destinatário não foi informado."
        )

    try:
        smtp_port = int(smtp_port_value)
    except (TypeError, ValueError):
        raise RuntimeError(
            "SMTP_PORT precisa ser um número."
        )

    safe_name = escape(
        str(name).strip() or "usuário"
    )

    message = EmailMessage()

    message["Subject"] = (
        "Confirme seu e-mail — "
        "Controle de Aulas"
    )

    message["From"] = (
        f"Controle de Aulas <{sender_email}>"
    )

    message["To"] = recipient_email

    message.set_content(
        (
            f"Olá, {safe_name}!\n\n"
            "Seu código de confirmação é: "
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
            <head>
                <meta charset="UTF-8">
                <meta
                    name="viewport"
                    content="width=device-width"
                >
            </head>

            <body
                style="
                    margin: 0;
                    padding: 32px 16px;
                    background: #080d1a;
                    font-family: Arial, sans-serif;
                    color: #e5e7eb;
                "
            >
                <div
                    style="
                        max-width: 520px;
                        margin: 0 auto;
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
                            font-size: 15px;
                            line-height: 1.6;
                        "
                    >
                        Use o código abaixo para
                        confirmar seu e-mail no
                        Controle de Aulas.
                    </p>

                    <div
                        style="
                            margin: 22px 0;
                            padding: 20px;
                            background: #171f35;
                            border: 1px solid #313c57;
                            border-radius: 14px;
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
                            font-size: 14px;
                            line-height: 1.6;
                        "
                    >
                        O código expira em 10 minutos.
                    </p>

                    <p
                        style="
                            color: #758096;
                            font-size: 12px;
                            line-height: 1.6;
                        "
                    >
                        Se você não solicitou esta
                        conta, ignore esta mensagem.
                    </p>
                </div>
            </body>
        </html>
        """,
        subtype="html",
    )

    ssl_context = ssl.create_default_context()

    with smtplib.SMTP(
        host=smtp_host,
        port=smtp_port,
        timeout=20,
    ) as smtp:
        smtp.ehlo()

        smtp.starttls(
            context=ssl_context
        )

        smtp.ehlo()

        smtp.login(
            user=smtp_username,
            password=smtp_password,
        )

        refused_recipients = (
            smtp.send_message(message)
        )

        if refused_recipients:
            refused_addresses = ", ".join(
                refused_recipients.keys()
            )

            raise RuntimeError(
                "O servidor SMTP recusou os "
                f"destinatários: {refused_addresses}"
            )