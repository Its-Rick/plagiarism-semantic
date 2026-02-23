# app/utils/text_utils.py

import re

def split_sentences(text: str):
    return re.split(r'(?<=[.!?])\s+', text.strip())