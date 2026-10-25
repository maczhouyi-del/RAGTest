import json
import os
import sys
import threading
import time
from contextlib import ExitStack, closing, redirect_stdout
from pathlib import Path


def watch_parent(parent_pid: int):
    """End the bounded worker if its supervisor dies, including a forced kill."""
    if parent_pid <= 0:
        raise ValueError("PARENT_INVALID")
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE only
        if not handle:
            raise ValueError("PARENT_UNAVAILABLE")

        def wait():
            kernel.WaitForSingleObject(handle, 0xFFFFFFFF)
            kernel.CloseHandle(handle)
            os._exit(70)
    else:
        if os.getppid() != parent_pid:
            raise ValueError("PARENT_MISMATCH")

        def wait():
            while os.getppid() == parent_pid:
                time.sleep(0.2)
            os._exit(70)

    threading.Thread(target=wait, daemon=True).start()


def main():
    try:
        request = json.loads(sys.stdin.buffer.readline(16384))
        watch_parent(request["parent_pid"])
        if sys.platform != "win32":
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (240, 240))
            # macOS RLIMIT_AS is not an effective sandbox; record its limitations.
            if sys.platform == "linux":
                limit = (4 if request.get("docling_directory") else 1) * 1024**3
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        if request.get("docling_directory"):
            # Defence in depth for this fixed candidate worker; not an OS sandbox.
            import socket

            def offline(*args, **kwargs):
                raise OSError("DOCLING_NETWORK_DISABLED")

            socket.socket.connect = offline
            socket.socket.connect_ex = offline
            socket.create_connection = offline
            with redirect_stdout(sys.stderr):
                from ragsystem.parsing.docling import create_pipeline, parse_document

                if request.get("operation") == "docling_probe":
                    _, fingerprint = create_pipeline(request["docling_directory"])
                    result = {"docling_fingerprint": fingerprint}
                elif request.get("operation", "parse") == "parse":
                    result = parse_document(
                        request["docling_directory"],
                        request["pdf_path"],
                        request["docling_fingerprint"],
                        request.get("page_numbers"),
                    )
                else:
                    raise ValueError("OPERATION_INVALID")
            encoded = json.dumps(result, ensure_ascii=False).encode()
            if len(encoded) > 8 * 1024 * 1024:
                raise ValueError("OUTPUT_LIMIT")
            sys.stdout.buffer.write(encoded)
            sys.stdout.buffer.flush()
            return 0
        import pypdfium2 as pdfium

        from ragsystem.parsing.ocr import POLICY, native_api, recognize

        with ExitStack() as resources:
            ocr = None
            if request.get("ocr_directory"):
                api, fingerprint = native_api(request["ocr_directory"])
                ocr = resources.enter_context(api)
                if request.get("operation") == "ocr_probe":
                    sys.stdout.write(json.dumps({"ocr_fingerprint": fingerprint}))
                    return 0
                if request.get("ocr_fingerprint") != fingerprint:
                    from ragsystem.domain.errors import EngineError

                    raise EngineError("OCR_FINGERPRINT_CHANGED")
            path = Path(request["pdf_path"])
            pages, total_chars, ocr_pages = [], 0, 0
            document = resources.enter_context(pdfium.PdfDocument(path))
            if not 0 < len(document) <= 500:
                raise ValueError("PAGE_LIMIT")
            document_page_count = len(document)
            if request.get("operation") == "page_count":
                sys.stdout.write(json.dumps({"page_count": len(document)}))
                return 0
            if request.get("operation", "parse") != "parse":
                raise ValueError("OPERATION_INVALID")
            from ragsystem.parsing.publication import validate_selection
            from ragsystem.parsing.routing import probe

            selection = validate_selection(request.get("page_numbers"))
            if selection and max(selection) > len(document):
                from ragsystem.domain.errors import EngineError

                raise EngineError("SOURCE_PAGE_INVALID")
            for index in [n - 1 for n in selection] if selection else range(len(document)):
                try:
                    with closing(document[index]) as page:
                        rotation = page.get_rotation()
                        with closing(page.get_textpage()) as textpage:
                            if textpage.count_chars() > 50000:
                                pages.append(
                                    {
                                        "page_number": index + 1,
                                        "text": "",
                                        "error_code": "PAGE_TEXT_LIMIT",
                                        "rotation": rotation,
                                    }
                                )
                                continue
                            text = textpage.get_text_range()
                            error, confidence, method = None, None, "native_text"
                            if ocr is not None and (
                                index + 1 in request.get("force_ocr_pages", [])
                                or len("".join(text.split())) < POLICY["min_native_nonspace_chars"]
                            ):
                                ocr_pages += 1
                                if ocr_pages > POLICY["max_ocr_pages"]:
                                    error = "OCR_PAGE_LIMIT"
                                else:
                                    method = "ocr"
                                    text, error, confidence = recognize(page, ocr)
                            total_chars += len(text)
                            if total_chars > 1500000:
                                raise ValueError("DOCUMENT_TEXT_LIMIT")
                            pages.append(
                                {
                                    "page_number": index + 1,
                                    "text": text,
                                    "error_code": error,
                                    "rotation": rotation,
                                    "method": method,
                                    "mean_confidence": confidence,
                                    **(
                                        {"signals": probe(page, textpage, text)}
                                        if request.get("quality_probe")
                                        else {}
                                    ),
                                }
                            )
                except pdfium.PdfiumError:
                    pages.append(
                        {
                            "page_number": index + 1,
                            "text": "",
                            "error_code": "PAGE_EXTRACT_FAILED",
                            "rotation": 0,
                        }
                    )
        result = {
            "parser": "pypdfium2",
            "version": str(pdfium.PYPDFIUM_INFO),
            "pdfium_version": str(pdfium.PDFIUM_INFO),
            "pages": pages,
            "document_page_count": document_page_count,
        }
        encoded = json.dumps(result, ensure_ascii=False).encode()
        if len(encoded) > 8 * 1024 * 1024:
            raise ValueError("OUTPUT_LIMIT")
        sys.stdout.buffer.write(encoded)
        sys.stdout.buffer.flush()
        return 0
    except Exception as exc:
        # Only typed internal codes cross IPC; PDF metadata/exception text are untrusted.
        import traceback

        from ragsystem.domain.errors import EngineError

        traceback.print_exc(file=sys.stderr)

        code = exc.code if isinstance(exc, EngineError) else "PDF_EXTRACTION_FAILED"
        sys.stdout.write(json.dumps({"error_code": code}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
