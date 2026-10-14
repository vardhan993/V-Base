interface ContactAvatarProps {
  name: string;
  hue?: number;
  size?: number | string;
  className?: string;
}

const SATURATION = 55;
//: Lightness comes from CSS so it can drop in dark mode — white initials on a
//: 52%-lightness fill measured only ~2.2:1.
const LIGHTNESS_VAR = "var(--vbase-avatar-lightness, 46%)";

function initials(name: string): string {
  const parts = name.trim().split(/[\s]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function hueColor(hue: number): string {
  return `hsl(${hue}, ${SATURATION}%, ${LIGHTNESS_VAR})`;
}

const FALLBACK_HUES = [220, 170, 30, 340, 120, 280];

export function ContactAvatar({ name, hue, size = 32, className = "" }: ContactAvatarProps) {
  const label = initials(name);
  const background = hue != null ? hueColor(hue) : hueColor(FALLBACK_HUES[label.charCodeAt(0) % FALLBACK_HUES.length]);

  return (
    <div
      className={`flex items-center justify-center rounded-full text-white font-medium ${className}`.trim()}
      style={{
        width: size,
        height: size,
        fontSize: typeof size === "number" ? Math.max(11, size * 0.36) : "0.875rem",
        background,
      }}
      title={name}
    >
      {label}
    </div>
  );
}
