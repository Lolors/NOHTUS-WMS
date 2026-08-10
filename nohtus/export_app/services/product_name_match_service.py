from __future__ import annotations

import re


NOISE_TERMS = (
    '대한', '유한', '한미', '휴온스', '대웅', '녹십자', '일동', '동아', '보령',
    '염산염', '염산', '황산염', '나트륨', '수화물',
    '주사액', '주사제', '주사', '정제', '캡슐', '시럽',
    'box', 'vial', 'ample', 'ampoule', 'amp',
)


def normalize_for_match(value: str) -> str:
    text = str(value or '').casefold()
    replacements = {
        '퍼센트': '%',
        '프로': '%',
        '앰플': 'am',
        'ampoule': 'am',
        'amp': 'am',
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    text = re.sub(r'[^0-9a-z가-힣%]+', '', text)
    for term in NOISE_TERMS:
        text = text.replace(term, '')

    text = re.sub(r'\d+(?:am|a|vial|ea|box)$', '', text)
    return text
