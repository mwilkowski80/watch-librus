import datetime
import logging
import smtplib
import sqlite3
from configparser import ConfigParser
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Callable, List

import click
from librus import LibrusSession


@dataclass
@dataclass
class Message(object):
    message_id: str
    sender: str
    subject: str
    sent_at: datetime.datetime
    content: str


def send_notifications(conn, consumer):
    log = logging.getLogger(__name__ + '.send_notifications')
    c = conn.cursor()
    c.execute('SELECT id, content, created_at, sender, subject, sent_at, notified_at'
              ' FROM messages WHERE notified_at IS NULL')
    for r in c.fetchall():
        m = Message(message_id=r[0], content=r[1], sender=r[3], subject=r[4],
                    sent_at=datetime.datetime.fromisoformat(r[5]))
        consumer(m)
        c.execute('UPDATE messages SET notified_at = ? WHERE id = ?',
                  (datetime.datetime.now().isoformat(), m.message_id))
        log.info('Processed notification for %s', m.message_id)


def build_send_smtp_notification_handler(config_section) -> Callable[[Message], None]:
    log = logging.getLogger(__name__ + '.send_smtp_notification_handler')
    subject_prefix = config_section['subject_prefix']

    def _get_content_as_html(m: Message) -> str:
        content_with_brs = m.content.replace('\n', '<br/>')
        return f"""
        <p><strong>From: </strong>{m.sender}</p>
        <p><strong>Sent at: </strong>{m.sent_at.isoformat()}</p>
        <p><strong>Content:</strong></p>{content_with_brs}"""

    def _send_smtp_notification(m: Message) -> None:
        session = None
        try:
            # Set up the email parameters
            message = MIMEMultipart()
            message["From"] = config_section['from']
            message["To"] = config_section['to']
            message["Subject"] = f'{subject_prefix}{m.subject}'

            # Add the message body
            message.attach(MIMEText(_get_content_as_html(m), _subtype='html', _charset='utf-8'))

            # Create the SMTP session
            session = smtplib.SMTP("smtp.gmail.com", 587)
            session.starttls()
            session.login(config_section['username'], config_section['password'])

            # Send the email
            text = message.as_string()
            session.sendmail(config_section['from'], config_section['to'], text)
            log.debug(f'Notification {m.message_id} processed: SMTP mail sent')
        finally:
            if session:
                session.quit()

    return _send_smtp_notification


def build_noop_notification_handler() -> Callable[[Message], None]:
    log = logging.getLogger(__name__ + '.noop_notification_handler')

    def _noop_notification_handler(m: Message) -> None:
        log.debug(f'Notification {m.message_id} processed: noop')

    return _noop_notification_handler


NOTIFICATION_HANDLER_BUILDERS = {
    'smtp': build_send_smtp_notification_handler,
    'noop': build_noop_notification_handler,
}


def build_notification_handler(config) -> Callable[[Message], None]:
    nh_name = config['general']['notification_handler']
    nh_builder = NOTIFICATION_HANDLER_BUILDERS[nh_name]
    nh_section_name = 'notification_handler:' + nh_name
    if nh_section_name in config:
        return nh_builder(config[nh_section_name])
    else:
        return nh_builder()


@click.command
@click.argument('CONFIG_FILE', required=True, type=click.Path(exists=True))
@click.option('--debug', is_flag=True)
def main(config_file: str, debug: bool):
    logging_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=logging_level, format='%(asctime)s:%(levelname)s:%(name)s:%(message)s')
    config = ConfigParser()
    config.read(config_file)

    notification_handler = build_notification_handler(config)
    conn = sqlite3.connect(config['sqlite3']['messages_db_path'])
    try:
        sync_messages(conn, config['librus'])
        send_notifications(conn, notification_handler)
        conn.commit()
    finally:
        if conn:
            conn.close()


def capture_messages_from_librus(username: str, password: str) -> List[Message]:
    session = LibrusSession()
    session.login(username, password)
    return [Message(
        message_id=m.message_id,
        sender=m.sender,
        subject=m.subject,
        sent_at=m.sent_at,
        content=m.content,
    ) for m in session.list_messages(get_content=True)]


def sync_messages(conn, config_section):
    log = logging.getLogger(__name__ + '.sync_messages')
    # Connect to the SQLite database
    c = conn.cursor()
    # Create the messages table if it doesn't exist
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                     (id TEXT PRIMARY KEY, content TEXT, created_at TEXT, sender TEXT, subject TEXT, sent_at TEXT, notified_at TEXT)''')
    # Get the last message ID stored in the database
    c.execute('SELECT id FROM messages ORDER BY id DESC LIMIT 1')
    last_id = c.fetchone()
    if last_id:
        last_id = last_id[0]
    else:
        last_id = 0

    messages = capture_messages_from_librus(config_section['username'], config_section['password'])
    log.info(f'Captured %s messages from Librus', len(messages))
    # Check which messages are not already in the database
    new_message_ids = set(message.message_id for message in messages)
    c.execute("SELECT id FROM messages WHERE id IN ({})".format(
        ','.join(['?' for _ in new_message_ids])), tuple(new_message_ids))
    existing_message_ids = set(row[0] for row in c.fetchall())
    # Store the new messages in the database
    for message in messages:
        if message.message_id not in existing_message_ids:
            c.execute("INSERT INTO messages (id, content, created_at, sender, subject, sent_at, notified_at)"
                      " VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (message.message_id, message.content, datetime.datetime.now().isoformat(),
                       message.sender, message.subject, message.sent_at.isoformat(), None))
            log.info(f'Added message %s', message.message_id)


if __name__ == '__main__':
    main()
