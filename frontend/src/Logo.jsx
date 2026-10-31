export default function Logo({ width = 34, height = 34, style = {} }) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={{ flexShrink: 0, ...style }}
    >
      <path d="M24 4L6 10C6 24 13 36 24 42C35 36 42 24 42 10L24 4Z" fill="#0d9488" />
      <path d="M24 7.5L9.5 12.5C9.5 24 15.5 33.5 24 38.5C32.5 33.5 38.5 24 38.5 12.5L24 7.5Z" fill="var(--bg-secondary)" />
      <rect x="21" y="20" width="6" height="13" rx="3" fill="#0d9488" />
      <rect x="15" y="23" width="18" height="6" rx="3" fill="#0d9488" />
      <circle cx="24" cy="15" r="3.5" fill="#0d9488" />
    </svg>
  )
}
