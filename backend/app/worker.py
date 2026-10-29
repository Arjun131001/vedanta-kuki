import logging
import signal
import threading

from .config import Settings
from .store import Store
from .validation import validate_file
from .extraction import extract_source
from . import fact_queue, qa_store
from .qa import answer_question
from .facts import call_openai, FactError, SCHEMA_HASH, PROMPT_VERSION, all_rejected

logger = logging.getLogger(__name__)


def process_one(store: Store, validator=validate_file):
    job = store.claim()
    if not job:
        return False
    stop = threading.Event()

    def renew():
        while not stop.wait(max(1, store.settings.lease_seconds / 3)):
            if not store.heartbeat(job):
                return

    heartbeat = threading.Thread(target=renew, daemon=True)
    heartbeat.start()
    try:
        validation = validator(store.settings.uploads_dir / job["storage_key"], job["document_kind"])
        source = extract_source(store.settings.uploads_dir / job["storage_key"], job["document_kind"])
        store.finish(job, validation=validation, source=source)
    except Exception as exc:
        # Return useful parser errors, never a traceback or internal file path to clients.
        if isinstance(exc, ValueError):
            error = str(exc)[:300]
        else:
            error = "Processing could not read this file. It may be damaged, encrypted, or unsupported."
        logger.warning("Processing failed for document %s (%s)", job["document_id"], type(exc).__name__)
        store.finish(job, error=error, permanent=isinstance(exc, ValueError))
    finally:
        stop.set()
        heartbeat.join(timeout=2)
    return True


def process_fact(store: Store, caller=call_openai):
    job = fact_queue.claim(store)
    if not job:
        return False
    stop = threading.Event()
    def renew():
        while not stop.wait(max(1, store.settings.lease_seconds / 3)):
            if not fact_queue.heartbeat(store, job):
                return
    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        import json
        if job["provider"] != "openai" or job["model"] != store.settings.openai_model:
            raise FactError("The provider or model changed while queued. Request a new extraction explicitly.")
        if job["schema_hash"] != SCHEMA_HASH or job["prompt_version"] != PROMPT_VERSION:
            raise FactError("The extraction configuration changed while queued. Retry to use the current version.")
        source = json.loads(job["source_snapshot"])
        output = caller(source, job["model"], store.settings.openai_api_key, segment=json.loads(job["segment_payload"]))
        output["schema_hash"] = job["schema_hash"]
        output["source_hash"] = job["source_hash"]
        output["document_hash"] = job["document_hash"]
        fact_queue.finish(store, job, output=output)
    except FactError as exc:
        fact_queue.finish(store, job, error=str(exc), permanent=exc.permanent)
    except Exception as exc:
        logger.warning("Fact extraction failed for document %s (%s)", job["document_id"], type(exc).__name__)
        fact_queue.finish(store, job, error="Fact extraction failed. Please review the configuration and retry.", permanent=True)
    finally:
        stop.set()
        thread.join(timeout=2)
    return True


def process_question(store: Store, caller=answer_question):
    job = qa_store.claim(store)
    if not job:
        return False
    stop = threading.Event()
    def renew():
        while not stop.wait(max(1, store.settings.lease_seconds / 3)):
            if not qa_store.heartbeat(store, job):
                return
    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        import json
        if job["model"] != store.settings.openai_model:
            raise FactError("The model changed while this question was queued; submit a new question explicitly.")
        output = caller(job["question"], json.loads(job["evidence_json"]), json.loads(job["history_json"]), job["model"], store.settings.openai_api_key)
        qa_store.finish(store, job, result=output)
    except FactError as exc:
        qa_store.finish(store, job, error=str(exc), audit=getattr(exc, "qa_audit", None))
    except Exception as exc:
        logger.warning("Question processing failed (%s)", type(exc).__name__)
        qa_store.finish(store, job, error="Question processing failed. Submit a new question to retry.")
    finally:
        stop.set()
        thread.join(timeout=2)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = Store(Settings())
    stopped = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stopped.set())
    logger.info("Source extraction worker started")
    while not stopped.is_set():
        processed_source = process_one(store)
        queued_generation = fact_queue.enqueue_automatic(store)
        if not processed_source and not queued_generation and not process_question(store) and not process_fact(store):
            stopped.wait(store.settings.poll_seconds)


if __name__ == "__main__":
    main()
