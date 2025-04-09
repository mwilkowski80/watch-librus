import datetime
import json
import logging
import sqlite3
from configparser import ConfigParser
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Callable, List, TextIO, Optional

import click
from watchlibrus.librus import LibrusSession, Lesson as LibrusLesson
from watchlibrus.SmtpNotificationMailer import SmtpNotificationMailer
from watchlibrus.lessonplan import LessonPlan, Lesson
from watchlibrus.renderer import Renderer

log = logging.getLogger(__name__)
config: ConfigParser = None


@dataclass
class Message(object):
    message_id: str
    sender: str
    subject: str
    sent_at: datetime.datetime
    content: str


def send_notifications(conn, consumer):
    _log = logging.getLogger(__name__ + '.send_notifications')
    c = conn.cursor()
    c.execute('SELECT id, content, created_at, sender, subject, sent_at, notified_at '
              'FROM messages WHERE notified_at IS NULL')
    for r in c.fetchall():
        m = Message(
            message_id=r[0],
            content=r[1],
            sender=r[3],
            subject=r[4],
            sent_at=datetime.datetime.fromisoformat(r[5])
        )
        consumer(m)
        c.execute('UPDATE messages SET notified_at = ? WHERE id = ?',
                  (datetime.datetime.now().isoformat(), m.message_id))
        _log.info('Processed notification for %s', m.message_id)


def build_send_smtp_notification_handler(_config: ConfigParser, config_section) -> Callable[[Message], None]:
    _log = logging.getLogger(__name__ + '.send_smtp_notification_handler')
    smtp_section_name = config_section['smtp_config_section']
    mailer = SmtpNotificationMailer(_config[smtp_section_name])

    def _get_content_as_html(m: Message) -> str:
        content_with_brs = m.content.replace('\n', '<br/>')
        return (
            f"<p><strong>From: </strong>{m.sender}</p>"
            f"<p><strong>Sent at: </strong>{m.sent_at.isoformat()}</p>"
            f"<p><strong>Content:</strong></p>{content_with_brs}"
        )

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


def build_notification_handler(conf) -> Callable[[Message], None]:
    nh_name = conf['general']['notification_handler']
    nh_builder = NOTIFICATION_HANDLER_BUILDERS[nh_name]
    nh_section_name = 'notification_handler:' + nh_name
    if nh_section_name in conf:
        return nh_builder(conf, conf[nh_section_name])
    else:
        return nh_builder()


@click.group()
@click.option('--config-file', required=True, type=click.Path(exists=True))
@click.option('--debug/--no-debug', default=False)
@click.pass_context
def watchlibrus_main(ctx: click.Context, debug: bool, config_file: str) -> None:
    """Watch Librus for schedule changes and send notifications."""
    ctx.ensure_object(dict)
    basic_logging_config(debug)
    global config
    config = ConfigParser()
    config.read([config_file])


def basic_logging_config(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s:%(levelname)s:%(name)s:%(message)s'
    )


@watchlibrus_main.command('capture-schedule')
@click.option('--output-file', required=True, type=click.File(mode='w'))
@click.option('--when', required=False,
              help="ISO date (YYYY-MM-DD) or +N / -N. Defaults to today if not provided.")
def cmd_capture_schedule(output_file: TextIO, when: Optional[str]) -> None:
    """Capture the schedule for a specific date or date range."""
    target_date = parse_when(when) if when else datetime.date.today()
    if target_date.weekday() >= 5:
        raise click.ClickException(f"Weekend not allowed: {target_date.isoformat()}")

    librus_section = config['librus']
    session = LibrusSession()
    session.login(librus_section['username'], librus_section['password'])

    try:
        lessons = session.schedule_for_date(target_date)
    except ValueError as e:
        raise click.ClickException(str(e)) from e

    lesson_plan = LessonPlan(lessons=[Lesson.from_librus_lesson(x) for x in lessons])
    json.dump(lesson_plan.to_list(), output_file, indent=2)
    log.info("Plan saved to file.")


@watchlibrus_main.command('compare-schedule')
@click.option('--input-file', required=True,
              type=click.Path(exists=True, file_okay=True, dir_okay=False))
@click.option('--when', required=True,
              help="ISO date (YYYY-MM-DD) or +N / -N. +0=today, +1=tomorrow, etc.")
