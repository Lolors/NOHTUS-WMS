import nohtus.pages.outbound as outbound_page


def _hide_last_sale_importer():
    return None


def page_outbound():
    original_renderer = outbound_page._render_last_sale_importer
    outbound_page._render_last_sale_importer = _hide_last_sale_importer
    try:
        return outbound_page.page_outbound()
    finally:
        outbound_page._render_last_sale_importer = original_renderer
