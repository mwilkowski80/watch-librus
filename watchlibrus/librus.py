import datetime
import logging
from urllib.parse import urljoin
import requests_html

logger = logging.getLogger(__name__)

class LibrusSession(object):
    def __init__(self):
        self._html_session = None

    def login(self, username, password):
        self._html_session = requests_html.HTMLSession()
        initial = self._html_session.get(
            url='https://api.librus.pl/OAuth/Authorization?client_id=46&response_type=code&scope=mydata'
        )
        response = self._html_session.post(
            url='https://api.librus.pl/OAuth/Authorization?client_id=46',
            data={'action': 'login', 'login': username, 'pass': password}
        )
        data = response.json()
        if data.get('status') != 'ok' or not data.get('goTo'):
            raise RuntimeError("Login failed (invalid credentials or unexpected format).")

        self._html_session.get(url=urljoin(response.url, data['goTo']))

    def schedule(self):
        url = 'https://synergia.librus.pl/przegladaj_plan_lekcji'
        response = self._html_session.get(url=url)
        lessons = self._parse_schedule_html(response.html)
        lessons.sort(key=lambda x: (x.day, x.index))
        return lessons

    def schedule_for_date(self, date: datetime.date):
        if date.weekday() >= 5:
            raise ValueError(f"Weekend not supported: {date.isoformat()}")

        start_of_week = date - datetime.timedelta(days=date.weekday())
        end_of_week = start_of_week + datetime.timedelta(days=6)
        tydzien_str = f"{start_of_week.isoformat()}_{end_of_week.isoformat()}"
        logger.debug(f"schedule_for_date: tydzien={tydzien_str}")

        html_obj = self._fetch_schedule_html(tydzien_str)
        lessons = self._parse_schedule_html(html_obj)
        if not lessons:
            raise ValueError(f"No schedule found for {tydzien_str}")

        filtered = [ls for ls in lessons if ls.day < 5]
        return filtered

    def _fetch_schedule_html(self, tydzien_str: str):
        url = 'https://synergia.librus.pl/przegladaj_plan_lekcji'
        data = {
            'tydzien': tydzien_str,
            'pokaz_zajecia_zsk': 'on',
            'pokaz_zajecia_ni': 'on',
            'pokaz_zajecia_dzd': 'on',
        }
        response = self._html_session.post(url, data=data)
        return response.html

    def _parse_schedule_html(self, html_obj):
        lessons = []
        table_rows = html_obj.find('table.decorated.plan-lekcji tr.line1')
        for row in table_rows:
            cells = row.find('td')
            if len(cells) < 1:
                continue

            try:
                index_lekcji = int(cells[0].text.strip())
            except ValueError:
                continue

            ths = row.find('th')
            if not ths:
                continue
            time_range = ths[0].text.strip()

            for day_idx in range(1, len(cells)):
                cell = cells[day_idx]
                day_in_week = day_idx - 1

                # Check if "odwołane" is present
                cell_html = cell.html.lower() if cell.html else ""
                is_canceled = ("odwołane" in cell_html)

                text_divs = cell.find('div.text')
                if not text_divs:
                    # Even if there's no div.text, we might mark it canceled if we want?
                    # But usually no lesson means skip
                    continue

                subject_names = []
                teachers = []
                classrooms = []

                for div_text in text_divs:
                    raw = div_text.text
                    parts = raw.split('-', maxsplit=1)
                    subject_part = parts[0].strip()
                    teacher_part = parts[1].strip() if len(parts) > 1 else ""

                    classroom_parsed = None
                    if 's.' in teacher_part:
                        subparts = teacher_part.split('s.')
                        teacher_str = subparts[0].strip()
                        classroom_parsed = subparts[1].strip() if len(subparts) > 1 else None
                    else:
                        teacher_str = teacher_part

                    subject_names.append(subject_part)
                    teachers.append(teacher_str)
                    if classroom_parsed:
                        classrooms.append(classroom_parsed)

                name_joined = " / ".join(subject_names)
                teacher_joined = " / ".join(teachers) if teachers else None
                classroom_joined = " / ".join(classrooms) if classrooms else None

                lesson = Lesson(
                    day=day_in_week,
                    index=index_lekcji,
                    subject=name_joined,
                    time=time_range,
                    teacher=teacher_joined,
                    classroom=classroom_joined
                )
                # Set 'is_canceled' if found
                lesson.is_canceled = is_canceled

                lessons.append(lesson)

        return lessons

    def list_messages(self, get_content=False):
        response = self._html_session.get(url='https://synergia.librus.pl/wiadomosci')
        rows = response.html.find('.stretch > tbody > tr')
        for row in rows:
            cells = row.find('td')
            if len(cells) < 5:
                continue
            href_el = cells[3].find('a')
            if not href_el:
                continue

            href = href_el[0].attrs.get('href', '').strip()
            sender = cells[2].text
            subject = cells[3].text
            raw_sent_at = cells[4].text
            try:
                sent_at = datetime.datetime.strptime(raw_sent_at, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                logger.warning(f"Cannot parse date: {raw_sent_at}")
                continue

            style = cells[3].attrs.get('style', '')
            is_read = ('font-weight: bold' not in style)

            msg = Message(href, sender, subject, sent_at, is_read)
            if get_content:
                url_msg = 'https://synergia.librus.pl' + href
                msg_html = self._html_session.get(url=url_msg).html.find('.container-message-content')
                msg.content = msg_html[0].text if msg_html else ""
            yield msg

class Lesson(object):
    def __init__(self, day, index, subject, time, teacher, classroom):
        self.day = day
        self.index = index
        self.name = subject
        self.time = time
        self.teacher = teacher
        self.classroom = classroom
        self.is_canceled = False

class Message(object):
    def __init__(self, message_id, sender, subject, sent_at, is_read):
        self.message_id = message_id
        self.sender = sender
        self.subject = subject
        self.sent_at = sent_at
        self.is_read = is_read
        self.content = None