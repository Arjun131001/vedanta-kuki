"""Load a local dataset through the same HTTP upload path as the dashboard.

Run from backend: python import_demo.py "path/to/kuki-assignment-dataset"
The source files remain local and must not be committed to the repository.
"""

import argparse
from contextlib import ExitStack
from pathlib import Path

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error("Dataset directory does not exist.")
    paths = sorted(p for p in args.directory.iterdir() if p.suffix.lower() in {".pdf", ".xlsx"})
    if not paths:
        parser.error("No PDF or XLSX files found.")
    failures = 0
    # Match the API's ten-file batch limit and keep each source file streamed.
    with httpx.Client(base_url=args.api_url.rstrip("/"), timeout=120) as client:
        for offset in range(0, len(paths), 10):
            with ExitStack() as stack:
                files = [("files", (p.name, stack.enter_context(p.open("rb")))) for p in paths[offset:offset + 10]]
                response = client.post("/api/documents", files=files)
                response.raise_for_status()
                for result in response.json()["results"]:
                    if "error" in result:
                        failures += 1
                        print(f"Rejected: {result['filename']}: {result['error']}")
                    else:
                        doc = result["document"]
                        action = "Existing" if result["duplicate"] else "Added"
                        print(f"{action}: {result['filename']} | {doc['id']} | {doc['status']}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
