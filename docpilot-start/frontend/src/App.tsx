import { useEffect, useRef, useState } from "react";
import {
  DocumentOut,
  getHealth,
  listDocuments,
  uploadDocument,
} from "./api";

export function App() {
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setDocs(await listDocuments());
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    getHealth()
      .then(() => setHealth("ok"))
      .catch(() => setHealth("down"));
    refresh();
  }, []);

  async function onUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      await uploadDocument(file);
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="wrap">
      <header className="head">
        <h1>DocPilot</h1>
        <span className={`badge badge--${health}`}>
          API: {health === "checking" ? "확인 중" : health === "ok" ? "정상" : "연결 끊김"}
        </span>
      </header>

      <p className="sub">문서 기반 AI 도우미 — 시작 스캐폴드 (frontend · api · db)</p>

      <section className="card">
        <h2>문서 업로드</h2>
        <div className="row">
          <input ref={fileRef} type="file" />
          <button onClick={onUpload} disabled={busy}>
            {busy ? "업로드 중…" : "업로드"}
          </button>
        </div>
        {error && <p className="err">{error}</p>}
      </section>

      <section className="card">
        <h2>문서 목록 ({docs.length})</h2>
        {docs.length === 0 ? (
          <p className="muted">아직 업로드된 문서가 없습니다.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>파일명</th>
                <th>타입</th>
                <th>크기(B)</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>{d.id}</td>
                  <td>{d.filename}</td>
                  <td>{d.content_type}</td>
                  <td>{d.size_bytes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
