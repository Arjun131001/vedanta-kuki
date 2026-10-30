/** Send one multipart batch. Progress describes the full request, including multipart overhead. */
export function uploadBatch(
  url,
  files,
  onProgress,
  createRequest = () => new XMLHttpRequest(),
) {
  return new Promise((resolve, reject) => {
    const request = createRequest();
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    request.open("POST", url);
    request.timeout = 300000;
    request.upload.onprogress = (event) =>
      onProgress(
        event.lengthComputable
          ? { loaded: event.loaded, total: event.total }
          : null,
      );
    request.upload.onload = () => onProgress("confirming");
    request.onload = () => {
      let body;
      try {
        body = JSON.parse(request.responseText);
      } catch {
        reject(
          new Error(
            "The server returned an invalid response. Check the library before retrying.",
          ),
        );
        return;
      }
      if (!body || typeof body !== "object") {
        reject(
          new Error(
            "The server returned an invalid response. Check the library before retrying.",
          ),
        );
        return;
      }
      if (request.status < 200 || request.status >= 300) {
        reject(
          new Error(
            typeof body.detail === "string"
              ? body.detail
              : "Upload failed. Check the library before retrying.",
          ),
        );
      } else if (
        !Array.isArray(body.results) ||
        body.results.some(
          (result) =>
            !result ||
            typeof result.filename !== "string" ||
            (typeof result.error !== "string" &&
              (!result.document ||
                typeof result.document.id !== "string" ||
                !["queued", "processing", "ready", "failed"].includes(
                  result.document.status,
                ))),
        )
      ) {
        reject(
          new Error(
            "The server returned an invalid response. Check the library before retrying.",
          ),
        );
      } else resolve(body.results);
    };
    request.onerror = () =>
      reject(
        new Error(
          "Could not confirm upload: connection lost. Check the library before retrying; the server may have received some files.",
        ),
      );
    request.ontimeout = () =>
      reject(
        new Error(
          "Upload timed out. Check the library before retrying; the server may have received some files.",
        ),
      );
    request.onabort = () =>
      reject(
        new Error("Upload was interrupted. Check the library before retrying."),
      );
    request.send(form);
  });
}
