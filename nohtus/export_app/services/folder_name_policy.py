from __future__ import annotations


def install(folder_service) -> None:
    """Apply the canonical export case folder naming policy."""

    def is_omitted(value: object, *extra_labels: str) -> bool:
        normalized = str(value or '').replace(' ', '').casefold()
        omitted = {
            '',
            '미지정',
            '바이어미입력',
            '운송방식미입력',
            *(str(label or '').replace(' ', '').casefold() for label in extra_labels),
        }
        return normalized in omitted

    def case_folder_name(case) -> str:
        actual_ship_date = folder_service._actual_ship_date(case)
        buyer = folder_service.sanitize_folder_part(case['buyer'], '')
        transport = folder_service.sanitize_folder_part(case['transport_mode'], '')
        summary = folder_service.order_item_summary(int(case['id']))

        label_parts: list[str] = []
        if not is_omitted(buyer, '바이어 미입력'):
            label_parts.append(buyer)
        if not is_omitted(transport, '운송방식 미입력'):
            label_parts.append(transport)

        date_prefix = actual_ship_date.strftime('%m%d') if actual_ship_date else ''
        if label_parts:
            detail_prefix = f'{" " if date_prefix else ""}[{" ".join(label_parts)}] '
        else:
            detail_prefix = ' ' if date_prefix else ''
        name = f'{date_prefix}{detail_prefix}{summary}'

        if str(case['status']) == '취소' or str(case['stage']) == '취소':
            return name if name.startswith('[취소]') else f'[취소]{name}'
        return name.removeprefix('[취소]')

    folder_service.case_folder_name = case_folder_name
