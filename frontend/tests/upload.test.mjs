import test from "node:test";
import assert from "node:assert/strict";
import { uploadBatch } from "../src/upload.mjs";

function fakeRequest() {
  return {
    upload: {},
    open(method, url) {
      this.method = method;
      this.url = url;
    },
    send(form) {
      this.form = form;
    },
  };
}
const files = [new Blob(["hello"], { type: "application/pdf" })];

test("reports computable and indeterminate bytes, confirmation, then server outcomes", async () => {
  const xhr = fakeRequest();
  const events = [];
  const result = uploadBatch(
    "/api/documents",
    files,
    (event) => events.push(event),
    () => xhr,
  );
  assert.equal(xhr.method, "POST");
  assert.equal(xhr.url, "/api/documents");
  assert.equal(xhr.form.getAll("files").length, 1);
  xhr.upload.onprogress({ lengthComputable: true, loaded: 5, total: 10 });
  xhr.upload.onprogress({ lengthComputable: false, loaded: 6, total: 0 });
  xhr.upload.onload();
  xhr.status = 202;
  xhr.responseText = JSON.stringify({
    results: [
      {
        filename: "report.pdf",
        duplicate: true,
        document: { id: "123", status: "ready" },
      },
    ],
  });
  xhr.onload();
  assert.deepEqual(events, [{ loaded: 5, total: 10 }, null, "confirming"]);
  const outcomes = await result;
  assert.equal(outcomes[0].filename, "report.pdf");
  assert.equal(outcomes[0].duplicate, true);
});

test("reports server errors and timeout without claiming success", async () => {
  const xhr = fakeRequest();
  const result = uploadBatch(
    "/api/documents",
    files,
    () => {},
    () => xhr,
  );
  xhr.status = 400;
  xhr.responseText = JSON.stringify({ detail: "Too many files." });
  xhr.onload();
  await assert.rejects(result, /Too many files/);
  const timeout = fakeRequest();
  const timed = uploadBatch(
    "/api/documents",
    files,
    () => {},
    () => timeout,
  );
  timeout.ontimeout();
  await assert.rejects(timed, /timed out/);
});

test("rejects malformed success responses and network failures", async () => {
  const xhr = fakeRequest();
  const result = uploadBatch(
    "/api/documents",
    files,
    () => {},
    () => xhr,
  );
  xhr.status = 202;
  xhr.responseText = "{}";
  xhr.onload();
  await assert.rejects(result, /invalid response/);
  const network = fakeRequest();
  const disconnected = uploadBatch(
    "/api/documents",
    files,
    () => {},
    () => network,
  );
  network.onerror();
  await assert.rejects(disconnected, /connection lost/);
});

test("rejects malformed JSON", async () => {
  const xhr = fakeRequest();
  const result = uploadBatch(
    "/api/documents",
    files,
    () => {},
    () => xhr,
  );
  xhr.status = 202;
  xhr.responseText = "not JSON";
  xhr.onload();
  await assert.rejects(result, /invalid response/);
});

test("rejects null and invalid result shapes", async () => {
  for (const body of [
    "null",
    JSON.stringify({ results: [{ filename: "a" }] }),
  ]) {
    const xhr = fakeRequest();
    const result = uploadBatch(
      "/api/documents",
      files,
      () => {},
      () => xhr,
    );
    xhr.status = 202;
    xhr.responseText = body;
    xhr.onload();
    await assert.rejects(result, /invalid response/);
  }
});
