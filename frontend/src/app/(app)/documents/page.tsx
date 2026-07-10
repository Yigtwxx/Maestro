'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { CSSProperties, DragEvent } from 'react';
import { FileText, UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Skeleton, SkeletonList } from '@/components/ui/Skeleton';
import { cn } from '@/lib/cn';
import { api, ApiError } from '@/lib/api';
import { MODULE_COLOR } from '@/lib/module-colors';
import type { DocumentMeta } from '@/types';

const mc = MODULE_COLOR.documents;

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentMeta[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | undefined>();
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setDocs(await api.listDocuments());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Documents could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const uploadFile = useCallback(
    async (file: File) => {
      setError(undefined);
      setUploading(true);
      try {
        await api.uploadDocument(file);
        await load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Upload failed.');
      } finally {
        setUploading(false);
        if (inputRef.current) inputRef.current.value = '';
      }
    },
    [load],
  );

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) await uploadFile(file);
  };

  const [dragging, setDragging] = useState(false);
  const onDragOver = (e: DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };
  const onDragLeave = () => setDragging(false);
  const onDrop = async (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) await uploadFile(file);
  };

  const onDelete = async (id: string) => {
    await api.deleteDocument(id);
    await load();
  };

  return (
    <div className="mx-auto max-w-4xl px-6 pt-5 pb-8">
      {error && <p className="mb-4 text-sm text-danger">&gt; ERROR: {error}</p>}

      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        style={{ ['--gb-rgb' as string]: mc.rgb } as CSSProperties}
        className={cn(
          'mb-8 flex flex-col items-center gap-3 rounded-lg p-8 text-center transition-all',
          dragging
            ? 'gradient-border scale-[1.01] shadow-glow-mod-documents'
            : 'border border-dashed border-module-documents/40 bg-surface hover:border-module-documents/70',
        )}
      >
        <UploadCloud className={`h-8 w-8 ${mc.text}`} aria-hidden />
        <p className="text-sm text-muted">Upload your .txt or .md file (max 2 MB)</p>
        <input
          ref={inputRef}
          type="file"
          accept=".txt,.md,.markdown"
          onChange={onUpload}
          className="hidden"
        />
        <Button
          variant="solid"
          module="documents"
          onClick={() => inputRef.current?.click()}
          loading={uploading}
        >
          Upload Document
        </Button>
      </div>

      <div className="rounded-lg border border-border bg-surface">
        <div className={`text-micro border-b border-border px-5 py-3 ${mc.text}`}>
          [ UPLOADED DOCUMENTS ]
        </div>
        {uploading && (
          <div className="border-b border-border px-5 py-4">
            <Skeleton module="documents" className="h-10" />
          </div>
        )}
        {loading ? (
          <div className="px-5 py-6">
            <p className={`mb-4 font-mono text-sm ${mc.text}`}>
              &gt; LOADING<span className="animate-blink">_</span>
            </p>
            <SkeletonList module="documents" rows={2} />
          </div>
        ) : docs.length === 0 ? (
          <p className="px-5 py-6 text-sm text-muted">&gt; No documents yet.</p>
        ) : (
          <ul className="stagger-children divide-y divide-border">
            {docs.map((doc) => (
              <li
                key={doc.id}
                className="flex items-center justify-between px-5 py-4"
              >
                <div className="flex items-center gap-3">
                  <FileText className={`h-4 w-4 shrink-0 ${mc.text}`} aria-hidden />
                  <div>
                    <p className="font-mono text-sm font-medium text-white">
                      {doc.filename}
                    </p>
                    <p className="text-micro mt-0.5 text-muted">
                      {doc.chunk_count} CHUNKS
                    </p>
                  </div>
                </div>
                <Button variant="danger-outline" onClick={() => onDelete(doc.id)}>
                  Delete
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
