export default function StatCard({ title, value, subtitle }) {
  return (
    <div className="card stat-card">
      <div className="muted">{title}</div>
      <div className="stat-value">{value}</div>
      {subtitle && <div className="small">{subtitle}</div>}
    </div>
  );
}