def cmd_compare_schedule(input_file: str, when: str) -> None:
    """Compare schedule changes for a specific date."""
    def _send_notification(diff_html: str, day_date: datetime.date) -> None:
        weekday_str = day_date.strftime('%A')
        subj = f"Schedule changed – {day_date.isoformat()} ({weekday_str})"
        mailer = SmtpNotificationMailer(config['smtp:1'])
        mailer.send(subj, MIMEText(diff_html, _subtype='html', _charset='utf-8'))

    with open(input_file, 'r') as f:
        old_plan_dict = json.load(f)
    old_plan = LessonPlan.from_dict_list(old_plan_dict)

    target_date = parse_when(when)
    if target_date.weekday() >= 5:
        raise click.ClickException(f"Weekend not allowed: {target_date.isoformat()}")

    librus_section = config['librus']
    session = LibrusSession()
    session.login(librus_section['username'], librus_section['password'])

    try:
        new_lessons = session.schedule_for_date(target_date)
    except ValueError as e:
        raise click.ClickException(str(e)) from e

    day_of_week = target_date.weekday()
    old_plan_day = old_plan.filter_by_day(day_of_week)
    new_plan_day = LessonPlan(lessons=[Lesson.from_librus_lesson(l) for l in new_lessons if l.day == day_of_week])

    compare_result = old_plan_day.compare(new_plan_day)
    if compare_result.is_change():
        mail_content = Renderer().render('lesson-plan-change-notification.html', {
            'lesson_pairs': [(ld.l1, ld.l2) for ld in compare_result.lesson_deltas],
            'day_date': target_date,
        })
        _send_notification(mail_content, target_date)
        log.info("Changes detected for %s. Notification sent.", target_date.isoformat())
    else:
        log.info("No changes for %s.", target_date.isoformat())


def parse_when(when_value: str) -> datetime.date:
    """Parse date from string in format YYYY-MM-DD or +N/-N (days from today)."""
    today = datetime.date.today()
    if when_value.startswith('+') or when_value.startswith('-'):
        try:
            offset = int(when_value)
        except ValueError:
            raise click.ClickException(f"Invalid offset: {when_value}")
        return today + datetime.timedelta(days=offset)
    else:
        try:
            return datetime.date.fromisoformat(when_value)
        except ValueError:
            raise click.ClickException(f"Invalid date format: {when_value}")


@watchlibrus_main.command('sync-messages')
def cmd_sync_messages():
    """Synchronize messages from Librus and send notifications."""
    notification_handler = build_notification_handler(config)
    conn = sqlite3.connect(config['sqlite3']['messages_db_path'])
    try:
        sync_messages(conn, config['librus'])
        send_notifications(conn, notification_handler)
        conn.commit()
    finally:
        conn.close()


def sync_messages(conn, config_section):
    """Synchronize messages from Librus to local database."""
    _log = logging.getLogger(__name__ + '.sync_messages')

    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (id TEXT PRIMARY KEY,
                  content TEXT,
                  created_at TEXT,
                  sender TEXT,
                  subject TEXT,
                  sent_at TEXT,
                  notified_at TEXT)''')
    messages = capture_messages_from_librus(config_section['username'], config_section['password'])
    _log.info(f'Captured {len(messages)} messages from Librus')

    new_ids = set(m.message_id for m in messages)
    query = "SELECT id FROM messages WHERE id IN ({})".format(','.join('?' for _ in new_ids))
    c.execute(query, tuple(new_ids))
    existing_ids = set(row[0] for row in c.fetchall())

    for message in messages:
        if message.message_id not in existing_ids:
            c.execute(
                "INSERT INTO messages (id, content, created_at, sender, subject, sent_at, notified_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    message.message_id,
                    message.content,
                    datetime.datetime.now().isoformat(),
                    message.sender,
                    message.subject,
                    message.sent_at.isoformat(),
                    None
                )
            )
            _log.info('Added message %s', message.message_id)


def capture_messages_from_librus(username: str, password: str) -> List[Message]:
    """Capture messages from Librus."""
    session = LibrusSession()
    session.login(username, password)
    out = []
    for m in session.list_messages(get_content=True):
        out.append(Message(
            message_id=m.message_id,
            sender=m.sender,
            subject=m.subject,
            sent_at=m.sent_at,
            content=m.content or ""
        ))
    return out


if __name__ == '__main__':
    watchlibrus_main(obj={})
