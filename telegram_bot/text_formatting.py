"""Opt-in rule-driven Telegram presentation; journal stores the visible text."""
from html.parser import HTMLParser
from telegram import MessageEntity


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


class BoldTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = ''
        self.start = None
        self.spans = []

    def handle_starttag(self, tag, attrs):
        if tag != 'b' or attrs or self.start is not None:
            raise ValueError('Unsupported presentation markup')
        self.start = len(self.text)

    def handle_endtag(self, tag):
        if tag != 'b' or self.start is None:
            raise ValueError('Unbalanced presentation markup')
        self.spans.append((self.start, len(self.text)))
        self.start = None

    def handle_data(self, text):
        self.text += text


def prepare_text(answer, rule):
    config = next((f['template'] for f in (rule or {}).get('fields', [])
                   if isinstance(f.get('template'), dict)), {})
    if config.get('telegram_format') != 'html_bold':
        return answer, []
    parser = BoldTextParser()
    parser.feed(answer)
    parser.close()
    if parser.start is not None:
        raise ValueError('Unclosed presentation markup')
    return parser.text, parser.spans


def message_chunks(text, spans, limit):
    # Telegram entity offsets/lengths and message limits use UTF-16 code units.
    start = 0
    while start < len(text):
        end = start
        size = 0
        while end < len(text) and size + utf16_length(text[end]) <= limit:
            size += utf16_length(text[end])
            end += 1
        if end == start:
            raise ValueError('Message limit too small')
        entities = []
        for a,b in spans:
            left,right = max(a,start),min(b,end)
            if left < right:
                entities.append(MessageEntity('bold',utf16_length(text[start:left]),
                                               utf16_length(text[left:right])))
        yield text[start:end], entities
        start = end
