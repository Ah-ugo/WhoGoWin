import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from fastapi import HTTPException, status


async def send_email(to_email: str, subject: str, body: str):

    smtp_server = "smtp.gmail.com"
    smtp_port = 465
    email_address = "ahuekweprinceugo@gmail.com"
    smtp_password = os.getenv("GMAIL_PASS")

    if not smtp_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SMTP password is not configured. Please set GMAIL_PASS environment variable."
        )

    # Create the email message
    msg = MIMEMultipart()
    msg['From'] = email_address
    msg['To'] = to_email
    msg['Subject'] = subject

    # Attach HTML body
    msg.attach(MIMEText(body, 'html'))

    try:
        # Connect to SMTP server with SSL
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.ehlo()
            server.login(email_address, smtp_password)
            server.send_message(msg)
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send email: {str(e)}"
        )