interface SectionLabelProps {
  label: string;
  count?: string;
}

export function SectionLabel({ label, count }: SectionLabelProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 14,
        fontFamily: "var(--mono)",
        fontSize: 10.5,
        letterSpacing: "0.22em",
        color: "var(--mute)",
        textTransform: "uppercase",
        margin: "28px 0 14px",
      }}
    >
      <span style={{ color: "var(--amber)", marginRight: -8 }}>▌</span>
      <span>{label}</span>
      <div
        style={{
          flex: 1,
          height: 1,
          background: "linear-gradient(to right, var(--border) 0, var(--border) 60%, transparent)",
        }}
      />
      {count && (
        <span
          style={{
            fontFamily: "var(--mono)",
            color: "var(--ink-2)",
            fontSize: 10.5,
            letterSpacing: "0.18em",
            padding: "2px 8px",
            border: "1px solid var(--border-2)",
            background: "var(--panel)",
          }}
        >
          {count}
        </span>
      )}
    </div>
  );
}
