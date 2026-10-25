"""Adapter for pinned Docling 2.142.1: supply words to TableFormer, retain lines."""

from docling.backend.pypdfium2_backend import (
    PyPdfiumDocumentBackend,
    PyPdfiumPageBackend,
    _rect_to_display_frame,
    pypdfium2_lock,
)
from docling_core.types.doc import BoundingBox, CoordOrigin
from docling_core.types.doc.page import BoundingRectangle, TextCell

from ragsystem.parsing.pdfium_words import words


class WordPageBackend(PyPdfiumPageBackend):
    def get_segmented_page(self):
        segmented = super().get_segmented_page()
        if segmented is None or segmented.has_words:
            return segmented
        size = self.get_size()
        with pypdfium2_lock:
            page = self._require_page()
            rotation, origin = page.get_rotation(), page.get_bbox()[:2]
            tokens = words(self.text_page)
            cells = []
            for index, token in enumerate(tokens):
                left, b, r, t = _rect_to_display_frame(token["bbox"], rotation, size, origin)
                cells.append(
                    TextCell(
                        index=index,
                        text=token["text"],
                        orig=token["text"],
                        from_ocr=False,
                        rect=BoundingRectangle.from_bounding_box(
                            BoundingBox(l=left, b=b, r=r, t=t, coord_origin=CoordOrigin.BOTTOMLEFT)
                        ).to_top_left_origin(size.height),
                    )
                )
        segmented.word_cells = cells
        segmented.has_words = bool(cells)
        return segmented


class WordDocumentBackend(PyPdfiumDocumentBackend):
    def load_page(self, page_no):
        with pypdfium2_lock:
            return WordPageBackend(self._pdoc, self.document_hash, page_no)
