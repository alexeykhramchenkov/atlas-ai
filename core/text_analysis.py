"""Shared identity of buyer texts; no storage or LLM access."""
import hashlib
import json
import re

ANALYSIS_VERSION = 'buyer-text-v1'
TEXT_FIELDS = {'review':('text','pros','cons'), 'question':('question_text',)}


def text_payload(source_type, row):
    return {field:str(row.get(field) or '').strip() for field in TEXT_FIELDS[source_type]}


def text_hash(source_type, row):
    value=json.dumps(text_payload(source_type,row),ensure_ascii=False,sort_keys=True)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def normalize_topic(title):
    return re.sub(r'\s+',' ',title.strip()).lower()
