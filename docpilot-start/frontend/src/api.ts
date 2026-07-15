// src/api.ts — API 호출 래퍼. 모든 경로는 /api 접두사(로컬은 vite 프록시, 배포는 nginx가 처리).
export interface DocumentOut {
  id: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string | null;
}

export async function getHealth(): Promise<{ status: string }> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(`health ${res.status}`);
  return res.json();
}

export async function listDocuments(): Promise<DocumentOut[]> {
  const res = await fetch("/api/documents");
  if (!res.ok) throw new Error(`list ${res.status}`);
  return res.json();
}

export async function uploadDocument(file: File): Promise<DocumentOut> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/documents", { method: "POST", body: form });
  if (!res.ok) throw new Error(`upload ${res.status}`);
  return res.json();
}
