import type { ReactNode } from "react";
import { AlertCircle, LoaderCircle } from "lucide-react";
import { humanize } from "./api";
export function Badge({
  children,
  tone = "",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function OriginBadge({ value }: { value: string }) {
  return (
    <Badge
      tone={
        value === "synthetic" || value === "mock"
          ? "amber"
          : value === "unavailable"
            ? "orange"
            : ""
      }
    >
      {humanize(value)}
    </Badge>
  );
}
export function ErrorMessage({ error }: { error: string | null }) {
  return error ? (
    <div className="error-message" role="alert">
      <AlertCircle size={16} />
      <span>{error}</span>
    </div>
  ) : null;
}
export function Loading({ label = "Loading evidence…" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={18} />
      {label}
    </div>
  );
}
export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-mark">⊙</span>
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
export function SafeLink({
  href,
  children,
}: {
  href: string | null | undefined;
  children: ReactNode;
}) {
  return href && /^https?:\/\//.test(href) ? (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  ) : (
    <span>{children}</span>
  );
}
