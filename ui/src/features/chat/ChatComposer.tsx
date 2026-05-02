import { useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Paperclip, Send, Square, Trash2, UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { useUploadFile, type FileMetadata } from "@/api/queries";
import { ApiError } from "@/api/client";
import { cn } from "@/lib/utils";
import { formatBytes } from "@/features/chat/MessageView";

interface ChatComposerProps {
  onSend: (text: string, attachments: FileMetadata[]) => Promise<void> | void;
  onCancel?: () => void;
  isStreaming: boolean;
  disabled?: boolean;
}

export function ChatComposer({ onSend, onCancel, isStreaming, disabled }: ChatComposerProps) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<FileMetadata[]>([]);
  const [error, setError] = useState<string | null>(null);
  const upload = useUploadFile();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const uploadFiles = async (files: File[]) => {
    setError(null);
    for (const file of files) {
      try {
        const meta = await upload.mutateAsync(file);
        setAttachments((prev) => [...prev, meta]);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : (err as Error).message);
      }
    }
  };

  const onDrop = async (accepted: File[]) => {
    if (accepted.length > 0) await uploadFiles(accepted);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    noClick: true,
    noKeyboard: true,
  });

  useEffect(() => {
    const onPaste = async (event: ClipboardEvent) => {
      const items = event.clipboardData?.items;
      if (!items) return;
      const files: File[] = [];
      for (const item of items) {
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) files.push(file);
        }
      }
      if (files.length === 0) return;
      event.preventDefault();
      await uploadFiles(files);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const removeAttachment = (id: string) =>
    setAttachments((prev) => prev.filter((a) => a.file_id !== id));

  const submit = async () => {
    const trimmed = text.trim();
    if (!trimmed && attachments.length === 0) return;
    await onSend(trimmed, attachments);
    setText("");
    setAttachments([]);
    textareaRef.current?.focus();
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (
      e.key === "Enter" &&
      !e.shiftKey &&
      (e.metaKey || e.ctrlKey || !e.nativeEvent.isComposing)
    ) {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <div
      {...getRootProps()}
      className={cn(
        "mx-auto w-full max-w-3xl rounded-xl border border-border bg-card p-3 shadow-sm transition-colors focus-within:border-primary/40 focus-within:ring-1 focus-within:ring-primary/20",
        isDragActive && "border-primary/60 bg-primary/5",
      )}
    >
      <input {...getInputProps()} />
      {isDragActive ? (
        <div className="flex items-center gap-2 px-1 pb-2 text-xs text-primary">
          <UploadCloud className="h-4 w-4" />
          <span>Drop files to attach…</span>
        </div>
      ) : null}

      {attachments.length > 0 ? (
        <ul className="mb-2 flex flex-wrap gap-2">
          {attachments.map((att) => (
            <li key={att.file_id}>
              <Badge variant="secondary" className="gap-1.5">
                <span className="font-medium">{att.name}</span>
                <span className="text-muted-foreground">{formatBytes(att.size)}</span>
                <button
                  type="button"
                  aria-label="Remove attachment"
                  className="text-muted-foreground hover:text-destructive"
                  onClick={() => removeAttachment(att.file_id)}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </Badge>
            </li>
          ))}
        </ul>
      ) : null}

      {upload.isPending ? (
        <p className="px-1 pb-2 text-xs text-muted-foreground">Uploading…</p>
      ) : null}
      {error ? (
        <p className="px-1 pb-2 text-xs text-destructive">{error}</p>
      ) : null}

      <Textarea
        ref={textareaRef}
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Ask the agent…  (drag files in or paste images)"
        className="resize-none border-0 bg-transparent p-0 font-sans text-[15px] leading-relaxed shadow-none focus-visible:ring-0"
        disabled={disabled}
      />

      <div className="mt-2 flex items-center gap-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            const files = Array.from(e.target.files ?? []);
            if (files.length > 0) void uploadFiles(files);
            e.target.value = "";
          }}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
        >
          <Paperclip className="h-4 w-4" />
          Attach
        </Button>
        <span className="text-xs text-muted-foreground">
          ⌘/Ctrl + Enter to send
        </span>
        <div className="ml-auto flex items-center gap-2">
          {isStreaming && onCancel ? (
            <Button type="button" variant="outline" size="sm" onClick={onCancel}>
              <Square className="h-3.5 w-3.5" />
              Stop
            </Button>
          ) : null}
          <Button type="button" size="sm" onClick={() => void submit()} disabled={disabled || isStreaming}>
            <Send className="h-4 w-4" />
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}
