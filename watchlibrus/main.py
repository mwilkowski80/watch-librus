import datetime
import json
import logging
import smtplib
import sqlite3
from configparser import ConfigParser
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from subprocess import check_output, CalledProcessError
from tempfile import NamedTemporaryFile
from typing import Callable, List, TextIO

import click
from librus import LibrusSession, Lesson

from watchlibrus.SmtpNotificationMailer import SmtpNotificationMailer

config: ConfigParser


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


def build_send_smtp_notification_handler(_config: ConfigParser, config_section) -> Callable[[Message], None]:
    _log = logging.getLogger(__name__ + '.send_smtp_notification_handler')

    smtp_section_name = config_section['smtp_config_section']
    mailer = SmtpNotificationMailer(_config[smtp_section_name])

    def _get_content_as_html(m: Message) -> str:
        content_with_brs = m.content.replace('\n', '<br/>')
        return f"""
        <p><strong>From: </strong>{m.sender}</p>
        <p><strong>Sent at: </strong>{m.sent_at.isoformat()}</p>
        <p><strong>Content:</strong></p>{content_with_brs}"""

    def _send_smtp_notification(m: Message) -> None:
        mailer.send(m.subject, MIMEText(_get_content_as_html(m), _subtype='html', _charset='utf-8'))
        _log.debug(f'Notification {m.message_id} processed: SMTP mail sent')

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
        return nh_builder(config, config[nh_section_name])
    else:
        return nh_builder()


@click.group()
@click.option('--config-file', required=True, type=click.Path(exists=True))
@click.option('--debug/--no-debug', default=False)
@click.pass_context
def watchlibrus_main(ctx: click.Context, debug: bool, config_file: str) -> None:
    ctx.ensure_object(dict)
    basic_logging_config(debug)
    global config
    config = ConfigParser()
    config.read([config_file])


def basic_logging_config(debug: bool) -> None:
    logging_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=logging_level, format='%(asctime)s:%(levelname)s:%(name)s:%(message)s')
    global log
    log = logging.getLogger('watchlibrus')


@watchlibrus_main.command('capture-schedule')
@click.option('--output-file', required=True, type=click.File(mode='w'))
def cmd_capture_schedule(output_file: TextIO) -> None:
    json.dump(capture_schedule(), output_file, indent=2)


@watchlibrus_main.command('compare-schedule')
@click.option('--input-file', required=True, type=click.Path(file_okay=True, dir_okay=False))
def cmd_compare_schedule(input_file: str) -> None:
    def _send_notification(diff: str) -> None:
        mailer = SmtpNotificationMailer(config['smtp:1'])
        mailer.send('Zmiana planu lekcji', MIMEText(diff))

    with NamedTemporaryFile(mode='w') as f:
        json.dump(capture_schedule(), f, indent=2)
        f.flush()

        try:
            check_output(['diff', input_file, f.name])
        except CalledProcessError as err:
            diff_content = err.output.decode('utf-8').strip()
            print(diff_content)
            _send_notification(diff_content)


def capture_schedule() -> List[dict]:
    librus_section = config['librus']
    session = LibrusSession()
    session.login(librus_section['username'], librus_section['password'])
    lessons = session.schedule()
    return [to_dict(l) for l in lessons]


def to_dict(lesson: Lesson) -> dict:
    return {
        'name': lesson.name,
        'day': lesson.day,
        'hour': lesson.index,
        'time': lesson.time,
        'classroom': lesson.classroom,
        'teacher': lesson.teacher
    }


@watchlibrus_main.command('sync-messages')
def cmd_sync_messages():
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
    watchlibrus_main()
