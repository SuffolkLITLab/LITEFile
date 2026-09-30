"""Small valid documents for upload tests, without optional PDF libraries."""

import io
import zipfile
from typing import Any, cast
from xml.sax.saxutils import escape

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    TextStringObject,
)


def pdf_bytes(text="Synthetic filing document", *, pages=1, form_value=None, missing_appearance=False):
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    fonts = DictionaryObject({NameObject("/Helv"): writer._add_object(font)})
    for index in range(pages):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})
        stream = DecodedStreamObject()
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /Helv 14 Tf 50 730 Td ({escaped} - page {index + 1}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if form_value is not None:
        widget = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Widget"),
                NameObject("/FT"): NameObject("/Tx"),
                NameObject("/T"): TextStringObject("answers"),
                NameObject("/V"): TextStringObject(form_value),
                NameObject("/Ff"): NumberObject(4096),
                NameObject("/F"): NumberObject(4),
                NameObject("/Rect"): ArrayObject([FloatObject(n) for n in [50, 500, 500, 650]]),
                NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 g"),
            }
        )
        ref = writer._add_object(widget)
        writer.pages[0][NameObject("/Annots")] = ArrayObject([ref])
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
            {
                NameObject("/Fields"): ArrayObject([ref]),
                NameObject("/DR"): DictionaryObject({NameObject("/Font"): fonts}),
                NameObject("/DA"): TextStringObject("/Helv 12 Tf 0 g"),
            }
        )
        writer.update_page_form_field_values(None, {"answers": form_value}, auto_regenerate=False)
        if missing_appearance:
            widget.pop("/AP", None)
            cast(Any, writer._root_object["/AcroForm"])[NameObject("/NeedAppearances")] = BooleanObject(True)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def docx_bytes(text="Synthetic Word filing"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>',
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p><w:p><w:r><w:t>/s/ Alex Example</w:t></w:r></w:p><w:p><w:r><w:br w:type="page"/></w:r></w:p><w:p><w:r><w:t>Second page exhibit. José García.</w:t></w:r></w:p></w:body></w:document>',
        )
    return output.getvalue()
