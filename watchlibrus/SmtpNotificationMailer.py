import smtplib
from email.mime.multipart import MIMEMultipart


class SmtpNotificationMailer(object):
    def __init__(self, smtp_config_section) -> None:
        self._from = smtp_config_section['from']
        self._to = smtp_config_section['to']
        self._subject_prefix = smtp_config_section.get('subject_prefix')
        self._host = smtp_config_section['host']
        self._port = int(smtp_config_section['port'])
        self._username = smtp_config_section['username']
        self._password = smtp_config_section['password']

    def send(self, subject: str, payload) -> None:
        session = None
        try:
            # Set up the email parameters
            message = MIMEMultipart()
            message["From"] = self._from
            message["To"] = self._to

            if self._subject_prefix:
                subject = self._subject_prefix + subject
            message["Subject"] = subject

            # Add the message body
            message.attach(payload)

            # Create the SMTP session
            session = smtplib.SMTP(self._host, self._port)
            session.starttls()
            session.login(self._username, self._password)

            # Send the email
            text = message.as_string()
            session.sendmail(self._from, self._to, text)
        finally:
            if session:
                session.quit()
