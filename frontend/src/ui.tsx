import type { ReactNode } from "react";
import { AlertCircle, LoaderCircle } from "lucide-react";
import { humanize } from "./api";
export function Badge({
  children,
  tone = "",
  title,
}: {
  children: ReactNode;
  tone?: string;
  title?: string;
}) {
  return (
    <span className={`badge ${tone}`} title={title}>
      {children}
    </span>
  );
}
export function OriginBadge({ value }: { value: string }) {
  const labels: Record<string, string> = {
    mock: "Demo output",
    real_provider: "Verified execution",
    synthetic: "Demo data",
    archive: "Archive footage",
    current_snapshot: "Public snapshot",
    public_sensor: "Sensor observation",
    unavailable: "Unavailable",
  };
  return (
    <Badge
      title={
        value === "real_provider"
          ? "This request used the configured provider. Archived results do not imply a new model run."
          : undefined
      }
      tone={
        value === "synthetic" || value === "mock"
          ? "amber"
          : value === "unavailable"
            ? "orange"
            : ""
      }
    >
      {labels[value] || humanize(value)}
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
      <strong>{title}</strong>
      <p>{children}</p>
    </div>
  );
}
export function SafeLink({
  href,
  children,
  className,
}: {
  href: string | null | undefined;
  children: ReactNode;
  className?: string;
}) {
  return href && /^https?:\/\//.test(href) ? (
    <a href={href} className={className} target="_blank" rel="noreferrer">
      {children}
    </a>
  ) : (
    <span className={className}>{children}</span>
  );
}
