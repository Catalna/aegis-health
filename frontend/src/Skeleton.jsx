/**
 * Skeleton loading untuk mencegah layout shift saat memuat data.
 */

function Line({ w = '100%', h = 10, className = '' }) {
  return <span className={`sk-line ${className}`} style={{ width: w, height: h }} aria-hidden="true" />
}

export function DashboardSkeleton() {
  return (
    <div className="sk-page" aria-hidden="true">
      <div className="sk-topbar">
        <div className="sk-stack">
          <div className="sk-row">
            <span className="sk-badge" />
            <Line w="180px" h={22} />
          </div>
          <Line w="340px" h={10} />
        </div>
        <span className="sk-pill-btn" />
      </div>

      <div className="sk-metrics">
        {[0, 1, 2, 3].map(i => (
          <div className="sk-card sk-card-metric" key={i}>
            <div className="sk-row sk-between">
              <Line w="70px" h={9} />
              <span className="sk-icon" />
            </div>
            <Line w="90px" h={26} />
            <Line w="130px" h={9} />
          </div>
        ))}
      </div>

      <div className="sk-card sk-card-summary">
        {[0, 1, 2].map(i => (
          <div className="sk-row sk-col" key={i}>
            <span className="sk-icon" />
            <div className="sk-stack sk-grow">
              <Line w="55%" h={9} />
              <Line w="70%" h={20} />
              <Line w="45%" h={8} />
            </div>
          </div>
        ))}
      </div>

      <div className="sk-charts">
        <div className="sk-card sk-card-chart">
          <Line w="45%" h={12} />
          <Line w="60%" h={9} />
          <div className="sk-block" />
        </div>
        <div className="sk-card sk-card-chart">
          <Line w="45%" h={12} />
          <Line w="60%" h={9} />
          <div className="sk-block" />
        </div>
      </div>
    </div>
  )
}

export function MonitoringSkeleton() {
  return (
    <div className="sk-page" aria-hidden="true">
      <div className="sk-metrics-2">
        {[0, 1, 2, 3].map(i => (
          <div className="sk-card sk-card-metric" key={i}>
            <Line w="110px" h={9} />
            <Line w="80px" h={32} />
          </div>
        ))}
      </div>

      <div className="sk-card sk-card-chart">
        <Line w="38%" h={12} />
        <Line w="55%" h={9} />
        <div className="sk-block" />
      </div>
    </div>
  )
}

export function ClaimsListSkeleton() {
  return (
    <div className="sk-page" aria-hidden="true">
      <div className="sk-topbar">
        <div className="sk-stack">
          <div className="sk-row">
            <span className="sk-badge" />
            <Line w="170px" h={22} />
          </div>
          <Line w="380px" h={10} />
        </div>
        <span className="sk-pill-btn" />
      </div>

      <div className="sk-card sk-card-filter">
        <div className="sk-block sk-block-search" />
        <div className="sk-row sk-chips">
          {[64, 88, 76, 92, 70].map((w, i) => <span className="sk-chip" key={i} style={{ width: w }} />)}
        </div>
      </div>

      <div className="sk-card sk-card-table">
        <div className="sk-row sk-between sk-table-head">
          <Line w="140px" h={12} />
          <Line w="220px" h={10} />
        </div>
        {[0, 1, 2, 3, 4, 5].map(i => (
          <div className="sk-table-row" key={i}>
            <div className="sk-stack sk-grow">
              <Line w="150px" h={11} />
              <Line w="100px" h={8} />
            </div>
            <Line w="80px" h={10} />
            <Line w="110px" h={10} />
            <Line w="120px" h={10} />
            <Line w="64px" h={10} />
          </div>
        ))}
      </div>
    </div>
  )
}
