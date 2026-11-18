import { useId, type ReactNode } from "react";

/** Segmented control built on native radio inputs (keyboard + screen readers for free). */
export function Segmented<T extends string>({ label, value, options, onChange, size = "md" }: {
  label: string;
  value: T;
  options: { value: T; label: ReactNode; disabled?: boolean; title?: string }[];
  onChange(v: T): void;
  size?: "sm" | "md";
}) {
  const name = useId();
  return (
    <fieldset className="min-w-0">
      <legend className="sr-only">{label}</legend>
      <div className="flex rounded-lg bg-slate-100 p-0.5 ring-1 ring-slate-200">
        {options.map((o) => (
          <label key={o.value} title={o.title}
            className={`relative flex-1 cursor-pointer select-none rounded-md text-center font-medium transition
              ${size === "sm" ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm"}
              ${o.value === value ? "bg-white text-slate-900 shadow-sm ring-1 ring-slate-200" : "text-slate-600 hover:text-slate-900"}
              ${o.disabled ? "cursor-not-allowed opacity-40" : ""}
              has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-orange-500`}>
            <input type="radio" name={name} value={o.value} checked={o.value === value} disabled={o.disabled}
              aria-label={typeof o.label === "string" ? o.label : undefined}
              onChange={() => onChange(o.value)} className="sr-only" />
            {o.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

export function Notice({ tone, children }: { tone: "warn" | "info"; children: ReactNode }) {
  const c = tone === "warn" ? "bg-amber-50 text-amber-900 ring-amber-200" : "bg-sky-50 text-sky-900 ring-sky-200";
  return <div className={`rounded-lg px-3 py-2 text-xs leading-snug ring-1 ${c}`} role="note">{children}</div>;
}
