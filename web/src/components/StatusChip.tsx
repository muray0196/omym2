type StatusChipProps = {
  value: string;
};

export function StatusChip({ value }: StatusChipProps) {
  return <span className="status-chip">{value}</span>;
}
