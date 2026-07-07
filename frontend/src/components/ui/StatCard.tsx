interface StatCardProps {
  label: string;
  value: number | string;
}

/** Central summary tile used on the dashboard. */
export function StatCard({ label, value }: StatCardProps) {
  return (
    <div className="stat-card">
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value">{value}</span>
    </div>
  );
}
