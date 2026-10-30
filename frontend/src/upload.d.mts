export type UploadProgress =
  { loaded: number; total: number } | null | "confirming";
export type UploadResult = {
  filename: string;
  duplicate?: boolean;
  error?: string;
  document?: {
    id: string;
    status: "queued" | "processing" | "ready" | "failed";
    generation_status?: "not_requested" | "generating" | "generated" | "failed";
  };
};
export function uploadBatch(
  url: string,
  files: File[],
  onProgress: (progress: UploadProgress) => void,
): Promise<UploadResult[]>;
