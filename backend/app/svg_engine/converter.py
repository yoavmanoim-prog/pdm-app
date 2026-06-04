import fitz  # PyMuPDF — the library for PDF/SVG conversion


def pdf_to_svg(pdf_bytes: bytes, page_index: int = 0) -> str:
    # Open the PDF from raw bytes (no file needed on disk)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    if page_index >= len(doc):
        raise ValueError(f"Page {page_index} does not exist — PDF has {len(doc)} page(s)")

    page = doc[page_index]

    # get_svg_image() returns the page as an SVG string
    # SVG is XML so we can parse, diff, and merge it as text
    svg_string = page.get_svg_image(matrix=fitz.Identity)

    doc.close()
    return svg_string


def svg_to_pdf(svg_string: str) -> bytes:
    # Open the SVG as a PyMuPDF document — PyMuPDF handles SVG as a single-page doc
    svg_bytes = svg_string.encode("utf-8")
    svg_doc = fitz.open(stream=svg_bytes, filetype="svg")

    # convert_to_pdf() converts the SVG document directly to a PDF byte stream
    pdf_bytes = svg_doc.convert_to_pdf()

    svg_doc.close()
    return pdf_bytes


def pdf_page_count(pdf_bytes: bytes) -> int:
    # Returns how many pages are in a PDF
    # Used to warn engineers if they upload a multi-page drawing
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    count = len(doc)
    doc.close()
    return count
