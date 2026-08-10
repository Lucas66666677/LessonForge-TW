"use client";

import * as Dialog from "@radix-ui/react-dialog";
import * as Progress from "@radix-ui/react-progress";
import { AlertCircle, CheckCircle2, LoaderCircle, X } from "lucide-react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes,
} from "react";
import { clsx } from "clsx";

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <button
      className={clsx("button", `button-${variant}`, className)}
      {...props}
    />
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className="input" {...props} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className="input textarea" {...props} />;
}

export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {error ? (
        <span className="field-error" role="alert">
          {error}
        </span>
      ) : hint ? (
        <span className="field-hint">{hint}</span>
      ) : null}
    </label>
  );
}

export function Card({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return <section className={clsx("card", className)}>{children}</section>;
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function LoadingState({ label = "載入中…" }: { label?: string }) {
  return (
    <div className="state" role="status">
      <LoaderCircle className="spin" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="state empty">
      <div className="empty-mark" aria-hidden="true">
        LF
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="state error" role="alert">
      <AlertCircle aria-hidden="true" />
      <h2>載入失敗</h2>
      <p>{message}</p>
      {retry ? (
        <Button variant="secondary" onClick={retry}>
          再試一次
        </Button>
      ) : null}
    </div>
  );
}

export function StatusPill({ value }: { value: string }) {
  const labels: Record<string, string> = {
    draft: "草稿",
    review: "待審核",
    approved: "已核准",
    ready: "解析完成",
    failed: "失敗",
    pending: "等待解析",
    completed: "完成",
  };
  return (
    <span className={clsx("status-pill", `status-${value}`)}>
      {labels[value] ?? value}
    </span>
  );
}

export function Notice({
  kind = "success",
  children,
}: {
  kind?: "success" | "error";
  children: ReactNode;
}) {
  return (
    <div className={clsx("notice", `notice-${kind}`)} role="status">
      {kind === "success" ? <CheckCircle2 /> : <AlertCircle />}
      {children}
    </div>
  );
}

export function ProgressBar({
  value,
  label,
}: {
  value: number;
  label: string;
}) {
  return (
    <div className="progress-wrap">
      <div className="progress-label">
        <span>{label}</span>
        <strong>{value}%</strong>
      </div>
      <Progress.Root className="progress-root" value={value}>
        <Progress.Indicator
          className="progress-indicator"
          style={{ transform: `translateX(-${100 - value}%)` }}
        />
      </Progress.Root>
    </div>
  );
}

export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" />
        <Dialog.Content className="dialog-content">
          <div>
            <Dialog.Title>{title}</Dialog.Title>
            {description ? (
              <Dialog.Description>{description}</Dialog.Description>
            ) : null}
          </div>
          <Dialog.Close className="icon-button" aria-label="關閉">
            <X />
          </Dialog.Close>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
