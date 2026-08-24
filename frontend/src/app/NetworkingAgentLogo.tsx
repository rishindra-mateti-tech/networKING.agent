type NetworkingAgentLogoProps = {
  className?: string;
  /** Render the wordmark under the crown. Off for sidebar badges and favicons. */
  showWordmark?: boolean;
  /** Draw the zinc-950 plate behind the mark. Off for transparent use. */
  showPlate?: boolean;
};

export default function NetworkingAgentLogo({
  className = "w-64 h-64",
  showWordmark = false,
  showPlate = false,
}: NetworkingAgentLogoProps) {
  return (
    <svg
      viewBox="0 0 1024 1024"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="networKING.agent"
    >
      <defs>
        <linearGradient id="nka-structure" x1="0" y1="215" x2="0" y2="680" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fafafa" />
          <stop offset="1" stopColor="#a1a1aa" />
        </linearGradient>
      </defs>

      {showPlate && <rect width="1024" height="1024" fill="#09090b" rx="180" />}

      {/* Interior relationship mesh */}
      <g stroke="url(#nka-structure)" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round">
        <line x1="505" y1="235" x2="505" y2="375" />
        <line x1="505" y1="375" x2="505" y2="510" />
        <line x1="505" y1="375" x2="440" y2="438" />
        <line x1="505" y1="375" x2="570" y2="438" />
        <line x1="440" y1="438" x2="505" y2="510" />
        <line x1="570" y1="438" x2="505" y2="510" />
        <line x1="350" y1="358" x2="400" y2="512" />
        <line x1="660" y1="358" x2="610" y2="512" />
        <line x1="287" y1="508" x2="400" y2="512" />
        <line x1="723" y1="508" x2="610" y2="512" />
        <line x1="287" y1="508" x2="345" y2="565" />
        <line x1="723" y1="508" x2="665" y2="565" />
        <line x1="400" y1="512" x2="505" y2="510" />
        <line x1="610" y1="512" x2="505" y2="510" />
        <line x1="400" y1="512" x2="345" y2="565" />
        <line x1="610" y1="512" x2="665" y2="565" />
        <line x1="345" y1="565" x2="505" y2="510" />
        <line x1="665" y1="565" x2="505" y2="510" />
        <line x1="345" y1="565" x2="290" y2="618" />
        <line x1="665" y1="565" x2="720" y2="618" />
        <line x1="345" y1="565" x2="505" y2="618" />
        <line x1="665" y1="565" x2="505" y2="618" />
        <line x1="505" y1="510" x2="505" y2="618" />
        <line x1="287" y1="508" x2="290" y2="618" />
        <line x1="723" y1="508" x2="720" y2="618" />
        <line x1="200" y1="370" x2="290" y2="618" />
        <line x1="810" y1="370" x2="720" y2="618" />
      </g>

      {/* Crown skyline, outer spikes, and base band */}
      <g stroke="url(#nka-structure)" strokeWidth="11" strokeLinecap="round" strokeLinejoin="round">
        <line x1="200" y1="370" x2="287" y2="508" />
        <line x1="287" y1="508" x2="350" y2="358" />
        <line x1="350" y1="358" x2="440" y2="438" />
        <line x1="440" y1="438" x2="505" y2="235" />
        <line x1="505" y1="235" x2="570" y2="438" />
        <line x1="570" y1="438" x2="660" y2="358" />
        <line x1="660" y1="358" x2="723" y2="508" />
        <line x1="723" y1="508" x2="810" y2="370" />
        <line x1="200" y1="370" x2="190" y2="655" />
        <line x1="810" y1="370" x2="820" y2="655" />
        <line x1="290" y1="618" x2="505" y2="618" />
        <line x1="505" y1="618" x2="720" y2="618" />
        <line x1="290" y1="618" x2="190" y2="655" />
        <line x1="720" y1="618" x2="820" y2="655" />
        <line x1="190" y1="655" x2="820" y2="655" />
      </g>

      {/* Outreach highlights — messages in flight across the graph */}
      <g stroke="#ffffff" strokeWidth="12" strokeLinecap="round">
        <line x1="392" y1="437" x2="448" y2="468" />
        <line x1="618" y1="437" x2="562" y2="468" />
        <line x1="358" y1="563" x2="414" y2="592" />
        <line x1="652" y1="563" x2="596" y2="592" />
      </g>
      <g fill="#ffffff">
        <circle cx="392" cy="437" r="13" />
        <circle cx="618" cy="437" r="13" />
        <circle cx="358" cy="563" r="13" />
        <circle cx="652" cy="563" r="13" />
      </g>

      {/* Structural nodes */}
      <g fill="url(#nka-structure)">
        <circle cx="505" cy="235" r="24" />
        <circle cx="350" cy="358" r="22" />
        <circle cx="660" cy="358" r="22" />
        <circle cx="200" cy="370" r="22" />
        <circle cx="810" cy="370" r="22" />
        <circle cx="440" cy="438" r="18" />
        <circle cx="570" cy="438" r="18" />
        <circle cx="345" cy="565" r="18" />
        <circle cx="665" cy="565" r="18" />
        <circle cx="290" cy="618" r="18" />
        <circle cx="720" cy="618" r="18" />
        <circle cx="190" cy="655" r="20" />
        <circle cx="820" cy="655" r="20" />
      </g>

      {/* Active nodes — same emerald the pipeline uses for live workers */}
      <g fill="#34d399">
        <circle cx="505" cy="375" r="19" />
        <circle cx="287" cy="508" r="17" />
        <circle cx="723" cy="508" r="17" />
        <circle cx="400" cy="512" r="19" />
        <circle cx="610" cy="512" r="19" />
        <circle cx="505" cy="618" r="19" />
      </g>

      {/* The agent: the hub every path routes through */}
      <circle cx="505" cy="510" r="27" fill="#09090b" stroke="#fafafa" strokeWidth="11" />
      <circle cx="505" cy="510" r="11" fill="#34d399" />

      {showWordmark && (
        <text
          x="512"
          y="800"
          textAnchor="middle"
          fontFamily="ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
          fontSize="72"
          fontWeight="500"
          letterSpacing="-0.02em"
        >
          <tspan fill="#ffffff">networ</tspan>
          <tspan fill="#34d399" fontWeight="700">KING</tspan>
          <tspan fill="#a1a1aa">.agent</tspan>
        </text>
      )}
    </svg>
  );
}
