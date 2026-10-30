# Final delivery

Finalized 30 October 2026 (Asia/Calcutta).

The repository includes backend application and tests, frontend source and tests, evaluation scripts, technical documentation, local development scripts, and EC2 deployment tooling. Runtime secrets, uploaded documents, database files, generated evidence exports, dependency folders and temporary files are excluded.

The application and deployment API/worker settings use gpt-4o-mini. Release a833add passed 181 backend tests, 14 frontend tests and both production image builds. Live synthetic fact extraction and cited Q&A passed on EC2, as did HTTPS authentication, dashboard and document-library checks.

Production database was cleared again at the owner's request after creating a consistent backup. Uploaded file bytes remain on disk; database records and saved conversations are reset. Production backups are retained outside Git.

The final source commit does not deploy automatically: GitHub builds and requires production approval, then the existing local SSH deployment process applies the approved artifact. No persistent self-hosted runner was installed.
